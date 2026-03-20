from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionFactory
from app.network.session_manager import SessionManager
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_manager = SessionManager()

async def _expire_job():
    async with AsyncSessionFactory() as db:
        count = await _manager.expire_overdue_sessions(db)
        if count:
            logger.info(f"Scheduler expired {count} sessions")

def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.start()
    logger.info("Session expiry scheduler started")

def stop_scheduler():
    scheduler.shutdown()
