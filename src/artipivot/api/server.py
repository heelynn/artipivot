"""FastAPI server — REST API entry point with middleware."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from artipivot.api.admin import admin_router
from artipivot.api.chat import chat_router

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_WEB_DIST = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ArtiPivot",
        version="0.5.0",
        description="Production-grade multi-agent framework API",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Trace ID middleware
    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        tid = request.headers.get("X-Trace-ID", uuid.uuid4().hex[:16])
        trace_id_var.set(tid)
        response = await call_next(request)
        response.headers["X-Trace-ID"] = tid
        return response

    # Routers
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/admin")

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Serve frontend static files (production mode)
    if _WEB_DIST.is_dir():
        from fastapi.staticfiles import StaticFiles

        # Serve static assets (js, css, images, etc.)
        app.mount("/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="static-assets")

        @app.middleware("http")
        async def spa_middleware(request: Request, call_next):
            """Serve index.html for browser navigation (text/html) requests.

            API calls from fetch/XHR send Accept: application/json — always let these through.
            Browser navigation sends Accept: text/html — serve index.html for SPA routing.
            """
            accept = request.headers.get("accept", "")
            path = request.url.path.lstrip("/")

            # Always let API calls through (fetch/XHR with Accept: application/json)
            if request.method == "GET" and "application/json" in accept:
                return await call_next(request)

            # Serve static files first
            if request.method == "GET" and path:
                file_path = _WEB_DIST / path
                if file_path.is_file():
                    return FileResponse(file_path)

            # Serve index.html for browser navigation (SPA client-side routing)
            if (
                request.method == "GET"
                and "text/html" in accept
            ):
                return FileResponse(_WEB_DIST / "index.html")

            return await call_next(request)

    return app
