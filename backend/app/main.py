"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import Base, engine, ensure_schema_compatibility, session_scope
from app.services.auth_service import AuthService
from app.services.log_service import LogService


configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Initialize database tables and bootstrap admin state on application startup.

    Args:
        _: FastAPI application instance, unused in the current startup flow.

    Returns:
        Async context manager yielding control to the ASGI runtime.
    """

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    with session_scope() as session:
        AuthService(session).ensure_bootstrap_admin()
        LogService(session).app_log("INFO", __name__, "API startup completed.")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/")
def health() -> dict[str, str]:
    """
    Return a simple API health payload.

    Returns:
        Service health status and application name.
    """

    return {"status": "ok", "app": settings.app_name}
