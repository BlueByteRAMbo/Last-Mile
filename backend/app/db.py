import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

RAW_URL = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./lastmile.db"

if RAW_URL.startswith("postgresql://") or RAW_URL.startswith("postgres://"):
    # asyncpg needs postgresql+asyncpg:// and no query string (sslmode/channel_binding passed via connect_args instead)
    ASYNC_URL = RAW_URL.replace("postgresql://", "postgresql+asyncpg://").replace("postgres://", "postgresql+asyncpg://").split("?")[0]
    connect_args = {"ssl": "require"}
else:
    ASYNC_URL = RAW_URL
    connect_args = {}

engine = create_async_engine(ASYNC_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as session:
        yield session
