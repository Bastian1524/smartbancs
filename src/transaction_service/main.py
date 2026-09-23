from fastapi import FastAPI, Header, Request
import asyncpg, uuid, time, asyncio, httpx, os, json, logging
from prometheus_client import Counter, Histogram, make_asgi_app

app = FastAPI(title="SmartBancs Transaction API")
# 3.4 Observabilidad
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartbancs")

TX_COUNTER = Counter('transactions_total', 'Total TX', ['status'])
TX_LATENCY = Histogram('transaction_duration_seconds', 'Latencia transfer')
TX_ERRORS = Counter('transactions_errors_total', 'Errores', ['reason'])
pool = None
AI_URL = os.getenv("AI_SERVICE_URL", "http://ai_api:8001")

@app.on_event("startup")
async def startup():
    global pool
    for i in range(15):
        try:
            pool = await asyncpg.create_pool(
                dsn=os.getenv("DATABASE_URL", "postgresql://bancs:bancs123@db:5432/smartbancs"),
                min_size=10, 
                max_size=50,  # 3.5 Fix para picos de quincena
                command_timeout=5
            )
            logger.info("DB conectada OK - pool 10-50")
            return
        except Exception as e:
            logger.warning(f"Esperando DB... intento {i+1}/15: {e}")
            await asyncio.sleep(2)
    raise Exception("No se pudo conectar a la DB")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

async def call_ai_async(data: dict):
    # 3.3 IA async no bloqueante - timeout corto para no afectar <2s
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{AI_URL}/recommend", json=data)
        logger.info(json.dumps({"trace_id": data.get("trace_id"), "ia": "solicitada"}))
    except Exception as e:
        # Si IA falla, la transferencia NO falla - requisito crítico
        logger.warning(json.dumps({"trace_id": data.get("trace_id"), "ia_error": str(e)}))

@app.post("/transfer")
async def transfer(
    payload: dict, 
    request: Request,
    idempotency_key: str = Header(..., alias="idempotency-key"), 
    x_trace_id: str = Header(default=None, alias="x-trace-id")
):
    trace_id = x_trace_id or str(uuid.uuid4())
    start = time.time()
    from_acc = payload.get('from')
    to_acc = payload.get('to')
    try:
        amount = float(payload.get('amount', 0))
    except:
        amount = 0

    if not from_acc or not to_acc or amount <= 0 or from_acc == to_acc:
        TX_ERRORS.labels(reason='validacion').inc()
        return {"status": "FAILED", "reason": "Datos inválidos", "trace_id": trace_id}
    
    # 3.5 Anti-deadlock: siempre bloquear en el mismo orden
    first, second = (from_acc, to_acc) if from_acc < to_acc else (to_acc, from_acc)
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                # 1. Idempotencia PRIMERO
                existing = await conn.fetchrow("SELECT id, status FROM transactions WHERE idempotency_key = $1", idempotency_key)
                if existing:
                    logger.info(json.dumps({"trace_id": trace_id, "idempotency": "hit", "key": idempotency_key}))
                    return {"status": existing['status'], "tx_id": str(existing['id']), "trace_id": trace_id, "message": "Idempotente - ya procesado"}

                # 2. Bloquear cuentas en orden - FIX DEADLOCK
                await conn.execute("SELECT id FROM accounts WHERE id IN ($1, $2) ORDER BY id FOR UPDATE", first, second)
                
                # 3. Validar fondos
                bal = await conn.fetchval("SELECT balance FROM accounts WHERE id=$1", from_acc)
                if bal is None:
                    TX_ERRORS.labels(reason='cuenta_no_existe').inc()
                    return {"status": "FAILED", "reason": "Cuenta origen no existe", "trace_id": trace_id}
                if bal < amount:
                    TX_ERRORS.labels(reason='fondos').inc()
                    return {"status": "FAILED", "reason": "Fondos insuficientes", "trace_id": trace_id}

                # 4. Mover plata - atomic
                await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id=$2", amount, from_acc)
                await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id=$2", amount, to_acc)
                
                tx_id = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO transactions (id, from_account, to_account, amount, status, idempotency_key, trace_id) VALUES ($1::uuid, $2, $3, $4, 'COMPLETED', $5, $6)", 
                    tx_id, from_acc, to_acc, amount, idempotency_key, trace_id
                )
                # 3.2 Outbox para Bancs legacy - no saturar core
                await conn.execute("INSERT INTO outbox_events (payload) VALUES ($1)", json.dumps({"tx_id": tx_id, "from": from_acc, "to": to_acc, "amount": amount, "trace_id": trace_id}))

                # 3.3 IA async, no bloquea el <2s
                asyncio.create_task(call_ai_async({"user_id": from_acc, "amount": amount, "trace_id": trace_id}))
                
                TX_COUNTER.labels(status='completed').inc()
                TX_LATENCY.observe(time.time() - start)
                
                logger.info(json.dumps({"trace_id": trace_id, "tx_id": tx_id, "from": from_acc, "to": to_acc, "amount": amount, "latencia_ms": int((time.time()-start)*1000)}))
                
                return {"status": "COMPLETED", "tx_id": tx_id, "trace_id": trace_id, "latency_ms": int((time.time()-start)*1000)}
                
            except asyncpg.exceptions.UniqueViolationError:
                # Carrera de idempotencia - 2 requests con misma key al mismo tiempo
                existing = await conn.fetchrow("SELECT id FROM transactions WHERE idempotency_key = $1", idempotency_key)
                if existing:
                    return {"status": "COMPLETED", "tx_id": str(existing['id']), "message": "Idempotencia por carrera", "trace_id": trace_id}
                raise
            except asyncpg.exceptions.DeadlockDetectedError as e:
                TX_ERRORS.labels(reason='deadlock').inc()
                logger.error(json.dumps({"trace_id": trace_id, "error": "deadlock_detected", "detail": str(e)}))
                # Reintento automático sería aquí, por ahora devolvemos error para que cliente reintente con misma idempotency_key
                return {"status": "FAILED", "reason": "Deadlock - reintente", "trace_id": trace_id}

# Métricas para 3.4
app.mount("/metrics", make_asgi_app())

@app.get("/")
def health():
    return {"status": "SmartBancs UP - listo para 30 concurrentes", "pool": "10-50", "ai_url": AI_URL}