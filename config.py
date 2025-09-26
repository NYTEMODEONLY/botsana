"""
Configuration management for Botsana.
Handles persistent storage of bot settings like audit log channels.
"""

import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class BotConfig:
    """Manages bot configuration with file-based persistence."""

    def __init__(self, config_file: str = "bot_config.json"):
        self.config_file = config_file
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config file: {e}")
                return {}
        return {}

    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config file: {e}")

    def get_audit_log_channel(self, guild_id: int) -> Optional[int]:
        """Get the audit log channel ID for a guild."""
        guild_config = self._config.get('guilds', {}).get(str(guild_id), {})
        return guild_config.get('audit_log_channel')

    def set_audit_log_channel(self, guild_id: int, channel_id: int):
        """Set the audit log channel ID for a guild."""
        if 'guilds' not in self._config:
            self._config['guilds'] = {}

        if str(guild_id) not in self._config['guilds']:
            self._config['guilds'][str(guild_id)] = {}

        self._config['guilds'][str(guild_id)]['audit_log_channel'] = channel_id
        self._save_config()
        logger.info(f"Set audit log channel for guild {guild_id} to {channel_id}")

    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """Get all configuration for a guild."""
        return self._config.get('guilds', {}).get(str(guild_id), {})

    def set_guild_config(self, guild_id: int, key: str, value: Any):
        """Set a configuration value for a guild."""
        if 'guilds' not in self._config:
            self._config['guilds'] = {}

        if str(guild_id) not in self._config['guilds']:
            self._config['guilds'][str(guild_id)] = {}

        self._config['guilds'][str(guild_id)][key] = value
        self._save_config()

    def get_global_config(self, key: str, default=None):
        """Get a global configuration value."""
        return self._config.get('global', {}).get(key, default)

    def set_global_config(self, key: str, value: Any):
        """Set a global configuration value."""
        if 'global' not in self._config:
            self._config['global'] = {}

        self._config['global'][key] = value
        self._save_config()

# Global configuration instance
bot_config = BotConfig()
