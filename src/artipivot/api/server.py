"""FastAPI server — REST API entry point with middleware."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from artipivot.api.admin import admin_router
from artipivot.api.chat import chat_router

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


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

    return app
