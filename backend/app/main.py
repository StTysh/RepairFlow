from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import approvals, cases, demo, metrics, observations, voice
from app.api.errors import register_error_handlers
from app.config import get_settings
from app.db import create_all, dispose_engine
from app.orchestration.worker import run_worker_loop

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend-fixi" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    await create_all()

    from app.seed import seed as seed_demo_data

    await seed_demo_data()  # idempotent: no-ops if the demo property already exists

    from app.agents.coordinator import build_coordinator

    coordinator = build_coordinator(settings)

    research_adapter = None
    if settings.tavily_live:
        from app.integrations.tavily import TavilyResearchAdapter

        research_adapter = TavilyResearchAdapter()

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(
        run_worker_loop(
            coordinator, stop_event=stop_event, elevenlabs_configured=settings.elevenlabs_live,
            research_adapter=research_adapter,
        )
    )
    app.state.coordinator = coordinator
    app.state.research_adapter = research_adapter

    yield

    stop_event.set()
    await worker_task
    await dispose_engine()


app = FastAPI(title="Fixi", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(cases.router)
app.include_router(observations.router)
app.include_router(approvals.router)
app.include_router(demo.router)
app.include_router(metrics.router)
app.include_router(voice.router)
app.include_router(voice.webhook_router)
app.include_router(voice.tools_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
