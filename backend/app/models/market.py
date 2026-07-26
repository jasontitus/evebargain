"""A local snapshot of market prices, one row per item per region.

WHY CACHE AT ALL
    Every price comparison needs two numbers: what an item costs here, and what
    it costs in Jita. Asking ESI for those live, per comparison, would be
    thousands of requests to answer one screen. Instead the app pulls a whole
    region's sell orders at once, reduces them to "cheapest price per item", and
    stores the result here. Comparisons then run entirely against the database.

    ESI serves market pages from a ~300 second cache anyway, so data fresher
    than that does not exist to be fetched -- see `fetched_at` below.
"""

from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketCache(Base):
    """The cheapest sell price for one item type in one region."""

    __tablename__ = "market_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # `index=True` tells the database to build a lookup structure for this
    # column. Queries filter on region_id and join on type_id constantly, and
    # without indexes each of those would scan every row in the table.
    region_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # The lowest asking price found. Nullable because a region may have no
    # sellers for an item at all -- which is different from a price of zero, and
    # the comparison query filters these out explicitly.
    lowest_sell: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Declared for completeness; this app only compares sell orders, since you
    # buy at the ask price. Left in place for a future buy-side feature.
    highest_buy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # How many separate orders, and how many units in total, back that price.
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    volume_remain: Mapped[int] = mapped_column(Integer, default=0)

    # When this row was written. This is what the cache-freshness guard reads to
    # decide whether a refetch would return anything new -- see
    # services/market_fetcher.py::is_cache_fresh.
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Table-level rules, as opposed to the per-column ones above. This one says
    # a given item may appear only once per region, which is what lets the
    # fetcher "upsert": insert a row, or overwrite it if that pair already
    # exists, in a single statement.
    #
    # (The trailing comma matters. `(x)` is just `x` in parentheses; `(x,)` is a
    # one-item tuple, which is what SQLAlchemy expects here.)
    __table_args__ = (
        UniqueConstraint("region_id", "type_id", name="uq_region_type"),
    )
