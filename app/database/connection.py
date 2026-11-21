"""Database connection and lifecycle management for SQLite."""
import sys
import sqlite3
import shutil
from pathlib import Path
from typing import Optional
from app.config.constants import DEFAULT_DB_PATH, BUNDLE_DIR


class DatabaseManager:
    """Manages SQLite connections, migrations, backups, and restores."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Creates a new SQLite connection with foreign keys and WAL enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_schema(self) -> None:
        """Executes the DDL schema if tables do not exist."""
        candidates = [
            Path(__file__).parent / "schema.sql",
            BUNDLE_DIR / "app" / "database" / "schema.sql",
            BUNDLE_DIR / "schema.sql",
            Path("app/database/schema.sql")
        ]
        schema_path = next((p for p in candidates if p.exists()), None)
        if schema_path:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            with self.get_connection() as conn:
                conn.executescript(schema_sql)

    def backup_database(self, destination_path: Path) -> Path:
        """Performs an online live zero-downtime database backup."""
        destination_path = Path(destination_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as src_conn:
            with sqlite3.connect(str(destination_path)) as dst_conn:
                src_conn.backup(dst_conn)
        return destination_path

    def restore_database(self, backup_path: Path) -> bool:
        """Restores the database safely from a backup file."""
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Test the backup integrity first
        with sqlite3.connect(str(backup_path)) as test_conn:
            cursor = test_conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            if not result or result[0] != "ok":
                raise ValueError(f"Backup integrity check failed: {result}")

        # Copy over
        shutil.copy2(str(backup_path), str(self.db_path))
        return True


# Global default database instance
db_manager = DatabaseManager()

