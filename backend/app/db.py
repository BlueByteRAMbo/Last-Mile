import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

RAW_URL = os.environ["DATABASE_URL"]
# asyncpg needs postgresql+asyncpg:// and no sslmode query param (passed via connect_args)
ASYNC_URL = RAW_URL.replace("postgresql://", "postgresql+asyncpg://").split("?")[0]

engine = create_async_engine(ASYNC_URL, connect_args={"ssl": "require"}, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as session:
        yield session
