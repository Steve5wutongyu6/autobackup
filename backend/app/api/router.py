"""Top-level API router registration."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_backup import router as backup_router
from app.api.routes_cos import router as cos_router
from app.api.routes_logs import router as logs_router


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(cos_router)
api_router.include_router(backup_router)
api_router.include_router(logs_router)

