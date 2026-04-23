from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATA_DIR = os.path.expanduser("~/.pdmanager")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/pdmanager.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from models import Application
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate existing DBs: add columns introduced after initial schema.
        result = await conn.exec_driver_sql("PRAGMA table_info(applications)")
        existing_columns = {row[1] for row in result.fetchall()}

        for col, definition in [
            ("auto_start",       "BOOLEAN NOT NULL DEFAULT 0"),
            ("restart_policy",   "VARCHAR(20) NOT NULL DEFAULT 'no'"),
            ("maintenance_mode", "BOOLEAN NOT NULL DEFAULT 0"),
            ("update_mode",      "BOOLEAN NOT NULL DEFAULT 0"),
            ("downtime_page",    "TEXT"),
            ("update_page",      "TEXT"),
            ("restart_page",     "TEXT"),
        ]:
            if col in existing_columns:
                continue
            await conn.exec_driver_sql(
                f"ALTER TABLE applications ADD COLUMN {col} {definition}"
            )
