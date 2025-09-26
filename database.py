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
    task_templates = relationship("TaskTemplate", back_populates="guild", cascade="all, delete-orphan")
    time_entries = relationship("TimeEntry", back_populates="guild", cascade="all, delete-orphan")
    timeclock_channels = relationship("TimeclockChannel", back_populates="guild", cascade="all, delete-orphan")
    saved_searches = relationship("SavedSearch", back_populates="guild", cascade="all, delete-orphan")
    project_dashboards = relationship("ProjectDashboard", back_populates="guild", cascade="all, delete-orphan")

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

class TimeclockChannel(Base):
    """Designated channel for time tracking clock in/out."""
    __tablename__ = 'timeclock_channels'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    channel_id = Column(BigInteger, nullable=False)  # Discord channel ID
    channel_name = Column(String(255))  # Store channel name for reference
    created_by = Column(BigInteger, nullable=False)  # Discord user who set it
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="timeclock_channels")

    __table_args__ = {'sqlite_autoincrement': True}

class TaskTemplate(Base):
    """Reusable task configuration templates."""
    __tablename__ = 'task_templates'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    name = Column(String(255), nullable=False)  # Template name (e.g., "Bug Report")
    description = Column(Text)  # Template description
    task_name_template = Column(String(500), nullable=False)  # Template for task name with variables
    default_assignee = Column(String(255))  # Default assignee Asana ID
    default_project = Column(String(255))  # Default project ID
    default_notes = Column(Text)  # Default task notes/description
    due_date_offset = Column(Integer)  # Days from creation date (e.g., 7 for 1 week)
    priority = Column(String(50))  # Template priority/ordering
    is_active = Column(Boolean, default=True)  # Whether template is available for use
    usage_count = Column(Integer, default=0)  # How many times template has been used
    created_by = Column(BigInteger, nullable=False)  # Discord user who created it
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="task_templates")

    __table_args__ = {'sqlite_autoincrement': True}

class TimeEntry(Base):
    """Time tracking entries for clock in/out functionality."""
    __tablename__ = 'time_entries'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    discord_user_id = Column(BigInteger, nullable=False)
    discord_username = Column(String(255))  # Store username for reference

    # Clock times
    clock_in_time = Column(DateTime, nullable=False)
    clock_out_time = Column(DateTime, nullable=True)

    # Duration in seconds (calculated on clock out)
    duration_seconds = Column(Integer, nullable=True)

    # Time proof and notes
    time_proof_link = Column(Text, nullable=True)  # URL to proof of work
    notes = Column(Text, nullable=True)  # Optional notes

    # Status and metadata
    status = Column(String(50), default='active')  # 'active', 'completed', 'cancelled'
    asana_task_gid = Column(String(255), nullable=True)  # Associated Asana task

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="time_entries")

    __table_args__ = {'sqlite_autoincrement': True}

class SavedSearch(Base):
    """Saved task search configurations."""
    __tablename__ = 'saved_searches'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    name = Column(String(255), nullable=False)  # Search name (e.g., "My Open Tasks")
    description = Column(Text)  # Search description
    search_query = Column(String(500))  # Text search query
    assignee_user_id = Column(BigInteger, nullable=True)  # Discord user ID filter
    assignee_asana_id = Column(String(255), nullable=True)  # Asana user ID filter
    project_id = Column(String(255), nullable=True)  # Asana project ID filter
    status_filter = Column(String(50), nullable=True)  # Status filter (completed, incomplete, etc.)
    due_date_filter = Column(String(50), nullable=True)  # Due date filter (overdue, today, week, etc.)
    sort_by = Column(String(50), default='created_at')  # Sort field
    sort_order = Column(String(10), default='desc')  # Sort order (asc, desc)
    max_results = Column(Integer, default=10)  # Maximum results to return
    is_active = Column(Boolean, default=True)  # Whether search is available
    usage_count = Column(Integer, default=0)  # How many times search has been used
    created_by = Column(BigInteger, nullable=False)  # Discord user who created it
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="saved_searches")

    __table_args__ = {'sqlite_autoincrement': True}

class ProjectDashboard(Base):
    """Project dashboard configurations for visual project status."""
    __tablename__ = 'project_dashboards'

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    name = Column(String(255), nullable=False)  # Dashboard name (e.g., "Development Sprint")
    description = Column(Text)  # Dashboard description
    projects = Column(Text, nullable=False)  # JSON array of project IDs to include
    metrics = Column(Text, nullable=False)  # JSON array of metrics to display
    is_active = Column(Boolean, default=True)  # Whether dashboard is available
    refresh_interval = Column(Integer, default=3600)  # Auto-refresh interval in seconds
    usage_count = Column(Integer, default=0)  # How many times dashboard has been viewed
    created_by = Column(BigInteger, nullable=False)  # Discord user who created it
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    guild = relationship("Guild", back_populates="project_dashboards")

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

    def create_task_template(self, guild_id: int, name: str, task_name_template: str,
                           description: str = None, default_assignee: str = None,
                           default_project: str = None, default_notes: str = None,
                           due_date_offset: int = None, priority: str = "normal",
                           created_by: int = None) -> bool:
        """Create a new task template."""
        try:
            with self.get_session() as session:
                template = TaskTemplate(
                    guild_id=guild_id,
                    name=name,
                    description=description,
                    task_name_template=task_name_template,
                    default_assignee=default_assignee,
                    default_project=default_project,
                    default_notes=default_notes,
                    due_date_offset=due_date_offset,
                    priority=priority,
                    created_by=created_by
                )
                session.add(template)
                session.commit()
                return True
        except Exception as e:
            print(f"Error creating task template: {e}")
            return False

    def get_task_templates(self, guild_id: int, active_only: bool = True) -> list:
        """Get all task templates for a guild."""
        try:
            with self.get_session() as session:
                query = session.query(TaskTemplate).filter(TaskTemplate.guild_id == guild_id)
                if active_only:
                    query = query.filter(TaskTemplate.is_active == True)
                templates = query.order_by(TaskTemplate.priority, TaskTemplate.name).all()

                return [{
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'task_name_template': t.task_name_template,
                    'default_assignee': t.default_assignee,
                    'default_project': t.default_project,
                    'default_notes': t.default_notes,
                    'due_date_offset': t.due_date_offset,
                    'priority': t.priority,
                    'is_active': t.is_active,
                    'usage_count': t.usage_count,
                    'created_by': t.created_by,
                    'created_at': t.created_at,
                    'updated_at': t.updated_at
                } for t in templates]
        except Exception as e:
            print(f"Error getting task templates: {e}")
            return []

    def get_task_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific task template by ID."""
        try:
            with self.get_session() as session:
                template = session.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
                if template:
                    return {
                        'id': template.id,
                        'guild_id': template.guild_id,
                        'name': template.name,
                        'description': template.description,
                        'task_name_template': template.task_name_template,
                        'default_assignee': template.default_assignee,
                        'default_project': template.default_project,
                        'default_notes': template.default_notes,
                        'due_date_offset': template.due_date_offset,
                        'priority': template.priority,
                        'is_active': template.is_active,
                        'usage_count': template.usage_count,
                        'created_by': template.created_by,
                        'created_at': template.created_at,
                        'updated_at': template.updated_at
                    }
                return None
        except Exception as e:
            print(f"Error getting task template: {e}")
            return None

    def update_task_template_usage(self, template_id: int) -> bool:
        """Increment the usage count for a template."""
        try:
            with self.get_session() as session:
                template = session.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
                if template:
                    template.usage_count += 1
                    template.updated_at = datetime.utcnow()
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error updating template usage: {e}")
            return False

    def delete_task_template(self, template_id: int) -> bool:
        """Delete a task template."""
        try:
            with self.get_session() as session:
                template = session.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
                if template:
                    session.delete(template)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error deleting task template: {e}")
            return False

    def get_timeclock_channel(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the designated timeclock channel for a guild."""
        try:
            with self.get_session() as session:
                channel = session.query(TimeclockChannel).filter(TimeclockChannel.guild_id == guild_id).first()
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
            print(f"Error getting timeclock channel: {e}")
            return None

    def set_timeclock_channel(self, guild_id: int, channel_id: int, channel_name: str = None, created_by: int = None) -> bool:
        """Set the designated timeclock channel for a guild."""
        try:
            with self.get_session() as session:
                # Remove any existing timeclock channel for this guild
                existing = session.query(TimeclockChannel).filter(TimeclockChannel.guild_id == guild_id).first()
                if existing:
                    session.delete(existing)

                # Create new timeclock channel
                channel = TimeclockChannel(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    created_by=created_by
                )
                session.add(channel)
                session.commit()
                return True
        except Exception as e:
            print(f"Error setting timeclock channel: {e}")
            return False

    def remove_timeclock_channel(self, guild_id: int) -> bool:
        """Remove the designated timeclock channel for a guild."""
        try:
            with self.get_session() as session:
                channel = session.query(TimeclockChannel).filter(TimeclockChannel.guild_id == guild_id).first()
                if channel:
                    session.delete(channel)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error removing timeclock channel: {e}")
            return False

    def create_time_entry(self, guild_id: int, discord_user_id: int, discord_username: str = None) -> Optional[int]:
        """Create a new time entry (clock in). Returns the entry ID."""
        try:
            with self.get_session() as session:
                # Check if user already has an active time entry
                active_entry = session.query(TimeEntry).filter(
                    TimeEntry.guild_id == guild_id,
                    TimeEntry.discord_user_id == discord_user_id,
                    TimeEntry.status == 'active'
                ).first()

                if active_entry:
                    # User is already clocked in, return existing entry ID
                    return active_entry.id

                # Create new time entry
                entry = TimeEntry(
                    guild_id=guild_id,
                    discord_user_id=discord_user_id,
                    discord_username=discord_username,
                    clock_in_time=datetime.utcnow()
                )
                session.add(entry)
                session.commit()
                return entry.id

        except Exception as e:
            print(f"Error creating time entry: {e}")
            return None

    def clock_out_time_entry(self, entry_id: int, time_proof_link: str = None, notes: str = None) -> bool:
        """Clock out a time entry with optional proof and notes."""
        try:
            with self.get_session() as session:
                entry = session.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
                if not entry:
                    return False

                if entry.status != 'active':
                    return False  # Already clocked out

                now = datetime.utcnow()
                duration = int((now - entry.clock_in_time).total_seconds())

                entry.clock_out_time = now
                entry.duration_seconds = duration
                entry.status = 'completed'
                entry.time_proof_link = time_proof_link
                entry.notes = notes
                entry.updated_at = now

                session.commit()
                return True

        except Exception as e:
            print(f"Error clocking out time entry: {e}")
            return False

    def get_active_time_entry(self, guild_id: int, discord_user_id: int) -> Optional[Dict[str, Any]]:
        """Get the active time entry for a user."""
        try:
            with self.get_session() as session:
                entry = session.query(TimeEntry).filter(
                    TimeEntry.guild_id == guild_id,
                    TimeEntry.discord_user_id == discord_user_id,
                    TimeEntry.status == 'active'
                ).first()

                if entry:
                    return {
                        'id': entry.id,
                        'guild_id': entry.guild_id,
                        'discord_user_id': entry.discord_user_id,
                        'discord_username': entry.discord_username,
                        'clock_in_time': entry.clock_in_time,
                        'status': entry.status,
                        'created_at': entry.created_at
                    }
                return None

        except Exception as e:
            print(f"Error getting active time entry: {e}")
            return None

    def get_user_time_entries(self, guild_id: int, discord_user_id: int, limit: int = 10) -> list:
        """Get recent time entries for a user."""
        try:
            with self.get_session() as session:
                entries = session.query(TimeEntry).filter(
                    TimeEntry.guild_id == guild_id,
                    TimeEntry.discord_user_id == discord_user_id
                ).order_by(TimeEntry.created_at.desc()).limit(limit).all()

                return [{
                    'id': entry.id,
                    'clock_in_time': entry.clock_in_time,
                    'clock_out_time': entry.clock_out_time,
                    'duration_seconds': entry.duration_seconds,
                    'time_proof_link': entry.time_proof_link,
                    'notes': entry.notes,
                    'status': entry.status,
                    'asana_task_gid': entry.asana_task_gid,
                    'created_at': entry.created_at
                } for entry in entries]

        except Exception as e:
            print(f"Error getting user time entries: {e}")
            return []

    def get_all_active_entries(self, guild_id: int) -> list:
        """Get all active time entries for a guild."""
        try:
            with self.get_session() as session:
                entries = session.query(TimeEntry).filter(
                    TimeEntry.guild_id == guild_id,
                    TimeEntry.status == 'active'
                ).order_by(TimeEntry.clock_in_time).all()

                return [{
                    'id': entry.id,
                    'discord_user_id': entry.discord_user_id,
                    'discord_username': entry.discord_username,
                    'clock_in_time': entry.clock_in_time,
                    'created_at': entry.created_at
                } for entry in entries]

        except Exception as e:
            print(f"Error getting active entries: {e}")
            return []

    def create_saved_search(self, guild_id: int, name: str, created_by: int, **search_params) -> bool:
        """Create a new saved search."""
        try:
            with self.get_session() as session:
                search = SavedSearch(
                    guild_id=guild_id,
                    name=name,
                    created_by=created_by,
                    **search_params
                )
                session.add(search)
                session.commit()
                return True
        except Exception as e:
            print(f"Error creating saved search: {e}")
            return False

    def get_saved_searches(self, guild_id: int, active_only: bool = True) -> list:
        """Get all saved searches for a guild."""
        try:
            with self.get_session() as session:
                query = session.query(SavedSearch).filter(SavedSearch.guild_id == guild_id)
                if active_only:
                    query = query.filter(SavedSearch.is_active == True)
                searches = query.order_by(SavedSearch.name).all()

                return [{
                    'id': s.id,
                    'name': s.name,
                    'description': s.description,
                    'search_query': s.search_query,
                    'assignee_user_id': s.assignee_user_id,
                    'assignee_asana_id': s.assignee_asana_id,
                    'project_id': s.project_id,
                    'status_filter': s.status_filter,
                    'due_date_filter': s.due_date_filter,
                    'sort_by': s.sort_by,
                    'sort_order': s.sort_order,
                    'max_results': s.max_results,
                    'is_active': s.is_active,
                    'usage_count': s.usage_count,
                    'created_by': s.created_by,
                    'created_at': s.created_at,
                    'updated_at': s.updated_at
                } for s in searches]
        except Exception as e:
            print(f"Error getting saved searches: {e}")
            return []

    def get_saved_search(self, search_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific saved search by ID."""
        try:
            with self.get_session() as session:
                search = session.query(SavedSearch).filter(SavedSearch.id == search_id).first()
                if search:
                    return {
                        'id': search.id,
                        'guild_id': search.guild_id,
                        'name': search.name,
                        'description': search.description,
                        'search_query': search.search_query,
                        'assignee_user_id': search.assignee_user_id,
                        'assignee_asana_id': search.assignee_asana_id,
                        'project_id': search.project_id,
                        'status_filter': search.status_filter,
                        'due_date_filter': search.due_date_filter,
                        'sort_by': search.sort_by,
                        'sort_order': search.sort_order,
                        'max_results': search.max_results,
                        'is_active': search.is_active,
                        'usage_count': search.usage_count,
                        'created_by': search.created_by,
                        'created_at': search.created_at,
                        'updated_at': search.updated_at
                    }
                return None
        except Exception as e:
            print(f"Error getting saved search: {e}")
            return None

    def update_saved_search_usage(self, search_id: int) -> bool:
        """Increment the usage count for a saved search."""
        try:
            with self.get_session() as session:
                search = session.query(SavedSearch).filter(SavedSearch.id == search_id).first()
                if search:
                    search.usage_count += 1
                    search.updated_at = datetime.utcnow()
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error updating search usage: {e}")
            return False

    def delete_saved_search(self, search_id: int) -> bool:
        """Delete a saved search."""
        try:
            with self.get_session() as session:
                search = session.query(SavedSearch).filter(SavedSearch.id == search_id).first()
                if search:
                    session.delete(search)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error deleting saved search: {e}")
            return False

    def create_project_dashboard(self, guild_id: int, name: str, projects: list, metrics: list, created_by: int, **dashboard_params) -> bool:
        """Create a new project dashboard."""
        try:
            with self.get_session() as session:
                import json
                dashboard = ProjectDashboard(
                    guild_id=guild_id,
                    name=name,
                    projects=json.dumps(projects),
                    metrics=json.dumps(metrics),
                    created_by=created_by,
                    **dashboard_params
                )
                session.add(dashboard)
                session.commit()
                return True
        except Exception as e:
            print(f"Error creating project dashboard: {e}")
            return False

    def get_project_dashboards(self, guild_id: int, active_only: bool = True) -> list:
        """Get all project dashboards for a guild."""
        try:
            with self.get_session() as session:
                import json
                query = session.query(ProjectDashboard).filter(ProjectDashboard.guild_id == guild_id)
                if active_only:
                    query = query.filter(ProjectDashboard.is_active == True)
                dashboards = query.order_by(ProjectDashboard.name).all()

                return [{
                    'id': d.id,
                    'name': d.name,
                    'description': d.description,
                    'projects': json.loads(d.projects),
                    'metrics': json.loads(d.metrics),
                    'is_active': d.is_active,
                    'refresh_interval': d.refresh_interval,
                    'usage_count': d.usage_count,
                    'created_by': d.created_by,
                    'created_at': d.created_at,
                    'updated_at': d.updated_at
                } for d in dashboards]
        except Exception as e:
            print(f"Error getting project dashboards: {e}")
            return []

    def get_project_dashboard(self, dashboard_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific project dashboard by ID."""
        try:
            with self.get_session() as session:
                import json
                dashboard = session.query(ProjectDashboard).filter(ProjectDashboard.id == dashboard_id).first()
                if dashboard:
                    return {
                        'id': dashboard.id,
                        'guild_id': dashboard.guild_id,
                        'name': dashboard.name,
                        'description': dashboard.description,
                        'projects': json.loads(dashboard.projects),
                        'metrics': json.loads(dashboard.metrics),
                        'is_active': dashboard.is_active,
                        'refresh_interval': dashboard.refresh_interval,
                        'usage_count': dashboard.usage_count,
                        'created_by': dashboard.created_by,
                        'created_at': dashboard.created_at,
                        'updated_at': dashboard.updated_at
                    }
                return None
        except Exception as e:
            print(f"Error getting project dashboard: {e}")
            return None

    def update_dashboard_usage(self, dashboard_id: int) -> bool:
        """Increment the usage count for a dashboard."""
        try:
            with self.get_session() as session:
                dashboard = session.query(ProjectDashboard).filter(ProjectDashboard.id == dashboard_id).first()
                if dashboard:
                    dashboard.usage_count += 1
                    dashboard.updated_at = datetime.utcnow()
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error updating dashboard usage: {e}")
            return False

    def delete_project_dashboard(self, dashboard_id: int) -> bool:
        """Delete a project dashboard."""
        try:
            with self.get_session() as session:
                dashboard = session.query(ProjectDashboard).filter(ProjectDashboard.id == dashboard_id).first()
                if dashboard:
                    session.delete(dashboard)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error deleting project dashboard: {e}")
            return False

# Global database manager instance
db_manager = DatabaseManager()
