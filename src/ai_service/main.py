# SmartBancs MVP completo - TCS NextGen
from fastapi import FastAPI, Header, BackgroundTasks, Request
import uuid
import httpx
import logging
import json
import time
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse

app = FastAPI(title="SmartBancs API")

# --- CONFIG DB ---
DB_URL = os.getenv("DATABASE_URL", "postgresql://bancs:bancs123@db:5432/smartbancs")

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

# --- OBSERVABILIDAD 3.4 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartbancs")

TX_COUNTER = Counter('smartbancs_transacciones_total', 'Total TX')
TX_ERRORS = Counter('smartbancs_errores_total', 'Errores')
TX_LATENCY = Histogram('smartbancs_latencia_seg', 'Latencia TX')

# --- 3.3 IA ASYNC NO BLOQUEANTE ---
async def call_ia_async(tx_id: str, data: dict, trace_id: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://ia_service:8001/recomendar",
                json={"transaction_id": tx_id, "trace_id": trace_id, **data},
                timeout=2.0
            )
        logger.info(json.dumps({"trace_id": trace_id, "ia": "solicitada", "tx_id": tx_id}))
    except Exception as e:
        # Si IA falla, NO afecta la transferencia
        logger.warning(json.dumps({"trace_id": trace_id, "ia_error": str(e), "tx_id": tx_id}))

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    start = time.time()
    try:
        response = await call_next(request)
        latency = time.time() - start
        TX_LATENCY.observe(latency)
        if request.url.path == "/transfer":
            TX_COUNTER.inc()
        logger.info(json.dumps({
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latencia_ms": int(latency*1000)
        }))
        response.headers["X-Trace-Id"] = trace_id
        return response
    except Exception as ex:
        TX_ERRORS.inc()
        logger.error(json.dumps({"trace_id": trace_id, "error": str(ex), "path": request.url.path}))
        raise

@app.get("/")
def health():
    return {"status": "SmartBancs UP", "version": "MVP"}

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type="text/plain")

# --- 3.1 TRANSFER CON DEADLOCK FIX + IDEMPOTENCY ---
@app.post("/transfer")
async def transfer(
    payload: dict,
    background_tasks: BackgroundTasks,
    request: Request,
    idempotency_key: str = Header(None, alias="idempotency-key")
):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    from_acc = payload.get("from")
    to_acc = payload.get("to")
    amount = float(payload.get("amount", 0))
    tx_id = str(uuid.uuid4())

    if not from_acc or not to_acc or amount <= 0:
        TX_ERRORS.inc()
        return {"status": "error", "message": "Datos inválidos"}

    if from_acc == to_acc:
        return {"status": "error", "message": "from == to no permitido"}

    # FIX DEADLOCK 3.5: ordenar IDs siempre menor->mayor antes de bloquear
    first, second = sorted([from_acc, to_acc])

    conn = get_conn()
    try:
        conn.autocommit = False
        cur = conn.cursor()

        # IDEMPOTENCY
        if idempotency_key:
            cur.execute("SELECT transaction_id FROM idempotency WHERE key = %s", (idempotency_key,))
            row = cur.fetchone()
            if row:
                conn.rollback()
                logger.info(json.dumps({"trace_id": trace_id, "idempotency": "hit", "key": idempotency_key}))
                return {"status": "ok", "transaction_id": row["transaction_id"], "message": "Ya procesada (idempotente)"}

        # BLOQUEO ORDENADO para evitar deadlock
        cur.execute("SELECT id, balance FROM accounts WHERE id IN (%s,%s) ORDER BY id FOR UPDATE", (first, second))
        accounts = {r["id"]: r["balance"] for r in cur.fetchall()}

        if from_acc not in accounts or to_acc not in accounts:
            conn.rollback()
            return {"status": "error", "message": "Cuenta no existe"}

        if accounts[from_acc] < amount:
            conn.rollback()
            return {"status": "error", "message": "Saldo insuficiente"}

        # MOVIMIENTO
        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_acc))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_acc))
        cur.execute("INSERT INTO transactions (id, from_acc, to_acc, amount, trace_id) VALUES (%s,%s,%s,%s,%s)",
                    (tx_id, from_acc, to_acc, amount, trace_id))

        if idempotency_key:
            cur.execute("INSERT INTO idempotency (key, transaction_id) VALUES (%s,%s)", (idempotency_key, tx_id))

        conn.commit()

        # 3.3 LLAMADA IA ASYNC DESPUES DEL COMMIT - NO BLOQUEA
        background_tasks.add_task(call_ia_async, tx_id, payload, trace_id)

        return {
            "status": "ok",
            "transaction_id": tx_id,
            "trace_id": trace_id,
            "message": f"Transferencia {from_acc}->{to_acc} ${amount} completada en <2s. IA en segundo plano."
        }

    except Exception as e:
        conn.rollback()
        TX_ERRORS.inc()
        logger.error(json.dumps({"trace_id": trace_id, "error": str(e), "operacion": "transfer"}))
        return {"status": "error", "message": str(e), "trace_id": trace_id}
    finally:
        conn.close()