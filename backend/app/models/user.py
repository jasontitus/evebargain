"""Database tables for the logged-in player and their alert settings.

READING A MODEL CLASS
    Each class here becomes one database table. Each `mapped_column(...)`
    becomes one column in it. The line

        character_name: Mapped[str] = mapped_column(String(255), nullable=False)

    says three separate things:
      - `Mapped[str]`      what Python type you get when you read the attribute
      - `String(255)`      what SQL type the column has in the database
      - `nullable=False`   the database rejects a row with no value here

    `Mapped[int | None]` means the value may be missing; the `| None` is
    Python's way of writing "either an int or nothing", and it lines up with
    `nullable=True` on the same line.

WHY TWO TABLES
    A player's identity (who they are, their EVE tokens, where they are) changes
    for different reasons and at a different rate than their preferences. Keeping
    settings in their own table means the settings screen writes one small row
    rather than touching the row holding the access tokens.
"""

from datetime import datetime

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """One logged-in EVE character."""

    # The actual table name in the database. Without this, SQLAlchemy would not
    # know what to call it.
    __tablename__ = "users"

    # The primary key: a number the database assigns automatically, unique to
    # this row. Note this is *not* the EVE character id -- it is internal to
    # this app, and it is what other tables point at.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The player's real EVE id. `unique=True` means two rows cannot share one,
    # so logging in twice updates the existing row instead of duplicating it.
    character_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    character_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # EVE SSO credentials. The access token proves who we are to ESI but expires
    # after about 20 minutes; the refresh token is used to obtain a new one
    # without the player logging in again (see services/sso.py). Text rather
    # than String because these are long and have no fixed length.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Where the character currently is. Nullable because it is unknown until the
    # first location poll succeeds -- and several endpoints check for exactly
    # that, returning "Location not yet detected" rather than guessing.
    current_region_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_system_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # `default` is used when the row is created; `onupdate` re-runs on every
    # change. Note both are the *function* `datetime.utcnow`, not a call to it
    # -- passing `datetime.utcnow()` would freeze the moment this file was
    # imported and stamp every row with that same time.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Not a column: a link SQLAlchemy follows for you, so `user.config` fetches
    # the matching UserConfig row. `uselist=False` says there is at most one
    # (one-to-one, not one-to-many), and `back_populates` names the attribute on
    # the other side that points back here.
    config: Mapped["UserConfig"] = relationship(back_populates="user", uselist=False)


class UserConfig(Base):
    """One player's filtering and alerting preferences.

    Two separate sets of thresholds live here, and the distinction is the whole
    point:
      - the `discount_threshold` / `min_*` group decides what fills the table
      - the `alert_*` group decides what is worth a notification

    Sharing one set forced the dashboard to be as quiet as the alerts, or the
    alerts as noisy as the dashboard.
    """

    __tablename__ = "user_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ForeignKey ties this row to a User. `unique=True` enforces one config per
    # user -- without it, nothing would stop a second config row appearing and
    # silently shadowing the first.
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )

    # --- What appears in the deal table -------------------------------------
    # Stored as a fraction, not a percentage: 0.10 is 10% below the Jita price.
    discount_threshold: Mapped[float] = mapped_column(Float, default=0.10)

    # A list of category ids, stored as JSON text because SQLite has no array
    # type. Code that reads it must `json.loads(...)` first, and code that
    # writes it must `json.dumps(...)` -- see routers/config.py.
    tracked_category_ids: Mapped[str] = mapped_column(
        Text, default="[6,8,4,91]"
    )  # JSON array

    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Interrupting you is a higher bar than filling a table. These default
    # stricter than the browse filters above, so the dashboard can show
    # everything worth a look while only the genuinely good deals chime.
    alert_discount_threshold: Mapped[float] = mapped_column(Float, default=0.25)
    alert_min_profit_isk: Mapped[float] = mapped_column(Float, default=1000000.0)
    alert_min_volume: Mapped[int] = mapped_column(Integer, default=5)

    # Blueprint originals and copies share one type_id in EVE, but a copy is
    # worth a tiny fraction of an original. ESI's market endpoint cannot tell
    # them apart, so a cheap copy listed locally reads as a 90%+ discount
    # against an original's Jita price. They are real listings but not real
    # margins, and they crowd out everything else -- so they are excluded from
    # alerts by default. The table still shows them, flagged.
    alert_on_blueprints: Mapped[bool] = mapped_column(Boolean, default=False)

    # Minimum units on offer before a deal is worth showing. One unit at a
    # spectacular discount is usually bait or a misclick, not an opportunity.
    min_volume: Mapped[int] = mapped_column(Integer, default=5)
    # 1M ISK/unit excluded almost everything except ships and faction modules,
    # which is where routine ammo and module arbitrage lives.
    min_profit_isk: Mapped[float] = mapped_column(Float, default=50000.0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # The other half of the pair declared on User.config above.
    user: Mapped["User"] = relationship(back_populates="config")
