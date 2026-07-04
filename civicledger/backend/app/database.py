from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(settings.DATABASE_URL_SYNC, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def get_sync_db() -> Session:
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
