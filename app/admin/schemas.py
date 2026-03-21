import uuid
from datetime import datetime
from pydantic import BaseModel
from app.core.models import PMSAdapterType


class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"


class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict  # plaintext — encrypted before DB write


class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float = 0.0
    error: str | None = None
