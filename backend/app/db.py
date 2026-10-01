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


async def auto_migrate(conn):
    """Hackathon-pragmatic substitute for real migrations: create_all only creates missing
    TABLES, not missing COLUMNS on ones that already exist — and this schema keeps growing across
    phases. Diff each model's columns against the live table and ADD COLUMN whatever's missing,
    with a type-appropriate default so existing rows don't end up with nulls in non-nullable columns.
    """
    from sqlalchemy import inspect as sa_inspect, text

    def _sync_inspect(sync_conn):
        inspector = sa_inspect(sync_conn)
        return {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}

    existing = await conn.run_sync(_sync_inspect)

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all already handles brand-new tables
        live_columns = existing[table.name]
        for col in table.columns:
            if col.name in live_columns:
                continue
            sql_type = col.type.compile(dialect=conn.dialect)
            default_sql = ""
            if col.default is not None and getattr(col.default, "is_scalar", False):
                val = col.default.arg
                if isinstance(val, str):
                    default_sql = f" DEFAULT '{val}'"
                elif isinstance(val, bool):
                    default_sql = f" DEFAULT {'TRUE' if val else 'FALSE'}"
                elif isinstance(val, (int, float)):
                    default_sql = f" DEFAULT {val}"
            await conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {sql_type}{default_sql}'))
