"""Alerting is a stricter, deduplicated subset of what the table shows."""

from datetime import datetime, timedelta

import pytest

from app.models.alert import Alert
from app.models.user import User, UserConfig
from app.schemas.market import ArbitrageResult
from app.utils.eve_constants import CATEGORY_BLUEPRINTS
from app.services.price_comparator import (
    ALERT_COOLDOWN,
    create_alerts_from_deals,
    deals_worth_alerting,
)


def _deal(type_id=34, discount=0.30, profit=2_000_000.0, volume=100, region=10000052,
          category=6):
    return ArbitrageResult(
        type_id=type_id,
        type_name=f"Item {type_id}",
        category_id=category,
        local_price=100.0,
        jita_price=200.0,
        discount_pct=discount,
        profit_per_unit=profit,
        volume_available=volume,
        region_id=region,
        region_name="Kador",
    )


def _config(**overrides):
    cfg = UserConfig(
        user_id=1,
        discount_threshold=0.10,
        tracked_category_ids="[6]",
        min_volume=5,
        min_profit_isk=50_000.0,
        alert_discount_threshold=0.25,
        alert_min_profit_isk=1_000_000.0,
        alert_min_volume=5,
        alert_on_blueprints=False,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_alert_bar_is_stricter_than_the_browse_bar():
    """A deal good enough for the table need not be worth a notification."""
    browsable = _deal(discount=0.12, profit=60_000.0)
    assert deals_worth_alerting([browsable], _config()) == []


def test_a_genuinely_good_deal_passes():
    assert len(deals_worth_alerting([_deal()], _config())) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"discount": 0.20},          # under the alert discount
        {"profit": 500_000.0},       # under the alert profit
        {"volume": 2},               # under the alert volume
    ],
)
def test_each_alert_threshold_can_reject_alone(kwargs):
    assert deals_worth_alerting([_deal(**kwargs)], _config()) == []


async def _seed_user(db):
    user = User(character_id=96347599, character_name="Test", access_token="x",
                refresh_token="y", token_expires=datetime.utcnow() + timedelta(hours=1))
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_the_same_deal_is_not_re_alerted_within_the_cooldown(db_session):
    """Scans run every 300s and the market barely moves between them, so
    without this the same item notified over and over, forever."""
    user = await _seed_user(db_session)

    first = await create_alerts_from_deals(db_session, user.id, [_deal()])
    assert len(first) == 1

    second = await create_alerts_from_deals(db_session, user.id, [_deal()])
    assert second == []


@pytest.mark.asyncio
async def test_the_deal_alerts_again_once_the_cooldown_lapses(db_session):
    user = await _seed_user(db_session)

    stale = Alert(
        user_id=user.id,
        type_id=34,
        type_name="Item 34",
        region_id=10000052,
        region_name="Kador",
        local_price=100.0,
        jita_price=200.0,
        discount_pct=0.30,
        potential_profit=2_000_000.0,
        created_at=datetime.utcnow() - ALERT_COOLDOWN - timedelta(minutes=5),
    )
    db_session.add(stale)
    await db_session.commit()

    again = await create_alerts_from_deals(db_session, user.id, [_deal()])
    assert len(again) == 1


@pytest.mark.asyncio
async def test_the_same_item_in_a_different_region_still_alerts(db_session):
    user = await _seed_user(db_session)

    await create_alerts_from_deals(db_session, user.id, [_deal(region=10000052)])
    other = await create_alerts_from_deals(db_session, user.id, [_deal(region=10000043)])

    assert len(other) == 1


@pytest.mark.asyncio
async def test_duplicates_inside_one_batch_collapse(db_session):
    user = await _seed_user(db_session)

    created = await create_alerts_from_deals(
        db_session, user.id, [_deal(), _deal(), _deal()]
    )

    assert len(created) == 1


def test_blueprints_do_not_alert_by_default():
    """BPOs and BPCs share a type_id, so a cheap copy reads as a 90%+ discount
    against an original's Jita price. Real listing, fake margin."""
    blueprint = _deal(category=CATEGORY_BLUEPRINTS, discount=0.95)
    assert deals_worth_alerting([blueprint], _config()) == []


def test_blueprints_alert_when_explicitly_enabled():
    blueprint = _deal(category=CATEGORY_BLUEPRINTS, discount=0.95)
    assert len(deals_worth_alerting([blueprint], _config(alert_on_blueprints=True))) == 1


def test_the_blueprint_rule_does_not_touch_other_categories():
    ship = _deal(category=6, discount=0.95)
    assert len(deals_worth_alerting([ship], _config())) == 1
