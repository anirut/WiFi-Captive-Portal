from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionFactory
from app.core.models import PMSAdapter as PMSAdapterModel
from app.core.models import Session as SessionModel, SessionStatus, VoucherType, UsageSnapshot
from app.network.session_manager import SessionManager
from app.network import tc
from app.pms.factory import get_adapter
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.mews import MewsAdapter
from app.pms.standalone import StandaloneAdapter
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
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


async def _bytes_job():
    """Update bytes_up/bytes_down from tc stats; enforce data-based voucher quotas."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(SessionModel)
            .options(selectinload(SessionModel.voucher))
            .where(SessionModel.status == SessionStatus.active)
        )
        sessions = result.scalars().all()
        for s in sessions:
            up, down = tc.get_bytes(s.ip_address)
            s.bytes_up = up
            s.bytes_down = down
            if s.voucher_id and s.voucher and s.voucher.type == VoucherType.data:
                quota_bytes = (s.voucher.data_limit_mb or 0) * 1024 * 1024
                if quota_bytes > 0 and down >= quota_bytes:
                    await _manager.expire_session(db, s, SessionStatus.expired)
        await db.commit()


async def _analytics_snapshot_job():
    """Write hourly usage snapshot for analytics charts."""
    async with AsyncSessionFactory() as db:
        snapshot_at = datetime.now(timezone.utc)

        count_result = await db.execute(
            select(func.count()).where(SessionModel.status == SessionStatus.active)
        )
        active_sessions = count_result.scalar_one() or 0

        sum_result = await db.execute(
            select(func.coalesce(func.sum(SessionModel.bytes_up), 0),
                   func.coalesce(func.sum(SessionModel.bytes_down), 0))
            .where(SessionModel.status == SessionStatus.active)
        )
        total_up, total_down = sum_result.one()

        voucher_result = await db.execute(
            select(func.count()).where(
                SessionModel.voucher_id.isnot(None),
                SessionModel.connected_at >= snapshot_at - timedelta(hours=1),
            )
        )
        voucher_uses = voucher_result.scalar_one() or 0

        snapshot = UsageSnapshot(
            snapshot_at=snapshot_at,
            active_sessions=active_sessions,
            total_bytes_up=total_up,
            total_bytes_down=total_down,
            voucher_uses=voucher_uses,
        )
        db.add(snapshot)
        await db.commit()
        logger.info(f"Analytics snapshot: {active_sessions} sessions, {total_down} bytes down")


def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.add_job(_bytes_job, "interval", seconds=60, id="update_bytes")
    scheduler.add_job(_poll_checkouts_job, "interval", seconds=300, id="poll_checkouts")
    scheduler.add_job(_analytics_snapshot_job, "interval", seconds=3600, id="analytics_snapshot")
    scheduler.start()
    logger.info("Scheduler started (expire: 60s, bytes: 60s, poll: 300s, analytics: 3600s)")


def stop_scheduler():
    scheduler.shutdown(wait=False)
