from fastapi import FastAPI
import asyncio, random, time
app = FastAPI()

@app.post("/recomendar")
async def recomendar(payload: dict):
    await asyncio.sleep(0.8) # simula inferencia
    score = random.random()
    return {
        "transaction_id": payload.get("transaction_id"),
        "recomendacion": "Ahorro" if score > 0.5 else "Inversion",
        "confianza": score
    }