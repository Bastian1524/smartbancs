import asyncio, httpx, uuid
async def send(i):
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8000/transfer", 
            headers={"idempotency-key": str(uuid.uuid4())},
            json={"from":"ACC001","to":"ACC002","amount":1})
        return r.text

async def main():
    results = await asyncio.gather(*[send(i) for i in range(30)])
    print(f"{len(results)} transferencias enviadas")

asyncio.run(main())
