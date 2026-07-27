import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Railway automatically injects DATABASE_URL when you add a Postgres plugin.
# Locally, set it in a .env file (see .env.example).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/budget_db")

# Railway's DATABASE_URL sometimes starts with postgres:// — normalize to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Force the psycopg (v3) driver instead of psycopg2. psycopg2-binary depends on
# a system-level libpq.so that Railway's slim Python image doesn't ship with,
# causing "ImportError: libpq.so.5: cannot open shared object file" at startup.
# psycopg[binary] bundles libpq inside the wheel, so it doesn't have this problem.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
