import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.core.encryption import decrypt_config
from app.pms.base import PMSAdapter
from app.pms.standalone import StandaloneAdapter
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.opera_fias import OperaFIASAdapter
from app.pms.cloudbeds import CloudbedsAdapter
from app.pms.mews import MewsAdapter
from app.pms.custom import CustomAdapter

logger = logging.getLogger(__name__)

_active_adapter: PMSAdapter | None = None

ADAPTER_MAP = {
    PMSAdapterType.opera_cloud: OperaCloudAdapter,
    PMSAdapterType.opera_fias: OperaFIASAdapter,
    PMSAdapterType.cloudbeds: CloudbedsAdapter,
    PMSAdapterType.mews: MewsAdapter,
    PMSAdapterType.custom: CustomAdapter,
    PMSAdapterType.standalone: StandaloneAdapter,
}


async def load_adapter(db: AsyncSession) -> PMSAdapter:
    global _active_adapter
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()

    if not record or record.type == PMSAdapterType.standalone or record.type not in ADAPTER_MAP:
        _active_adapter = StandaloneAdapter()
        return _active_adapter

    config = decrypt_config(record.config_encrypted) if record.config_encrypted else {}
    adapter_class = ADAPTER_MAP[record.type]
    adapter = adapter_class(config)

    # FIAS needs TCP connection established before health check
    if isinstance(adapter, OperaFIASAdapter):
        try:
            await adapter.connect()
        except Exception as e:
            logger.error(f"FIAS connect failed: {e}")

    # Health check with retry (3 attempts, 500ms backoff)
    for attempt in range(3):
        if await adapter.health_check():
            break
        if attempt < 2:
            logger.warning(f"Adapter health check failed (attempt {attempt + 1}/3), retrying...")
            await asyncio.sleep(0.5)
    else:
        logger.error(f"Adapter {record.type.value} health check failed after 3 attempts — portal will return pms_unavailable")

    _active_adapter = adapter
    return _active_adapter


def get_adapter() -> PMSAdapter:
    if _active_adapter is None:
        return StandaloneAdapter()
    return _active_adapter
