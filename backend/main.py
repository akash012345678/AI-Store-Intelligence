import os
import yaml
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from backend.database.connection import init_db, Base, engine
from backend.api.v1 import api_v1_router
from backend.middleware.logging import LoggingMiddleware
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.utils.exceptions import (
    PurpleInsightException,
    system_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PurpleInsight.App")

def create_app(config_path: str = "backend/config/backend_config.yaml") -> FastAPI:
    """FastAPI Application Factory configuring middlewares, routers, database engines, and exception mapping."""
    
    # 1. Load backend configuration
    database_url = os.getenv("DATABASE_URL", "sqlite:///store_intelligence.db")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    rate_limit_rpm = 120
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f)
                if not os.getenv("DATABASE_URL"):
                    database_url = config_data.get("database_url", database_url)
                rate_limit_rpm = config_data.get("rate_limit_rpm", rate_limit_rpm)
            logger.info("Loaded backend configuration successfully.")
        except Exception as e:
            logger.error(f"Failed to parse configuration: {e}. Using defaults.")

    # 2. Database engine initialization
    init_db(database_url)
    
    # Auto-create tables (Alembic is typically used, but auto-create guarantees instant local setup)
    try:
        from backend.database.connection import engine
        Base.metadata.create_all(bind=engine)
        logger.info("Relational database tables checked/created successfully.")
        
        # Auto-seed the uploaded sales dataset if tables are empty
        from sqlalchemy.orm import sessionmaker
        from backend.models.sales import SalesStore
        from backend.utils.seeder import seed_database_from_csv
        
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            if session.query(SalesStore).count() == 0:
                csv_path = "c:\\Users\\Maha Monisha\\OneDrive\\Desktop\\purple\\data\\Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
                if not os.path.exists(csv_path):
                    alternatives = [
                        "data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv",
                        "../data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv",
                        "/app/data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
                    ]
                    for alt in alternatives:
                        if os.path.exists(alt):
                            csv_path = alt
                            break
                            
                if os.path.exists(csv_path):
                    logger.info(f"Auto-seeding retail sales dataset from CSV at: {csv_path}...")
                    seed_database_from_csv(session, csv_path)
                else:
                    logger.warning(f"Sales dataset CSV not found at paths. Skipping seeder.")
        except Exception as se:
            logger.error(f"Auto-seeding failed: {se}")
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Database table generation failed: {e}")


    # 3. Create FastAPI app metadata
    app = FastAPI(
        title="PurpleInsight AI Store Intelligence API Layer",
        description=(
            "Enterprise-grade store analytics and computer vision metadata compiler. "
            "Integrates CCTV camera counts, dwell trajectories, and POS sales "
            "to expose shopper traffic, layout heatmaps, queue crowding, and conversions."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    # 4. Configure Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Expand in production to specific frontend domains
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Request ID tracing context middleware
    from backend.middleware.request_context import RequestContextMiddleware
    app.add_middleware(RequestContextMiddleware)
    
    # IP-based rate limiting (120 requests/minute default)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=rate_limit_rpm)
    
    # Advanced logging & latency tracker
    app.add_middleware(LoggingMiddleware)

    # 5. Wire Exception Handlers
    from backend.middleware.exception_handler import register_exception_handlers
    register_exception_handlers(app)


    # 6. Mount APIRouter
    app.include_router(api_v1_router, prefix="/api/v1")

    # Serve simplified root redirecting to Swagger UI
    @app.get("/", include_in_schema=False)
    def root_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")

    logger.info("FastAPI Application setup finished successfully.")
    return app

app = create_app()
