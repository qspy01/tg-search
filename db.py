"""
database.py - High-Performance FTS5 Database Layer
Handles all database operations with Full-Text Search optimization
"""
import aiosqlite
import logging
from typing import List, Tuple, Optional
from contextlib import asynccontextmanager
import os

logger = logging.getLogger(__name__)

DB_PATH = "logs_database.db"


class Database:
    """Async database wrapper with FTS5 support"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """Establish database connection and initialize schema"""
        self._connection = await aiosqlite.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None  # Autocommit mode for better concurrency
        )
        
        # Enable performance optimizations
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA cache_size=-64000")  # 64MB cache
        await self._connection.execute("PRAGMA temp_store=MEMORY")
        
        await self._init_schema()
        logger.info(f"Database connected: {self.db_path}")
    
    async def disconnect(self) -> None:
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            logger.info("Database disconnected")
    
    async def _init_schema(self) -> None:
        """Initialize FTS5 virtual table for full-text search"""
        # Create FTS5 virtual table with optimized tokenizer
        await self._connection.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts 
            USING fts5(
                raw_data,
                tokenize='porter unicode61 remove_diacritics 2'
            )
        """)
        
        # Create metadata table for statistics
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await self._connection.commit()
        logger.info("Database schema initialized with FTS5")
    
    async def search(
        self, 
        query: str, 
        limit: int = 30,
        offset: int = 0
    ) -> Tuple[List[str], int]:
        """
        Perform FTS5 full-text search
        
        Args:
            query: Search query (sanitized)
            limit: Maximum results to return
            offset: Offset for pagination
            
        Returns:
            Tuple of (results list, total count)
        """
        if not query.strip():
            return [], 0
        
        # Sanitize query for FTS5 MATCH syntax
        sanitized_query = self._sanitize_fts_query(query)
        
        try:
            # Get total count
            count_cursor = await self._connection.execute(
                "SELECT COUNT(*) FROM logs_fts WHERE logs_fts MATCH ?",
                (sanitized_query,)
            )
            total_count = (await count_cursor.fetchone())[0]
            await count_cursor.close()
            
            # Get results with ranking
            cursor = await self._connection.execute("""
                SELECT raw_data, rank
                FROM logs_fts
                WHERE logs_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """, (sanitized_query, limit, offset))
            
            results = [row[0] for row in await cursor.fetchall()]
            await cursor.close()
            
            logger.info(f"Search for '{query}': {total_count} total, {len(results)} returned")
            return results, total_count
            
        except Exception as e:
            logger.error(f"Search error for query '{query}': {e}")
            raise
    
    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """
        Sanitize user input for FTS5 MATCH queries
        Prevents syntax errors from special characters
        """
        # Remove or escape FTS5 special characters
        special_chars = ['"', '*', '^', '(', ')', '{', '}', '[', ']']
        sanitized = query
        
        for char in special_chars:
            sanitized = sanitized.replace(char, ' ')
        
        # Split into tokens and join with OR for flexible matching
        tokens = [t.strip() for t in sanitized.split() if t.strip()]
        
        if not tokens:
            return '""'  # Empty match
        
        # Use phrase matching for better results
        if len(tokens) == 1:
            return f'"{tokens[0]}"'
        
        # Multiple tokens: use OR for flexibility
        return ' OR '.join(f'"{token}"' for token in tokens)
    
    async def get_stats(self) -> dict:
        """Get database statistics"""
        try:
            cursor = await self._connection.execute(
                "SELECT COUNT(*) FROM logs_fts"
            )
            total_rows = (await cursor.fetchone())[0]
            await cursor.close()
            
            # Get database file size
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            return {
                "total_records": total_rows,
                "db_size_mb": round(db_size / (1024 * 1024), 2),
                "db_path": self.db_path
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}
    
    async def bulk_insert(self, records: List[str], chunk_size: int = 10000) -> int:
        """
        Bulk insert records in optimized transactions
        
        Args:
            records: List of text records to insert
            chunk_size: Number of records per transaction
            
        Returns:
            Number of records inserted
        """
        total_inserted = 0
        
        # Process in chunks for optimal performance
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            
            try:
                await self._connection.execute("BEGIN TRANSACTION")
                
                await self._connection.executemany(
                    "INSERT INTO logs_fts(raw_data) VALUES (?)",
                    [(record,) for record in chunk]
                )
                
                await self._connection.execute("COMMIT")
                total_inserted += len(chunk)
                
                if (i // chunk_size + 1) % 10 == 0:
                    logger.info(f"Inserted {total_inserted} records...")
                    
            except Exception as e:
                await self._connection.execute("ROLLBACK")
                logger.error(f"Error inserting chunk at position {i}: {e}")
                raise
        
        # Optimize FTS5 index after bulk insert
        await self._connection.execute("INSERT INTO logs_fts(logs_fts) VALUES('optimize')")
        await self._connection.commit()
        
        logger.info(f"Bulk insert completed: {total_inserted} records")
        return total_inserted
    
    async def clear_all(self) -> None:
        """Clear all data from the database (use with caution)"""
        await self._connection.execute("DELETE FROM logs_fts")
        await self._connection.commit()
        logger.warning("All data cleared from database")


# Global database instance
db = Database()


async def init_db() -> None:
    """Initialize database connection"""
    await db.connect()


async def close_db() -> None:
    """Close database connection"""
    await db.disconnect()
