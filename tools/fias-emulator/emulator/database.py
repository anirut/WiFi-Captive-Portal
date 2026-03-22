"""
SQLAlchemy async database setup for FIAS Emulator.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from emulator.config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL debugging
)

# Session factory
AsyncSessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session."""
    async with AsyncSessionFactory() as session:
        yield session


async def init_db() -> None:
    """Create all tables. Called on application startup."""
    from emulator.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the database engine. Called on application shutdown."""
    await engine.dispose()
