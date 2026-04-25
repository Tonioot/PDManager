from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATA_DIR = os.path.expanduser("~/.cloudbase")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/cloudbase.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from models import Application, User
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate existing DBs: add columns introduced after initial schema.
        result = await conn.exec_driver_sql("PRAGMA table_info(applications)")
        existing_columns = {row[1] for row in result.fetchall()}

        for col, definition in [
            ("auto_start",        "BOOLEAN NOT NULL DEFAULT 0"),
            ("restart_policy",    "VARCHAR(20) NOT NULL DEFAULT 'no'"),
            ("maintenance_mode",  "BOOLEAN NOT NULL DEFAULT 0"),
            ("update_mode",       "BOOLEAN NOT NULL DEFAULT 0"),
            ("downtime_page",     "TEXT"),
            ("update_page",       "TEXT"),
            ("restart_page",      "TEXT"),
            ("starting_page",     "TEXT"),
            ("extra_domains",     "TEXT"),
            ("redirect_domains",  "TEXT"),
        ]:
            if col in existing_columns:
                continue
            await conn.exec_driver_sql(
                f"ALTER TABLE applications ADD COLUMN {col} {definition}"
            )

    # Seed admin user from credentials file if no users exist yet
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select as _select
        from models import User
        result = await session.execute(_select(User))
        if result.scalars().first() is None:
            creds_file = os.path.join(DATA_DIR, "credentials")
            if os.path.exists(creds_file):
                with open(creds_file) as f:
                    hashed = f.read().strip()
            else:
                # No credentials yet — generate a placeholder; start.sh will set real password
                import bcrypt
                hashed = bcrypt.hashpw(b"changeme", bcrypt.gensalt()).decode()
            admin = User(username="admin", hashed_password=hashed, role="admin")
            session.add(admin)
            await session.commit()
