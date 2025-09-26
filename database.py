"""
Database models and connection management for Botsana.
Provides persistent storage using SQLAlchemy with PostgreSQL.
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import QueuePool

Base = declarative_base()

class Guild(Base):
    """Represents a Discord guild/server."""
    __tablename__ = 'guilds'

    id = Column(Integer, primary_key=True)  # Discord guild ID
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    configs = relationship("GuildConfig", back_populates="guild", cascade="all, delete-orphan")
    error_logs = relationship("ErrorLog", back_populates="guild", cascade="all, delete-orphan")

class GuildConfig(Base):
    """Configuration settings for each guild."""
    __tablename__ = 'guild_configs'

    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, ForeignKey('guilds.id'), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text)  # JSON string for complex values
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="configs")

    __table_args__ = {'sqlite_autoincrement': True}

class ErrorLog(Base):
    """Comprehensive error logging."""
    __tablename__ = 'error_logs'

    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, ForeignKey('guilds.id'))
    user_id = Column(Integer)
    severity = Column(String(20), default='ERROR')  # ERROR, CRITICAL, WARNING, INFO
    error_type = Column(String(255))
    error_message = Column(Text)
    context = Column(Text)
    command = Column(String(255))
    stack_trace = Column(Text)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="error_logs")

    __table_args__ = {'sqlite_autoincrement': True}

class GlobalConfig(Base):
    """Global bot configuration."""
    __tablename__ = 'global_configs'

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BotStats(Base):
    """Bot usage statistics."""
    __tablename__ = 'bot_stats'

    id = Column(Integer, primary_key=True)
    stat_type = Column(String(100), nullable=False)  # commands_used, errors_logged, etc.
    stat_value = Column(Integer, default=0)
    metadata_json = Column(Text)  # Additional data as JSON
    recorded_at = Column(DateTime, default=datetime.utcnow)

class DatabaseManager:
    """Manages database connections and operations."""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()

    def _initialize_database(self):
        """Initialize database connection."""
        database_url = os.getenv('DATABASE_URL')

        if not database_url:
            # Fallback to SQLite for development (won't persist on Heroku)
            database_url = 'sqlite:///botsana.db'
            print("⚠️  WARNING: No DATABASE_URL found, using SQLite (data won't persist on Heroku)")

        # Handle Heroku Postgres URL format
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        try:
            self.engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False  # Set to True for debugging
            )

            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            print("✅ Database initialized successfully")

        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
            raise

    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()

    def ensure_guild_exists(self, guild_id: int, guild_name: str = None):
        """Ensure a guild record exists in the database."""
        with self.get_session() as session:
            guild = session.query(Guild).filter(Guild.id == guild_id).first()
            if not guild:
                guild = Guild(id=guild_id, name=guild_name or f"Guild {guild_id}")
                session.add(guild)
                session.commit()
            return guild

# Global database manager instance
db_manager = DatabaseManager()
