"""
Database models and connection management for Botsana.
Provides persistent storage using SQLAlchemy with PostgreSQL.
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import QueuePool

Base = declarative_base()

class Guild(Base):
    """Represents a Discord guild/server."""
    __tablename__ = 'guilds'

    id = Column(BigInteger, primary_key=True)  # Discord guild ID (snowflake)
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    configs = relationship("GuildConfig", back_populates="guild", cascade="all, delete-orphan")
    error_logs = relationship("ErrorLog", back_populates="guild", cascade="all, delete-orphan")
    user_mappings = relationship("UserMapping", back_populates="guild", cascade="all, delete-orphan")
    notification_preferences = relationship("UserNotificationPreferences", back_populates="guild", cascade="all, delete-orphan")
    chat_channels = relationship("ChatChannel", back_populates="guild", cascade="all, delete-orphan")

class GuildConfig(Base):
    """Configuration settings for each guild."""
    __tablename__ = 'guild_configs'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
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
    guild_id = Column(BigInteger, ForeignKey('guilds.id'))
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

class UserMapping(Base):
    """Maps Discord users to Asana users for task assignment."""
    __tablename__ = 'user_mappings'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    discord_user_id = Column(BigInteger, nullable=False)  # Discord user ID (snowflake)
    asana_user_id = Column(String(255), nullable=False)  # Asana user ID/GID
    discord_username = Column(String(255))  # Store username for reference
    asana_user_name = Column(String(255))  # Store Asana user name for reference
    created_by = Column(BigInteger, nullable=False)  # Discord user who created this mapping
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="user_mappings")

    __table_args__ = {'sqlite_autoincrement': True}

class UserNotificationPreferences(Base):
    """User notification preferences for task updates."""
    __tablename__ = 'user_notification_preferences'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    discord_user_id = Column(BigInteger, nullable=False)
    due_date_reminder = Column(String(50), default='1_day')  # 'disabled', '1_hour', '1_day', '1_week'
    assignment_notifications = Column(String(50), default='enabled')  # 'enabled', 'disabled'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="notification_preferences")

    __table_args__ = {'sqlite_autoincrement': True}

class ChatChannel(Base):
    """Designated channel for natural language task creation."""
    __tablename__ = 'chat_channels'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    channel_id = Column(BigInteger, nullable=False)  # Discord channel ID
    channel_name = Column(String(255))  # Store channel name for reference
    created_by = Column(BigInteger, nullable=False)  # Discord user who set it
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="chat_channels")

    __table_args__ = {'sqlite_autoincrement': True}

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
            try:
                Base.metadata.create_all(bind=self.engine)
                print("✅ Database initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not create tables: {e}")
                print("This might be due to existing tables with different schema.")
                print("Consider running database migrations or dropping tables manually.")

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

    def get_user_mapping(self, guild_id: int, discord_user_id: int) -> Optional[Dict[str, Any]]:
        """Get the Asana user mapping for a Discord user."""
        with self.get_session() as session:
            mapping = session.query(UserMapping).filter(
                UserMapping.guild_id == guild_id,
                UserMapping.discord_user_id == discord_user_id
            ).first()

            if mapping:
                return {
                    'id': mapping.id,
                    'guild_id': mapping.guild_id,
                    'discord_user_id': mapping.discord_user_id,
                    'asana_user_id': mapping.asana_user_id,
                    'discord_username': mapping.discord_username,
                    'asana_user_name': mapping.asana_user_name,
                    'created_by': mapping.created_by,
                    'created_at': mapping.created_at,
                    'updated_at': mapping.updated_at
                }
            return None

    def set_user_mapping(self, guild_id: int, discord_user_id: int, asana_user_id: str,
                        discord_username: str = None, asana_user_name: str = None,
                        created_by: int = None) -> bool:
        """Create or update a user mapping."""
        try:
            with self.get_session() as session:
                # Ensure guild exists
                self.ensure_guild_exists(guild_id)

                # Check if mapping already exists
                existing = session.query(UserMapping).filter(
                    UserMapping.guild_id == guild_id,
                    UserMapping.discord_user_id == discord_user_id
                ).first()

                if existing:
                    # Update existing mapping
                    existing.asana_user_id = asana_user_id
                    existing.discord_username = discord_username
                    existing.asana_user_name = asana_user_name
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new mapping
                    mapping = UserMapping(
                        guild_id=guild_id,
                        discord_user_id=discord_user_id,
                        asana_user_id=asana_user_id,
                        discord_username=discord_username,
                        asana_user_name=asana_user_name,
                        created_by=created_by
                    )
                    session.add(mapping)

                session.commit()
                return True
        except Exception as e:
            print(f"Error setting user mapping: {e}")
            return False

    def remove_user_mapping(self, guild_id: int, discord_user_id: int) -> bool:
        """Remove a user mapping."""
        try:
            with self.get_session() as session:
                mapping = session.query(UserMapping).filter(
                    UserMapping.guild_id == guild_id,
                    UserMapping.discord_user_id == discord_user_id
                ).first()

                if mapping:
                    session.delete(mapping)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error removing user mapping: {e}")
            return False

    def list_user_mappings(self, guild_id: int) -> list:
        """List all user mappings for a guild."""
        with self.get_session() as session:
            mappings = session.query(UserMapping).filter(UserMapping.guild_id == guild_id).all()

            return [{
                'id': m.id,
                'discord_user_id': m.discord_user_id,
                'discord_username': m.discord_username,
                'asana_user_id': m.asana_user_id,
                'asana_user_name': m.asana_user_name,
                'created_by': m.created_by,
                'created_at': m.created_at
            } for m in mappings]

    def get_user_mapping_by_asana_id(self, asana_user_id: str) -> Optional[Dict[str, Any]]:
        """Get Discord user mapping by Asana user ID (returns first match across all guilds)."""
        try:
            with self.get_session() as session:
                # Get all mappings for this Asana user and return the first one
                # In practice, one Asana user might be mapped in multiple guilds
                mapping = session.query(UserMapping).filter(
                    UserMapping.asana_user_id == asana_user_id
                ).first()

                if mapping:
                    return {
                        'id': mapping.id,
                        'guild_id': mapping.guild_id,
                        'discord_user_id': mapping.discord_user_id,
                        'discord_username': mapping.discord_username,
                        'asana_user_id': mapping.asana_user_id,
                        'asana_user_name': mapping.asana_user_name,
                        'created_by': mapping.created_by,
                        'created_at': mapping.created_at
                    }
                return None
        except Exception as e:
            print(f"Error getting user mapping by Asana ID: {e}")
            return None

    def get_notification_preferences(self, discord_user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get notification preferences for a user."""
        try:
            with self.get_session() as session:
                pref = session.query(UserNotificationPreferences).filter(
                    UserNotificationPreferences.discord_user_id == discord_user_id,
                    UserNotificationPreferences.guild_id == guild_id
                ).first()

                if pref:
                    return {
                        'due_date_reminder': pref.due_date_reminder,
                        'assignment_notifications': pref.assignment_notifications,
                        'created_at': pref.created_at,
                        'updated_at': pref.updated_at
                    }
                return None
        except Exception as e:
            print(f"Error getting notification preferences: {e}")
            return None

    def set_notification_preferences(self, discord_user_id: int, guild_id: int,
                                   due_date_reminder: str = '1_day',
                                   assignment_notifications: str = 'enabled') -> bool:
        """Set notification preferences for a user."""
        try:
            with self.get_session() as session:
                existing = session.query(UserNotificationPreferences).filter(
                    UserNotificationPreferences.discord_user_id == discord_user_id,
                    UserNotificationPreferences.guild_id == guild_id
                ).first()

                if existing:
                    # Update existing preferences
                    existing.due_date_reminder = due_date_reminder
                    existing.assignment_notifications = assignment_notifications
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new preferences
                    prefs = UserNotificationPreferences(
                        discord_user_id=discord_user_id,
                        guild_id=guild_id,
                        due_date_reminder=due_date_reminder,
                        assignment_notifications=assignment_notifications
                    )
                    session.add(prefs)

                session.commit()
                return True
        except Exception as e:
            print(f"Error setting notification preferences: {e}")
            return False

    def get_chat_channel(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the designated chat channel for a guild."""
        try:
            with self.get_session() as session:
                channel = session.query(ChatChannel).filter(ChatChannel.guild_id == guild_id).first()
                if channel:
                    return {
                        'id': channel.id,
                        'guild_id': channel.guild_id,
                        'channel_id': channel.channel_id,
                        'channel_name': channel.channel_name,
                        'created_by': channel.created_by,
                        'created_at': channel.created_at,
                        'updated_at': channel.updated_at
                    }
                return None
        except Exception as e:
            print(f"Error getting chat channel: {e}")
            return None

    def set_chat_channel(self, guild_id: int, channel_id: int, channel_name: str, created_by: int) -> bool:
        """Set the designated chat channel for a guild."""
        try:
            with self.get_session() as session:
                existing = session.query(ChatChannel).filter(ChatChannel.guild_id == guild_id).first()

                if existing:
                    # Update existing channel
                    existing.channel_id = channel_id
                    existing.channel_name = channel_name
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new channel designation
                    channel = ChatChannel(
                        guild_id=guild_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        created_by=created_by
                    )
                    session.add(channel)

                session.commit()
                return True
        except Exception as e:
            print(f"Error setting chat channel: {e}")
            return False

    def remove_chat_channel(self, guild_id: int) -> bool:
        """Remove the designated chat channel for a guild."""
        try:
            with self.get_session() as session:
                channel = session.query(ChatChannel).filter(ChatChannel.guild_id == guild_id).first()
                if channel:
                    session.delete(channel)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error removing chat channel: {e}")
            return False

# Global database manager instance
db_manager = DatabaseManager()
