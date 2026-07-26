"""What the browser is told about the logged-in player.

Note what is *absent*: the User table also holds `access_token` and
`refresh_token`, and neither appears here. That is the point of having a
separate schema -- the response can only contain fields listed below, so
credentials cannot escape by accident.
"""

from pydantic import BaseModel


class UserResponse(BaseModel):
    character_id: int
    character_name: str
    current_region_id: int | None = None
    current_system_id: int | None = None
    current_region_name: str | None = None

    # Lets Pydantic build this straight from a SQLAlchemy User object by
    # reading matching attributes, instead of requiring a hand-written dict.
    model_config = {"from_attributes": True}
