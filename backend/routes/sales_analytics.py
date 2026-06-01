from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import os

from backend.database.connection import get_db
from backend.services.sales_analytics import SalesAnalyticsService
from backend.utils.seeder import seed_database_from_csv
from backend.schemas.sales import (
    BrandPerformanceItem,
    CategoryPerformanceItem,
    SalesProductPerformanceResponse,
    RevenueAnalysisResponse,
    ConversionAnalysisResponse
)

router = APIRouter(prefix="/sales-analytics", tags=["Retail Dataset Sales Analytics"])

@router.get("/brands", response_model=List[BrandPerformanceItem])
def get_brand_performance(db: Session = Depends(get_db)):
    """Provides sales volume, total revenues, and private label shares across product brands."""
    service = SalesAnalyticsService(db)
    return service.get_brand_performance()

@router.get("/categories", response_model=List[CategoryPerformanceItem])
def get_category_performance(db: Session = Depends(get_db)):
    """Provides sales volumes, collected taxes, and peak purchasing hours grouped by category."""
    service = SalesAnalyticsService(db)
    return service.get_category_performance()

@router.get("/products", response_model=SalesProductPerformanceResponse)
def get_product_performance(db: Session = Depends(get_db)):
    """Provides top-moving product ranges by volume/revenue alongside slowest-moving inventory items."""
    service = SalesAnalyticsService(db)
    return service.get_product_performance()

@router.get("/revenue", response_model=RevenueAnalysisResponse)
def get_revenue_analysis(db: Session = Depends(get_db)):
    """Provides overall GMV, True realized realized revenue NMV, taxes, and hourly sales splits."""
    service = SalesAnalyticsService(db)
    return service.get_revenue_analysis()

@router.get("/conversion", response_model=ConversionAnalysisResponse)
def get_conversion_analysis(db: Session = Depends(get_db)):
    """Provides promotional campaign ratios and private label vs national brand split funnels."""
    service = SalesAnalyticsService(db)
    return service.get_conversion_analysis()

@router.post("/seed", status_code=201)
def seed_dataset(
    csv_path: Optional[str] = Query(None, description="Custom path to the CSV file (defaults to data/Brigade_Bangalore...)"),
    db: Session = Depends(get_db)
):
    """Utility endpoint to trigger parsing and seeding of the uploaded sales CSV file into database rows."""
    if not csv_path:
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
        
    if not os.path.exists(csv_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Target retail dataset file not found at path: {csv_path}. Please verify placement."
        )

    try:
        item_count = seed_database_from_csv(db, csv_path)
        return {
            "success": True, 
            "message": f"Successfully parsed retail sales dataset and seeded {item_count} order item records into SQL."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database seeding execution failed: {str(e)}")
