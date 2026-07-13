from fastapi import FastAPI
app = FastAPI()

@app.get("/api/v1/cn/health")
async def health():
    return {"status": "ok"}
