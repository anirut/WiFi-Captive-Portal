from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.pms.base import PMSAdapter
from app.pms.standalone import StandaloneAdapter
import logging

logger = logging.getLogger(__name__)
_active_adapter: PMSAdapter | None = None

async def load_adapter(db: AsyncSession) -> PMSAdapter:
    global _active_adapter
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record or record.type == PMSAdapterType.standalone:
        _active_adapter = StandaloneAdapter()
    else:
        # Plan 2 adds Opera, Cloudbeds, Mews, Custom
        logger.warning(f"Adapter type {record.type} not yet implemented, falling back to standalone")
        _active_adapter = StandaloneAdapter()
    return _active_adapter

def get_adapter() -> PMSAdapter:
    if _active_adapter is None:
        return StandaloneAdapter()
    return _active_adapter
