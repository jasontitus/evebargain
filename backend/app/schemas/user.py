from pydantic import BaseModel


class UserResponse(BaseModel):
    character_id: int
    character_name: str
    current_region_id: int | None = None
    current_system_id: int | None = None
    current_region_name: str | None = None

    model_config = {"from_attributes": True}
