from fastapi import APIRouter

from app.api.v1 import analytics, burn_scars, incidents, map, overview

router = APIRouter(prefix="/api/v1")
router.include_router(overview.router)
router.include_router(incidents.router)
router.include_router(burn_scars.router)
router.include_router(map.router)
router.include_router(analytics.router)
