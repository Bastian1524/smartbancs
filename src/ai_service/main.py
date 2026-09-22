from fastapi import FastAPI
import asyncio
app = FastAPI()
@app.post("/recommend")
async def recommend(data: dict):
    await asyncio.sleep(0.3)
    print(f"[IA] Recomendacion para {data['user_id']} trace={data.get('trace_id')}")
    return {"recommendation": "Mueve 10% a ahorro programado"}
@app.get("/")
def health():
    return {"status": "AI UP"}
