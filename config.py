"""
Configuration management for Botsana.
Handles persistent storage of bot settings using database.
"""

import json
import logging
from typing import Optional, Dict, Any
from database import db_manager, GuildConfig, GlobalConfig

logger = logging.getLogger(__name__)

class BotConfig:
    """Manages bot configuration with database persistence."""

    def get_audit_log_channel(self, guild_id: int) -> Optional[int]:
        """Get the audit log channel ID for a guild."""
        try:
            with db_manager.get_session() as session:
                config = session.query(GuildConfig).filter(
                    GuildConfig.guild_id == guild_id,
                    GuildConfig.key == 'audit_log_channel'
                ).first()

                if config and config.value:
                    return int(config.value)
                return None
        except Exception as e:
            logger.error(f"Failed to get audit log channel for guild {guild_id}: {e}")
            return None

    def set_audit_log_channel(self, guild_id: int, channel_id: int):
        """Set the audit log channel ID for a guild."""
        try:
            with db_manager.get_session() as session:
                # Ensure guild exists
                db_manager.ensure_guild_exists(guild_id)

                # Check if config already exists
                config = session.query(GuildConfig).filter(
                    GuildConfig.guild_id == guild_id,
                    GuildConfig.key == 'audit_log_channel'
                ).first()

                if config:
                    config.value = str(channel_id)
                else:
                    config = GuildConfig(
                        guild_id=guild_id,
                        key='audit_log_channel',
                        value=str(channel_id)
                    )
                    session.add(config)

                session.commit()
                logger.info(f"Set audit log channel for guild {guild_id} to {channel_id}")

        except Exception as e:
            logger.error(f"Failed to set audit log channel for guild {guild_id}: {e}")
            raise

    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """Get all configuration for a guild."""
        try:
            with db_manager.get_session() as session:
                configs = session.query(GuildConfig).filter(
                    GuildConfig.guild_id == guild_id
                ).all()

                config_dict = {}
                for config in configs:
                    try:
                        # Try to parse as JSON first
                        config_dict[config.key] = json.loads(config.value)
                    except (json.JSONDecodeError, TypeError):
                        # If not JSON, store as string
                        config_dict[config.key] = config.value

                return config_dict

        except Exception as e:
            logger.error(f"Failed to get guild config for guild {guild_id}: {e}")
            return {}

    def set_guild_config(self, guild_id: int, key: str, value: Any):
        """Set a configuration value for a guild."""
        try:
            with db_manager.get_session() as session:
                # Ensure guild exists
                db_manager.ensure_guild_exists(guild_id)

                # Convert value to string (JSON if complex)
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)

                # Check if config already exists
                config = session.query(GuildConfig).filter(
                    GuildConfig.guild_id == guild_id,
                    GuildConfig.key == key
                ).first()

                if config:
                    config.value = value_str
                else:
                    config = GuildConfig(
                        guild_id=guild_id,
                        key=key,
                        value=value_str
                    )
                    session.add(config)

                session.commit()
                logger.info(f"Set guild config {key} for guild {guild_id}")

        except Exception as e:
            logger.error(f"Failed to set guild config {key} for guild {guild_id}: {e}")
            raise

    def get_global_config(self, key: str, default=None):
        """Get a global configuration value."""
        try:
            with db_manager.get_session() as session:
                config = session.query(GlobalConfig).filter(
                    GlobalConfig.key == key
                ).first()

                if config and config.value:
                    try:
                        return json.loads(config.value)
                    except (json.JSONDecodeError, TypeError):
                        return config.value
                return default

        except Exception as e:
            logger.error(f"Failed to get global config {key}: {e}")
            return default

    def set_global_config(self, key: str, value: Any):
        """Set a global configuration value."""
        try:
            with db_manager.get_session() as session:
                # Convert value to string (JSON if complex)
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)

                # Check if config already exists
                config = session.query(GlobalConfig).filter(
                    GlobalConfig.key == key
                ).first()

                if config:
                    config.value = value_str
                else:
                    config = GlobalConfig(
                        key=key,
                        value=value_str
                    )
                    session.add(config)

                session.commit()
                logger.info(f"Set global config {key}")

        except Exception as e:
            logger.error(f"Failed to set global config {key}: {e}")
            raise

# Global configuration instance
bot_config = BotConfig()
