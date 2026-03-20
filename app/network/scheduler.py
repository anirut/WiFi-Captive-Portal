from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionFactory
from app.core.models import PMSAdapter as PMSAdapterModel
from app.network.session_manager import SessionManager
from app.pms.factory import get_adapter
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.mews import MewsAdapter
from app.pms.standalone import StandaloneAdapter
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_manager = SessionManager()


async def _expire_job():
    async with AsyncSessionFactory() as db:
        count = await _manager.expire_overdue_sessions(db)
        if count:
            logger.info(f"Scheduler expired {count} sessions")


async def _poll_checkouts_job():
    adapter = get_adapter()
    # Opera Cloud and Mews use webhooks; Standalone has no external PMS — no polling needed
    if isinstance(adapter, (OperaCloudAdapter, MewsAdapter, StandaloneAdapter)):
        return

    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
        )
        record = result.scalar_one_or_none()
        last_sync = (record.last_sync_at if record and record.last_sync_at
                     else datetime.now(timezone.utc) - timedelta(minutes=10))

        try:
            checkouts = await adapter.get_checkouts_since(last_sync)
        except Exception as e:
            logger.error(f"Checkout poll failed: {e} — skipping last_sync_at update")
            return

        for room in checkouts:
            count = await _manager.expire_sessions_for_room(db, room)
            if count:
                logger.info(f"Poll checkout: room={room}, expired {count} sessions")

        if record:
            record.last_sync_at = datetime.now(timezone.utc)
        await db.commit()


def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.add_job(_poll_checkouts_job, "interval", seconds=300, id="poll_checkouts")
    scheduler.start()
    logger.info("Scheduler started (expire: 60s, poll_checkouts: 300s)")


def stop_scheduler():
    scheduler.shutdown(wait=False)
