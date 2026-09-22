from fastapi import FastAPI, Header
import asyncpg, uuid, time, asyncio, httpx, os, json
from prometheus_client import Counter, Histogram, make_asgi_app

app = FastAPI()
TX_COUNTER = Counter('transactions_total', 'Total', ['status'])
TX_LATENCY = Histogram('transaction_duration_seconds', 'Latencia')
pool = None

@app.on_event("startup")
async def startup():
    global pool
    # REINTENTO para que no falle con ConnectionRefusedError
    for i in range(15):
        try:
            pool = await asyncpg.create_pool(
                dsn=os.getenv("DATABASE_URL", "postgresql://bancs:bancs123@db:5432/smartbancs"),
                min_size=10, 
                max_size=50
            )
            print("Conectado a DB!")
            return
        except Exception as e:
            print(f"Esperando DB... intento {i+1}/15: {e}")
            await asyncio.sleep(2)
    raise Exception("No se pudo conectar a la DB")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

@app.post("/transfer")
async def transfer(payload: dict, idempotency_key: str = Header(..., alias="idempotency-key"), x_trace_id: str = Header(default=None, alias="x-trace-id")):
    trace_id = x_trace_id or str(uuid.uuid4())
    start = time.time()
    from_acc, to_acc, amount = payload['from'], payload['to'], float(payload['amount'])
    
    # Anti-deadlock: siempre bloquear en el mismo orden
    first, second = (from_acc, to_acc) if from_acc < to_acc else (to_acc, from_acc)
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                # 1. Chequear idempotencia PRIMERO
                existing = await conn.fetchrow("SELECT id, status FROM transactions WHERE idempotency_key = $1", idempotency_key)
                if existing:
                    return {"status": existing['status'], "tx_id": str(existing['id']), "trace_id": trace_id, "message": "Idempotente - ya procesado"}

                # 2. Bloquear cuentas en orden
                await conn.execute("SELECT id FROM accounts WHERE id IN ($1, $2) ORDER BY id FOR UPDATE", first, second)
                
                # 3. Validar fondos
                bal = await conn.fetchval("SELECT balance FROM accounts WHERE id=$1", from_acc)
                if bal is None:
                    return {"status": "FAILED", "reason": "Cuenta origen no existe"}
                if bal < amount:
                    return {"status": "FAILED", "reason": "Fondos insuficientes"}

                # 4. Mover plata
                await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id=$2", amount, from_acc)
                await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id=$2", amount, to_acc)
                
                tx_id = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO transactions (id, from_account, to_account, amount, status, idempotency_key, trace_id) VALUES ($1::uuid, $2, $3, $4, 'COMPLETED', $5, $6)", 
                    tx_id, from_acc, to_acc, amount, idempotency_key, trace_id
                )
                await conn.execute("INSERT INTO outbox_events (payload) VALUES ($1)", json.dumps({"tx_id": tx_id, "from": from_acc, "trace_id": trace_id}))

                # IA async, no bloquea
                asyncio.create_task(call_ai_async({"user_id": from_acc, "amount": amount, "trace_id": trace_id}))
                
                TX_COUNTER.labels(status='completed').inc()
                TX_LATENCY.observe(time.time() - start)
                
                return {"status": "COMPLETED", "tx_id": tx_id, "trace_id": trace_id, "latency_ms": int((time.time()-start)*1000)}
                
            except asyncpg.exceptions.UniqueViolationError:
                # Carrera de idempotencia
                existing = await conn.fetchrow("SELECT id FROM transactions WHERE idempotency_key = $1", idempotency_key)
                return {"status": "COMPLETED", "tx_id": str(existing['id']), "message": "Idempotencia por carrera"}

async def call_ai_async(data: dict):
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            await client.post("http://ai_api:8001/recommend", json=data)
    except:
        pass

app.mount("/metrics", make_asgi_app())

@app.get("/")
def health():
    return {"status": "SmartBancs UP - listo para 30 concurrentes"}