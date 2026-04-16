import os
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# Can be overridden via env var so the backend can share the same DB later
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.sqxwactoqwbqsosbfilz:sihamdisoudani@aws-0-eu-west-1.pooler.supabase.com:6543/postgres",
)

_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def _configure_conn(conn) -> None:
    """
    Called for every new connection in the pool.

    Supabase exposes PgBouncer on port 6543 in *transaction* mode.
    PgBouncer transaction mode does NOT support server-side prepared
    statements.  In psycopg3, `prepare_threshold = None` fully disables
    automatic statement preparation so we never get:
        DuplicatePreparedStatement: prepared statement "_pg3_0" already exists
    """
    conn.prepare_threshold = None  # type: ignore[assignment]


async def get_checkpointer() -> AsyncPostgresSaver:
    """Initialize once and return the shared AsyncPostgresSaver."""
    global _pool, _saver
    if _saver is not None:
        return _saver

    logger.info("Initialising Postgres checkpoint pool ...")
    _pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=10,
        # open=False prevents the deprecated auto-open inside __init__;
        # we call pool.open() explicitly right after.
        open=False,
        # autocommit=True is required by AsyncPostgresSaver
        kwargs={"autocommit": True},
        configure=_configure_conn,
    )
    await _pool.open(wait=True)
    _saver = AsyncPostgresSaver(_pool)
    # Creates the checkpoint tables the first time (idempotent)
    await _saver.setup()
    logger.info("Postgres checkpointer ready.")
    return _saver


async def close_checkpointer() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("Postgres connection pool closed.")
