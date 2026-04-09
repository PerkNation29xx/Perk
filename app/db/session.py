from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


database_url = settings.sqlalchemy_database_url


def _uses_transaction_pooler(url: str) -> bool:
    if not url.startswith("postgresql+psycopg://"):
        return False

    try:
        parsed = make_url(url)
    except Exception:
        return False

    host = (parsed.host or "").lower()
    port = parsed.port
    return host.endswith(".pooler.supabase.com") or port == 6543


if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif _uses_transaction_pooler(database_url):
    # Supabase pooler connections can fail on startup with psycopg prepared
    # statements ("prepared statement ... already exists"). Disable prepares.
    connect_args = {"prepare_threshold": None}
else:
    connect_args = {}

engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
