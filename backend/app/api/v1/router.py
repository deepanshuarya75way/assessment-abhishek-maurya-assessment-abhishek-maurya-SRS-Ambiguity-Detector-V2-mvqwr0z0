"""Aggregates all v1 endpoint routers. Add one ``include_router`` per resource."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_providers,
    analysis,
    auth,
    dashboard,
    documents,
    health,
    privacy,
    settings,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(analysis.router)
api_router.include_router(documents.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai_providers.router)
api_router.include_router(settings.router)
api_router.include_router(privacy.router)
