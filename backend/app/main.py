from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    approvals,
    cases,
    contractors,
    costs,
    documents,
    field_updates,
    insights,
    messaging,
    metrics,
    notes,
    notifications,
    observations,
    overview,
    properties,
    reports,
    search,
    tenants,
    voice,
)
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

    # Nothing is seeded on boot. The application starts against whatever
    # is in the database -- including an empty one, which is a legitimate
    # state every screen renders an onboarding empty state for. A sample
    # portfolio is available on demand via `python -m app.seed`, and
    # illustrative closed history via `python -m app.archive --apply`.

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
    # DELETE is real (demo.py's delete-ticket endpoint) and PATCH/PUT cost
    # nothing to allow -- a missing method here fails silently at the
    # browser's CORS preflight, never reaching the handler or its tests
    # (ASGITransport doesn't preflight), so it's invisible until clicked
    # live from an actual cross-origin dev server.
    allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(cases.router)
app.include_router(observations.router)
app.include_router(field_updates.router)
app.include_router(approvals.router)
app.include_router(metrics.router)
app.include_router(notifications.router)
app.include_router(overview.router)
app.include_router(properties.router)
app.include_router(contractors.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(notes.router)
app.include_router(costs.router)
app.include_router(messaging.router)
app.include_router(insights.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(voice.router)
app.include_router(voice.webhook_router)
app.include_router(voice.tools_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


class SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for unknown paths.

    The frontend is a client-side-routed SPA served as a static build, so
    `/properties/<uuid>` exists only in the browser's router -- there is no
    such file on disk. Plain StaticFiles answers 404 for it, which is
    invisible while navigating in-app (the router handles the click) and
    breaks the moment anyone reloads the page or opens a shared deep link.
    Anything under /api, /webhooks or /integrations is left alone so a
    genuine missing endpoint still reports itself as missing instead of
    silently returning HTML.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 404 and not path.startswith(
            ("api/", "webhooks/", "integrations/", "assets/")
        ):
            return await super().get_response("index.html", scope)
        return response


if FRONTEND_DIST.is_dir():
    app.mount("/", SpaStaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
