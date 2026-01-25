import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "panwatch.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(engine):
    """增量 schema 迁移（SQLite ALTER TABLE ADD COLUMN）"""
    migrations = [
        ("stock_agents", "schedule", "ALTER TABLE stock_agents ADD COLUMN schedule TEXT DEFAULT ''"),
    ]
    with engine.connect() as conn:
        for table, column, sql in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(f"SELECT {column} FROM {table} LIMIT 1"))
            except Exception:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
