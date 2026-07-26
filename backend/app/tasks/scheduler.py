"""Background task scheduler for location polling and market updates."""

import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.user import User, UserConfig
from app.services import sso, location
from app.services.market_fetcher import update_market_cache, get_tracked_type_ids, update_jita_cache
from app.services.price_comparator import (
    find_arbitrage,
    create_alerts_from_deals,
    deals_worth_alerting,
)
from app.services.notification import ws_manager
from app.utils.eve_constants import THE_FORGE_REGION_ID

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def poll_user_location(user_id: int):
    """Poll a user's character location and trigger market scan on region change."""
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            return

        try:
            token = await sso.get_valid_token(user)
            system_id, region_id, changed = await location.detect_region_change(
                user.character_id, token, user.current_region_id
            )

            # Update user's current location
            user.current_system_id = system_id
            if changed:
                user.current_region_id = region_id
                region_name = await location.get_region_name(region_id)

                # Notify frontend of region change
                await ws_manager.send_region_change(user.id, region_id, region_name)

                # Trigger immediate market scan for the new region
                await scan_market_for_user(user.id, region_id)

            await db.commit()

        except Exception as e:
            logger.error(f"Location poll failed for user {user_id}: {e}")


async def scan_market_for_user(
    user_id: int, region_id: int | None = None, force: bool = False
):
    """Scan market data and find arbitrage opportunities for a user.

    force=True bypasses the cache-freshness guard for the *local* region only.
    A manual refresh should re-read the region the user is sitting in, but Jita
    is ~275 pages and is already kept current by the global refresh job, so
    repeated button presses must not drag it along.
    """
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            return

        config = await db.execute(
            select(UserConfig).where(UserConfig.user_id == user_id)
        )
        user_config = config.scalar_one_or_none()
        if not user_config:
            return

        target_region = region_id or user.current_region_id
        if not target_region or target_region == THE_FORGE_REGION_ID:
            return  # Skip if we're already in Jita's region

        try:
            tracked_categories = json.loads(user_config.tracked_category_ids)
            type_ids = await get_tracked_type_ids(db, tracked_categories)

            region_name = await location.get_region_name(target_region)

            def progress_for(phase: str, name: str):
                async def report(completed: int, total: int):
                    await ws_manager.send_progress(
                        user_id, phase, name, completed, total
                    )
                return report

            # Update both local region and Jita market data
            await update_market_cache(
                db,
                target_region,
                type_filter=type_ids,
                force=force,
                on_progress=progress_for("region", region_name),
            )
            await update_jita_cache(
                db,
                type_ids=type_ids,
                on_progress=progress_for("jita", "Jita"),
            )
            await ws_manager.send_progress(
                user_id, "compare", region_name, 1, 1, done=True
            )

            # Find arbitrage opportunities
            deals = await find_arbitrage(db, target_region, user_config)

            # The table shows everything past the browse filters; only the
            # stricter alert bar is allowed to make a noise.
            alertable = deals_worth_alerting(deals, user_config)
            # create_alerts_from_deals drops anything already raised inside the
            # cooldown, so this is genuinely new finds only.
            new_alerts = await create_alerts_from_deals(db, user_id, alertable)

            by_type = {(a.type_id, a.region_id) for a in new_alerts}
            for deal in deals:
                if (deal.type_id, deal.region_id) in by_type:
                    await ws_manager.send_alert(user_id, deal.model_dump())

            if deals:
                await ws_manager.send_market_update(
                    user_id, target_region, len(deals)
                )

            logger.info(
                f"Market scan complete for user {user_id}: {len(deals)} deals, "
                f"{len(alertable)} past the alert bar, "
                f"{len(new_alerts)} newly notified"
            )

        except Exception as e:
            logger.error(f"Market scan failed for user {user_id}: {e}")


async def refresh_jita_prices():
    """Periodically refresh Jita market data for all tracked types."""
    async with async_session() as db:
        # Get all unique tracked categories across all users
        result = await db.execute(select(UserConfig.tracked_category_ids))
        all_configs = result.scalars().all()

        all_categories = set()
        for cat_json in all_configs:
            all_categories.update(json.loads(cat_json))

        if not all_categories:
            return

        type_ids = await get_tracked_type_ids(db, list(all_categories))
        await update_jita_cache(db, type_ids=type_ids)
        logger.info(f"Jita price refresh complete: {len(type_ids)} types")


def setup_user_polling(user_id: int):
    """Set up periodic location polling for a user."""
    job_id = f"location_poll_{user_id}"

    # Remove existing job if any
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        poll_user_location,
        "interval",
        seconds=settings.location_poll_interval,
        args=[user_id],
        id=job_id,
        replace_existing=True,
        # Fire immediately rather than one interval from now. Until the first
        # poll lands the user has no current_region_id, and every market
        # endpoint rejects on it -- so the dashboard would 400 for the whole
        # first interval after login.
        next_run_time=datetime.now(timezone.utc),
    )
    logger.info(f"Started location polling for user {user_id}")


def setup_market_refresh(user_id: int):
    """Set up periodic market scanning for a user."""
    job_id = f"market_scan_{user_id}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        scan_market_for_user,
        "interval",
        seconds=settings.market_update_interval,
        args=[user_id],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"Started market scanning for user {user_id}")


def start_scheduler():
    """Start the background task scheduler."""
    # Global Jita price refresh job
    scheduler.add_job(
        refresh_jita_prices,
        "interval",
        seconds=settings.market_update_interval,
        id="jita_refresh",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Background scheduler stopped")
