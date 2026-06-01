from typing import List, Optional
from pydantic import BaseModel, Field

class EntryTelemetry(BaseModel):
    store_id: str
    camera_id: str
    track_id: int
    timestamp: str
    re_entry_detected: bool = False
    correlated_previous_track_id: Optional[int] = None

class ExitTelemetry(BaseModel):
    store_id: str
    camera_id: str
    track_id: int
    timestamp: str

class DwellTelemetry(BaseModel):
    store_id: str
    camera_id: str
    track_id: int
    zone_id: str
    entered_at: str
    exited_at: str
    dwell_time_seconds: float

class POSItemPayload(BaseModel):
    sku: str
    product_name: str
    category: str
    brand: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0.0)

class POSTransactionPayload(BaseModel):
    receipt_number: str
    total_amount: float = Field(..., ge=0.0)
    tax_amount: float = Field(0.0, ge=0.0)
    transaction_time: str
    payment_method: Optional[str] = "Credit"
    items: List[POSItemPayload]
