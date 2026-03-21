import uuid
from datetime import datetime
from pydantic import BaseModel
from app.core.models import PMSAdapterType, VoucherType


class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"


class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict  # plaintext — encrypted before DB write
    webhook_secret: str | None = None


class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float = 0.0
    error: str | None = None


class VoucherCreate(BaseModel):
    type: VoucherType
    duration_minutes: int | None = None
    data_limit_mb: int | None = None
    max_devices: int = 1
    max_uses: int = 1
    expires_at: datetime | None = None


class VoucherResponse(BaseModel):
    id: uuid.UUID
    code: str
    type: VoucherType
    duration_minutes: int | None
    data_limit_mb: int | None
    max_devices: int
    max_uses: int
    used_count: int
    expires_at: datetime | None
    created_by: uuid.UUID
