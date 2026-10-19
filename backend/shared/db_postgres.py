"""PostgreSQL connections: the primary takes all writes; the replica serves the API's reads."""

from pathlib import Path

from sqlalchemy import Engine, create_engine

from shared.settings import settings

SCHEMA_FILE = Path(__file__).with_name("db_schema.sql")


def _helper_make_engine(url) -> Engine:
    """Create a connection pool for this process. The connect timeout makes an outage fail fast, not hang."""
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS},
    )


primary_engine = _helper_make_engine(settings.database_url())
# Without a real replica (local development), reads go to the primary.
if settings.POSTGRES_REPLICA_HOST:
    replica_engine = _helper_make_engine(settings.database_url(replica=True))
else:
    replica_engine = primary_engine
