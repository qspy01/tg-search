"""
importer.py - High-Performance Log File Importer
Efficiently loads millions of records into SQLite with FTS5
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Generator, Set
import hashlib
from datetime import datetime

from database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogImporter:
    """High-performance log file importer with deduplication"""
    
    def __init__(self, db: Database, chunk_size: int = 10000):
        """
        Args:
            db: Database instance
            chunk_size: Number of records to insert per transaction
        """
        self.db = db
        self.chunk_size = chunk_size
        self.seen_hashes: Set[str] = set()
        self.stats = {
            "total_lines": 0,
            "imported": 0,
            "duplicates": 0,
            "empty_lines": 0,
            "start_time": None,
            "end_time": None
        }
    
    def read_file_generator(self, file_path: Path) -> Generator[str, None, None]:
        """
        Memory-efficient file reader using generator pattern
        
        Args:
            file_path: Path to the log file
            
        Yields:
            Individual lines from the file
        """
        logger.info(f"Reading file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines
                    if not line:
                        self.stats["empty_lines"] += 1
                        continue
                    
                    self.stats["total_lines"] += 1
                    
                    # Progress indicator
                    if line_num % 100000 == 0:
                        logger.info(f"Read {line_num:,} lines...")
                    
                    yield line
                    
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise
    
    def deduplicate_records(self, records: list[str]) -> list[str]:
        """
        Remove duplicate records using hash-based deduplication
        
        Args:
            records: List of records to check
            
        Returns:
            List of unique records
        """
        unique_records = []
        
        for record in records:
            # Generate hash of the record
            record_hash = hashlib.md5(record.encode()).hexdigest()
            
            if record_hash not in self.seen_hashes:
                self.seen_hashes.add(record_hash)
                unique_records.append(record)
            else:
                self.stats["duplicates"] += 1
        
        return unique_records
    
    async def import_file(
        self, 
        file_path: str | Path,
        deduplicate: bool = True
    ) -> dict:
        """
        Import log file into database with optimal performance
        
        Args:
            file_path: Path to the log file
            deduplicate: Whether to remove duplicate entries
            
        Returns:
            Dictionary with import statistics
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        self.stats["start_time"] = datetime.now()
        logger.info(f"Starting import from: {file_path}")
        logger.info(f"Deduplication: {'enabled' if deduplicate else 'disabled'}")
        
        # Process file in chunks
        chunk = []
        
        for line in self.read_file_generator(file_path):
            chunk.append(line)
            
            # When chunk is full, insert into database
            if len(chunk) >= self.chunk_size:
                # Deduplicate if enabled
                if deduplicate:
                    chunk = self.deduplicate_records(chunk)
                
                if chunk:  # Only insert if there are unique records
                    await self.db.bulk_insert(chunk, chunk_size=self.chunk_size)
                    self.stats["imported"] += len(chunk)
                
                chunk = []  # Reset chunk
        
        # Insert remaining records
        if chunk:
            if deduplicate:
                chunk = self.deduplicate_records(chunk)
            
            if chunk:
                await self.db.bulk_insert(chunk, chunk_size=self.chunk_size)
                self.stats["imported"] += len(chunk)
        
        self.stats["end_time"] = datetime.now()
        
        # Calculate duration
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        records_per_second = self.stats["imported"] / duration if duration > 0 else 0
        
        # Log final statistics
        logger.info("=" * 60)
        logger.info("IMPORT COMPLETED")
        logger.info("=" * 60)
        logger.info(f"Total lines read: {self.stats['total_lines']:,}")
        logger.info(f"Records imported: {self.stats['imported']:,}")
        logger.info(f"Duplicates skipped: {self.stats['duplicates']:,}")
        logger.info(f"Empty lines skipped: {self.stats['empty_lines']:,}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Speed: {records_per_second:,.0f} records/second")
        logger.info("=" * 60)
        
        return self.stats


async def main():
    """Main importer script"""
    if len(sys.argv) < 2:
        print("Usage: python importer.py <log_file_path> [--no-dedupe]")
        print("\nExample:")
        print("  python importer.py data/logs.txt")
        print("  python importer.py data/logs.txt --no-dedupe")
        sys.exit(1)
    
    file_path = sys.argv[1]
    deduplicate = "--no-dedupe" not in sys.argv
    
    # Initialize database
    db = Database()
    await db.connect()
    
    try:
        # Create importer instance
        importer = LogImporter(db, chunk_size=10000)
        
        # Import file
        stats = await importer.import_file(file_path, deduplicate=deduplicate)
        
        # Show final database stats
        db_stats = await db.get_stats()
        print("\n📊 Database Statistics:")
        print(f"   Total records: {db_stats['total_records']:,}")
        print(f"   Database size: {db_stats['db_size_mb']} MB")
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
