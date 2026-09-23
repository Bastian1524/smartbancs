import pandas as pd
import asyncpg, os, asyncio, json, logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bancs-etl")

async def run():
    dsn = os.getenv("DATABASE_URL", "postgresql://bancs:bancs123@db:5432/smartbancs")
    pool = await asyncpg.create_pool(dsn=dsn)
    try:
        # Soporta ambos esquemas: processed=false O status=PENDING
        rows = await pool.fetch("SELECT id, payload FROM outbox_events WHERE processed=false OR status='PENDING' LIMIT 5000")
        if not rows:
            logger.info("ETL: Nada que procesar - Bancs no saturado (OK)")
            return
        data = []
        ids = []
        for r in rows:
            p = r['payload']
            if isinstance(p, str):
                p = json.loads(p)
            data.append(p)
            ids.append(r['id'])
        df = pd.DataFrame(data)
        os.makedirs("tmp", exist_ok=True)
        df.to_json("tmp/bancs_para_ia.jsonl", orient="records", lines=True)
        df.to_parquet("tmp/bancs_para_ia.parquet", engine="pyarrow", compression="snappy")
        await pool.execute("UPDATE outbox_events SET processed=true, status='PROCESSED' WHERE id = ANY($1::uuid[])", ids)
        logger.info(f"ETL OK: {len(df)} eventos -> JSONL + Parquet - Bancs no saturado")
        print(f"ETL OK: {len(df)} eventos -> JSONL + Parquet optimizado para IA")
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(run())
