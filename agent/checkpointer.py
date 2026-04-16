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


async def get_checkpointer() -> AsyncPostgresSaver:
    """Initialize once and return the shared AsyncPostgresSaver."""
    global _pool, _saver
    if _saver is not None:
        return _saver

    logger.info("Initialising Postgres checkpoint pool ...")
    _pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        max_size=20,
        # autocommit + prepare_threshold=0 are required by AsyncPostgresSaver
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _pool.open()
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
