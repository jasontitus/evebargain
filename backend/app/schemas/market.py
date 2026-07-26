from pydantic import BaseModel


class ArbitrageResult(BaseModel):
    type_id: int
    type_name: str
    category_id: int | None = None
    category_name: str | None = None
    local_price: float
    jita_price: float
    discount_pct: float
    profit_per_unit: float
    volume_available: int
    region_id: int
    region_name: str
    # Jumps from the character, set only by the nearby scan.
    jumps: int | None = None


class MarketDealResponse(BaseModel):
    deals: list[ArbitrageResult]
    region_id: int
    region_name: str
    last_updated: str | None = None
    # True when these deals are for a region the user picked from the dropdown
    # rather than the one their character is actually sitting in.
    is_browsed: bool = False


class RegionSummary(BaseModel):
    region_id: int
    name: str
    # Jumps from the character's current system. None when not measured, or
    # when no route exists under the requested safety flag.
    jumps: int | None = None


class RegionListResponse(BaseModel):
    regions: list[RegionSummary]
    current_region_id: int | None = None


class NearbyDealsResponse(BaseModel):
    deals: list[ArbitrageResult]
    regions_scanned: int
    regions_in_range: int
    max_jumps: int
    flag: str
    # Set when the scan was capped, so the UI can say so rather than implying
    # the result is complete.
    truncated: bool = False
