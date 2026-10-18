"""PostgreSQL connections: the primary takes all writes; the replica serves the API's reads."""

from pathlib import Path

from sqlalchemy import Engine, create_engine

from shared.config import settings

SCHEMA_FILE = Path(__file__).with_name("db_schema.sql")


def make_engine(url) -> Engine:
    """Create a connection pool for this process. The connect timeout makes an outage fail fast, not hang."""
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )


primary_engine = make_engine(settings.database_url())
# Without a real replica (local development), reads go to the primary.
if settings.postgres_replica_host:
    replica_engine = make_engine(settings.database_url(replica=True))
else:
    replica_engine = primary_engine
