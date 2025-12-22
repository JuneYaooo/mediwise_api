from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Load environment variables
load_dotenv()

# Get database connection parameters from environment variables
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE", "mediwise_api")

# URL encode password to handle special characters like @
POSTGRES_PASSWORD_ENCODED = quote_plus(POSTGRES_PASSWORD)

# Construct DATABASE_URL from individual parameters
DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD_ENCODED}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"

# Database connection pooling parameters
pool_size = int(os.getenv("DATABASE_POOL_SIZE", "5"))
max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
pool_timeout = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
pool_recycle = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))  # Recycle connections every hour
pool_pre_ping = os.getenv("DATABASE_POOL_PRE_PING", "True").lower() in ("true", "1", "t")

# Create engine with connection pooling and recovery settings
engine = create_engine(
    DATABASE_URL,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle,  # Recycle connections to prevent timeout issues
    pool_pre_ping=pool_pre_ping,  # Test connections before use
    echo=False,  # Set to True for SQL debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 