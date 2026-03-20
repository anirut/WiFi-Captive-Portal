import random
import string
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Voucher

class VoucherValidationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)

def generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    # Remove ambiguous chars (0, O, I, 1)
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(random.choices(chars, k=length))

async def validate_voucher(code: str, db: AsyncSession) -> Voucher:
    result = await db.execute(select(Voucher).where(Voucher.code == code))
    voucher = result.scalar_one_or_none()
    if not voucher:
        raise VoucherValidationError("invalid_code")
    if voucher.expires_at and voucher.expires_at < datetime.now(timezone.utc):
        raise VoucherValidationError("expired")
    if voucher.used_count >= voucher.max_uses:
        raise VoucherValidationError("no_uses_remaining")
    return voucher
