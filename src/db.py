"""Database helpers."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql+psycopg://football:football@localhost:5432/football"


def get_engine() -> Engine:
    return create_engine(os.getenv("DATABASE_URL", DEFAULT_URL), future=True)


def init_schema(engine: Engine) -> None:
    """Run every SQL file in sql/init (safe to run several times)."""
    for sql_file in sorted((ROOT / "sql" / "init").glob("*.sql")):
        with engine.begin() as conn:
            conn.exec_driver_sql(sql_file.read_text())