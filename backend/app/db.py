from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # The default pool is 5 (+10 overflow). The network-wide outbound job holds
    # a connection for the whole run, so with the default the API is left
    # contending for what remains.
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
)
# expire_on_commit=False: with the default, every commit expires all loaded
# instances, so touching an attribute afterwards re-SELECTs that row. The batch
# indent path commits thousands of reports and the caller then reads their
# quantities — that alone is a refresh per row. Keeping values loaded across a
# commit removes those round trips.
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
