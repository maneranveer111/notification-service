from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()

class Base(DeclarativeBase):
    """
    Base class for all ORM models.
    Every table model will inherit from this Base.
    """
    pass

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

def get_db():
    """
    FastAPI dependency.
    Creates a DB session for a request and closes it after the request is done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()