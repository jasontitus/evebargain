from pydantic import BaseModel, Field


class UserConfigResponse(BaseModel):
    discount_threshold: float
    tracked_category_ids: list[int]
    notifications_enabled: bool
    sound_enabled: bool
    min_volume: int
    min_profit_isk: float
    # Alerting is a separate, stricter bar than what the table shows.
    alert_discount_threshold: float
    alert_min_profit_isk: float
    alert_min_volume: int

    model_config = {"from_attributes": True}


class UserConfigUpdate(BaseModel):
    discount_threshold: float | None = Field(None, ge=0.01, le=0.90)
    tracked_category_ids: list[int] | None = None
    notifications_enabled: bool | None = None
    sound_enabled: bool | None = None
    min_volume: int | None = Field(None, ge=1)
    min_profit_isk: float | None = Field(None, ge=0)
    alert_discount_threshold: float | None = Field(None, ge=0.01, le=0.90)
    alert_min_profit_isk: float | None = Field(None, ge=0)
    alert_min_volume: int | None = Field(None, ge=1)


class CategoryInfo(BaseModel):
    category_id: int
    name: str
