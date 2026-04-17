import os
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def _configure_conn(conn) -> None:
    """Disable prepared statements for PgBouncer transaction mode."""
    conn.prepare_threshold = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _pool, _saver
    if _saver is not None:
        return _saver

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required")

    logger.info("Initialising Postgres checkpoint pool ...")
    _pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": True},
        configure=_configure_conn,
    )
    await _pool.open(wait=True)
    _saver = AsyncPostgresSaver(_pool)
    await _saver.setup()
    logger.info("Postgres checkpointer ready.")
    return _saver


async def close_checkpointer() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("Postgres connection pool closed.")
