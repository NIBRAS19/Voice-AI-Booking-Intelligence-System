"""
Database connection and session management.
Uses asyncpg for high-performance async PostgreSQL connections.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import asyncpg
from asyncpg import Pool, Connection

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Global connection pool
_pool: Optional[Pool] = None


import json

async def init_connection(conn: Connection) -> None:
    """Initialize database connection with type codecs."""
    try:
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    except Exception as e:
        logger.warning(f"Failed to register JSON codec: {e}")


async def create_pool() -> Pool:
    """Create the database connection pool."""
    global _pool
    
    if _pool is not None:
        return _pool
    
    logger.info("Creating database connection pool", database_url=settings.database_url.split("@")[-1])
    
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=settings.database_pool_size,
        max_inactive_connection_lifetime=300,
        command_timeout=60,
        init=init_connection,
    )
    
    logger.info("Database connection pool created successfully")
    return _pool


async def close_pool() -> None:
    """Close the database connection pool."""
    global _pool
    
    if _pool is not None:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None


async def get_pool() -> Pool:
    """Get the database connection pool, creating if necessary."""
    global _pool
    
    if _pool is None:
        _pool = await create_pool()
    
    return _pool


@asynccontextmanager
async def get_db() -> AsyncGenerator[Connection, None]:
    """
    Get a database connection from the pool.
    
    Usage:
        async with get_db() as db:
            result = await db.fetch("SELECT * FROM users")
    """
    pool = await get_pool()
    
    async with pool.acquire() as connection:
        try:
            yield connection
        except Exception as e:
            logger.error("Database error", error=str(e))
            raise


async def get_db_connection() -> Connection:
    """
    Get a database connection (for use in services).
    Caller is responsible for releasing the connection.
    """
    pool = await get_pool()
    return await pool.acquire()


async def release_db_connection(connection: Connection) -> None:
    """Release a database connection back to the pool."""
    pool = await get_pool()
    await pool.release(connection)


async def init_db() -> None:
    """
    Initialize the database.
    Run migrations and verify connection.
    """
    logger.info("Initializing database connection")
    
    try:
        async with get_db() as db:
            # Verify connection
            result = await db.fetchval("SELECT 1")
            assert result == 1
            
            # Check if required extensions exist
            extensions = await db.fetch(
                "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'btree_gist')"
            )
            ext_names = [ext["extname"] for ext in extensions]
            
            if "uuid-ossp" not in ext_names:
                logger.warning("Extension uuid-ossp not found. Please run migrations.")
            
            if "btree_gist" not in ext_names:
                logger.warning("Extension btree_gist not found. Required for booking constraints.")
            
            logger.info("Database connection verified successfully")
            
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def execute_raw_sql(sql: str) -> None:
    """
    Execute raw SQL (for migrations or admin tasks).
    Use with caution!
    """
    async with get_db() as db:
        await db.execute(sql)


class DatabaseTransaction:
    """
    Context manager for database transactions.
    
    Usage:
        async with DatabaseTransaction() as tx:
            await tx.execute("INSERT INTO ...")
            await tx.execute("UPDATE ...")
            # Automatically commits on success, rolls back on error
    """
    
    def __init__(self):
        self.connection: Optional[Connection] = None
        self.transaction = None
    
    async def __aenter__(self) -> Connection:
        pool = await get_pool()
        self.connection = await pool.acquire()
        self.transaction = self.connection.transaction()
        await self.transaction.start()
        return self.connection
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                await self.transaction.rollback()
                logger.warning("Transaction rolled back", error=str(exc_val))
            else:
                await self.transaction.commit()
        finally:
            pool = await get_pool()
            await pool.release(self.connection)
