from pydantic import BaseModel

class ShelfEngagementItem(BaseModel):
    zone_id: str
    name: str
    total_stops: int
    attractive_stops: int
    attractiveness_index_pct: float
    hold_power_seconds: float
