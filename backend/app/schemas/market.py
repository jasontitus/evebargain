"""API shapes for market data -- what the JSON going to the browser looks like.

SCHEMAS VS MODELS: THE THING TO UNDERSTAND FIRST
    There are two families of classes in this project that look similar and do
    completely different jobs.

      models/  are SQLAlchemy classes. One class = one database table. They
               describe how data is *stored*.

      schemas/ are Pydantic classes (like the ones below). They describe how
               data is *sent and received over HTTP*, and they validate it.

    They are kept apart deliberately. The database row for a user holds their
    EVE access token; the JSON sent to the browser must not. Because the API
    response is built from a schema listing exactly which fields exist, a
    secret cannot leak just because someone added a column.

WHAT PYDANTIC DOES FOR YOU
    FastAPI reads these classes and, for free:
      - converts the object to JSON on the way out
      - validates and converts incoming JSON on the way in, rejecting bad
        requests with a clear 422 error before your code ever runs
      - documents every field at /docs

    `field: int` is required. `field: int | None = None` is optional and
    defaults to nothing. That is the whole syntax.
"""

from pydantic import BaseModel


class ArbitrageResult(BaseModel):
    """One buying opportunity: an item cheaper here than it is in Jita."""

    type_id: int
    type_name: str
    category_id: int | None = None
    category_name: str | None = None
    local_price: float
    jita_price: float
    # A fraction, not a percentage: 0.25 means 25% below the Jita price. The
    # frontend multiplies by 100 for display.
    discount_pct: float
    profit_per_unit: float
    volume_available: int
    region_id: int
    region_name: str
    # Jumps from the character, set only by the nearby scan.
    jumps: int | None = None
    # Packaged cubic metres per unit, and profit per cubic metre. Cargo space
    # is the binding constraint on a haul, so ISK/m3 ranks deals better than
    # ISK/unit: a 40% discount on something bulky can be worth less per trip
    # than a 12% discount on something dense.
    volume_m3: float | None = None
    isk_per_m3: float | None = None


class MarketDealResponse(BaseModel):
    """The reply to "what deals are there in this one region?"."""

    deals: list[ArbitrageResult]
    region_id: int
    region_name: str
    last_updated: str | None = None
    # True when these deals are for a region the user picked from the dropdown
    # rather than the one their character is actually sitting in.
    is_browsed: bool = False


class RegionSummary(BaseModel):
    """One entry in the region dropdown."""

    region_id: int
    name: str
    # Jumps from the character's current system. None when not measured, or
    # when no route exists under the requested safety flag.
    jumps: int | None = None


class RegionListResponse(BaseModel):
    """Every region worth offering, plus where the player currently is."""

    regions: list[RegionSummary]
    current_region_id: int | None = None


class NearbyDealsResponse(BaseModel):
    """The reply to "what deals are within N jumps?".

    Carries counts as well as deals so the UI can distinguish "scanned
    everything in range" from "scanned as much as the cap allowed".
    """

    deals: list[ArbitrageResult]
    regions_scanned: int
    regions_in_range: int
    max_jumps: int
    flag: str
    # Set when the scan was capped, so the UI can say so rather than implying
    # the result is complete.
    truncated: bool = False
