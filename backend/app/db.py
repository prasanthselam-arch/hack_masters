from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)


def init_db() -> None:
    from app.models import tables  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    _migrate_data()


def _add_missing_columns() -> None:
    """create_all() does not alter existing tables; add columns introduced after a database was created."""
    added = {
        "patient": {"owner_id": ("VARCHAR", True), "relationship": ("VARCHAR", True)},
        "account": {"email": ("VARCHAR", True), "email_verified_at": ("TIMESTAMP", False),
                    "notify_security": ("BOOLEAN NOT NULL DEFAULT TRUE", False),
                    "notify_medicines": ("BOOLEAN NOT NULL DEFAULT TRUE", False),
                    "notify_weekly": ("BOOLEAN NOT NULL DEFAULT TRUE", False), "last_weekly_at": ("TIMESTAMP", False)},
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in added.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for col, (sql_type, indexed) in cols.items():
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}"))
                    if indexed:
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})"))


def _migrate_data() -> None:
    """Idempotent fix-ups for data saved by earlier versions."""
    with engine.begin() as conn:
        # Indian mobile numbers used to be stored as 10 bare digits; now everything is E.164.
        for table, col in (("account", "login"), ("patient", "phone")):
            rows = conn.execute(text(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")).all()
            for row_id, value in rows:
                digits = "".join(ch for ch in value if ch.isdigit())
                if "@" not in value and not value.startswith("+") and len(digits) == 10 and digits[0] in "6789":
                    conn.execute(text(f"UPDATE {table} SET {col} = :v WHERE id = :id"), {"v": "+91" + digits, "id": row_id})
        # Accounts that sign in with an email use it for codes and alerts too (it still needs verifying).
        conn.execute(text("UPDATE account SET email = login WHERE email IS NULL AND login LIKE '%@%'"))
        # Each account's first profile is the account holder's own.
        owners = conn.execute(text("SELECT DISTINCT owner_id FROM patient WHERE owner_id IS NOT NULL")).scalars().all()
        for owner in owners:
            has_self = conn.execute(text("SELECT 1 FROM patient WHERE owner_id = :o AND relationship = 'self'"), {"o": owner}).first()
            if not has_self:
                first = conn.execute(text("SELECT id FROM patient WHERE owner_id = :o AND relationship IS NULL ORDER BY created_at LIMIT 1"),
                                     {"o": owner}).scalar()
                if first:
                    conn.execute(text("UPDATE patient SET relationship = 'self' WHERE id = :id"), {"id": first})


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
