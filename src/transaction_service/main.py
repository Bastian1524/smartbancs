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
    pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL", "postgresql://bancs:bancs123@db:5432/smartbancs"), min_size=10, max_size=50)
@app.post("/transfer")
async def transfer(payload: dict, idempotency_key: str = Header(...), x_trace_id: str = Header(default=None)):
    trace_id = x_trace_id or str(uuid.uuid4())
    start = time.time()
    from_acc, to_acc, amount = payload['from'], payload['to'], float(payload['amount'])
    first, second = (from_acc, to_acc) if from_acc < to_acc else (to_acc, from_acc)
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                await conn.execute("SELECT * FROM accounts WHERE id IN ($1,$2) ORDER BY id FOR UPDATE", first, second)
                bal = await conn.fetchval("SELECT balance FROM accounts WHERE id=$1", from_acc)
                if bal is None or bal < amount:
                    return {"status": "FAILED", "reason": "Fondos insuficientes"}
                await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id=$2", amount, from_acc)
                await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id=$2", amount, to_acc)
                tx_id = str(uuid.uuid4())
                await conn.execute("INSERT INTO transactions (id, from_account, to_account, amount, status, idempotency_key, trace_id) VALUES ($1::uuid, $2, $3, $4, 'COMPLETED', $5, $6)", tx_id, from_acc, to_acc, amount, idempotency_key, trace_id)
                await conn.execute("INSERT INTO outbox_events (payload) VALUES ($1)", json.dumps({"tx_id": tx_id, "from": from_acc}))
                asyncio.create_task(call_ai_async({"user_id": from_acc, "amount": amount, "trace_id": trace_id}))
                TX_COUNTER.labels(status='completed').inc()
                TX_LATENCY.observe(time.time() - start)
                return {"status": "COMPLETED", "tx_id": tx_id, "trace_id": trace_id, "latency_ms": int((time.time()-start)*1000)}
            except Exception as e:
                if "UniqueViolation" in str(type(e)) or "duplicate" in str(e).lower():
                    return {"status": "COMPLETED", "message": "Idempotencia"}
                raise
async def call_ai_async(data: dict):
    try:
        async with httpx.AsyncClient(timeout=0.1) as client:
            await client.post("http://ai_api:8001/recommend", json=data)
    except:
        pass
app.mount("/metrics", make_asgi_app())
@app.get("/")
def health():
    return {"status": "SmartBancs UP"}
