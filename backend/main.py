import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from database import SessionLocal, init_db
from routers import admin, auth, requests, staff, triage
from services.routing_engine import check_sla


async def sla_loop():
    while True:
        await asyncio.sleep(config.SLA_CHECK_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            check_sla(db)
        except Exception as e:  # never let the background loop crash the app
            print("SLA check error:", e)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(sla_loop())
    yield
    task.cancel()


app = FastAPI(title="CampusCare API", description="AI-Powered Student Triage & Intelligent Support Routing", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, requests.router, triage.router, staff.router, admin.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"status": "ok", "ai_engine": "llm" if config.LLM_API_KEY else "deterministic-fallback", "demo_mode": config.DEMO_MODE}
