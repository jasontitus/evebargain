"""A record of every notification raised, and the feed behind the UI.

WHY ALERTS ARE STORED AT ALL, NOT JUST PUSHED
    Two reasons. First, the alert feed in the sidebar needs history -- a
    notification you missed while looking at the game should still be there.
    Second, and less obvious, this table is what stops the app repeating
    itself: before raising an alert, the scanner checks whether this item in
    this region was already alerted recently, and skips it if so.

    Without that check the 300-second scan re-notified every standing deal on
    every pass, forever. See services/price_comparator.py::create_alerts_from_deals.

    The prices are copied in rather than looked up later on purpose: an alert
    is a record of what was true when it fired, and the market moves.
"""

from datetime import datetime

from sqlalchemy import Integer, Float, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    """One notification: this item, in this region, at this price, at this time."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    region_id: Mapped[int] = mapped_column(Integer, nullable=False)
    region_name: Mapped[str] = mapped_column(String(255), nullable=False)
    local_price: Mapped[float] = mapped_column(Float, nullable=False)
    jita_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, nullable=False)
    potential_profit: Mapped[float] = mapped_column(Float, nullable=False)
    # Both of these drive behaviour rather than just recording it: created_at
    # is compared against the cooldown window to suppress repeats, and
    # dismissed lets the feed hide something without deleting the history that
    # keeps it from being raised again.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
