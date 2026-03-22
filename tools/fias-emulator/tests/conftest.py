"""
Pytest configuration and fixtures for FIAS Emulator tests.
"""

import os
import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """Set test environment variables before any app imports."""
    # Use in-memory SQLite for tests
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["AUTH_KEY"] = "test-key"
    yield
    # Cleanup
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("AUTH_KEY", None)


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh database session for each test with isolated tables."""
    from emulator.models import Base

    # Create a new engine for each test to ensure isolation
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    # Cleanup
    await engine.dispose()
