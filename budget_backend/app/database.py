import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Railway automatically injects DATABASE_URL when you add a Postgres plugin.
# Locally, set it in a .env file (see .env.example).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/budget_db")

# Railway's DATABASE_URL sometimes starts with postgres:// — SQLAlchemy 2.x needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
