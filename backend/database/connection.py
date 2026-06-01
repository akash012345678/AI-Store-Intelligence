import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.base import Base


# Global session factory
SessionLocal = None
engine = None

def init_db(database_url: str = "sqlite:///store_intelligence.db"):
    """Initializes the database engine and session factory."""
    global SessionLocal, engine
    
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        
    engine = create_engine(database_url, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # For SQLite, automatically register a listener to enforce foreign keys on connect
    if database_url.startswith("sqlite"):
        from sqlalchemy import event
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine

def get_db():
    """Dependency generator that provides a database session."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Please call init_db() first.")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
