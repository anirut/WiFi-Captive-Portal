import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from app.voucher.generator import generate_code, validate_voucher, VoucherValidationError

def test_generate_code_format():
    code = generate_code()
    assert len(code) == 8
    assert code.isupper()
    assert code.isalnum()

def test_generate_code_unique():
    codes = {generate_code() for _ in range(100)}
    assert len(codes) == 100

@pytest.mark.asyncio
async def test_validate_valid_voucher():
    mock_db = AsyncMock()
    mock_voucher = MagicMock()
    mock_voucher.used_count = 0
    mock_voucher.max_uses = 5
    mock_voucher.expires_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_voucher
    mock_db.execute = AsyncMock(return_value=mock_result)

    voucher = await validate_voucher("ABCD1234", db=mock_db)
    assert voucher == mock_voucher

@pytest.mark.asyncio
async def test_validate_nonexistent_voucher_raises():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(VoucherValidationError, match="invalid_code"):
        await validate_voucher("INVALID1", db=mock_db)

@pytest.mark.asyncio
async def test_validate_exhausted_voucher_raises():
    mock_db = AsyncMock()
    mock_voucher = MagicMock()
    mock_voucher.used_count = 5
    mock_voucher.max_uses = 5
    mock_voucher.expires_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_voucher
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(VoucherValidationError, match="no_uses_remaining"):
        await validate_voucher("USED1234", db=mock_db)

@pytest.mark.asyncio
async def test_validate_expired_voucher_raises():
    mock_db = AsyncMock()
    mock_voucher = MagicMock()
    mock_voucher.used_count = 0
    mock_voucher.max_uses = 5
    mock_voucher.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_voucher
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(VoucherValidationError, match="expired"):
        await validate_voucher("EXPIREDX", db=mock_db)
