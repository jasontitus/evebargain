from pydantic import BaseModel


class ArbitrageResult(BaseModel):
    type_id: int
    type_name: str
    local_price: float
    jita_price: float
    discount_pct: float
    profit_per_unit: float
    volume_available: int
    region_id: int
    region_name: str


class MarketDealResponse(BaseModel):
    deals: list[ArbitrageResult]
    region_id: int
    region_name: str
    last_updated: str | None = None
