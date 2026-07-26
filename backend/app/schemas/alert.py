"""API shapes for the alert feed."""

from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    type_id: int
    type_name: str
    region_id: int
    region_name: str
    local_price: float
    jita_price: float
    discount_pct: float
    potential_profit: float
    created_at: datetime
    dismissed: bool

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int
