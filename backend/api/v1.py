from fastapi import APIRouter
from backend.routes.health import router as health_router
from backend.routes.telemetry import router as telemetry_router
from backend.routes.metrics import router as metrics_router
from backend.routes.funnel import router as funnel_router
from backend.routes.alerts import router as alerts_router
from backend.routes.analytics import router as analytics_router
from backend.routes.sales import router as sales_router
from backend.routes.events import router as events_router
from backend.routes.occupancy import router as occupancy_router
from backend.routes.analytics_legacy import router as analytics_legacy_router

api_v1_router = APIRouter()

# Register modular sub-routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(telemetry_router)
api_v1_router.include_router(metrics_router)
api_v1_router.include_router(funnel_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(sales_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(occupancy_router)
api_v1_router.include_router(analytics_legacy_router)
