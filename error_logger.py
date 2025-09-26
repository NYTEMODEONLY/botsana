"""
Comprehensive error logging and reporting system for Botsana.
Handles logging to Discord audit channels and provides detailed error analysis.
"""

import logging
import discord
import json
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from config import bot_config
from database import db_manager, ErrorLog

logger = logging.getLogger(__name__)

class ErrorLogger:
    """Handles comprehensive error logging and reporting."""

    def __init__(self, bot):
        self.bot = bot
        self.error_counts = {}
        self.warning_counts = {}

    async def log_error(self, error: Exception, context: str = "", user_id: Optional[int] = None,
                        guild_id: Optional[int] = None, command: Optional[str] = None,
                        severity: str = "ERROR") -> bool:
        """
        Log an error with comprehensive context to both database and Discord.

        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred
            user_id: Discord user ID who triggered the error
            guild_id: Discord guild ID where the error occurred
            command: Command that was being executed
            severity: Error severity (ERROR, CRITICAL, WARNING)

        Returns:
            bool: True if logged to audit channel, False otherwise
        """
        # Create detailed error log
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'severity': severity,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'user_id': user_id,
            'guild_id': guild_id,
            'command': command
        }

        # Get stack trace
        stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        # Log to console/file
        log_message = f"[{severity}] {type(error).__name__}: {error}"
        if context:
            log_message += f" | Context: {context}"
        if user_id:
            log_message += f" | User: {user_id}"
        if guild_id:
            log_message += f" | Guild: {guild_id}"
        if command:
            log_message += f" | Command: {command}"

        if severity == "CRITICAL":
            logger.critical(log_message)
        elif severity == "WARNING":
            logger.warning(log_message)
        else:
            logger.error(log_message)

        # Save to database
        try:
            with db_manager.get_session() as session:
                if guild_id:
                    db_manager.ensure_guild_exists(guild_id)

                error_log = ErrorLog(
                    guild_id=guild_id,
                    user_id=user_id,
                    severity=severity,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    context=context,
                    command=command,
                    stack_trace=stack_trace[:5000]  # Limit stack trace length
                )
                session.add(error_log)
                session.commit()
        except Exception as db_error:
            logger.error(f"Failed to save error to database: {db_error}")

        # Send to audit log channel if configured
        success = await self._send_to_audit_channel(error_info, severity)
        return success

    async def log_command_error(self, interaction: discord.Interaction, error: Exception,
                               command_name: str) -> bool:
        """Log a command execution error."""
        return await self.log_error(
            error=error,
            context=f"Command execution failed: {command_name}",
            user_id=interaction.user.id if interaction.user else None,
            guild_id=interaction.guild.id if interaction.guild else None,
            command=command_name,
            severity="ERROR"
        )

    async def log_asana_error(self, error: Exception, operation: str,
                             task_id: Optional[str] = None, project_id: Optional[str] = None) -> bool:
        """Log an Asana API error."""
        context = f"Asana API {operation}"
        if task_id:
            context += f" | Task: {task_id}"
        if project_id:
            context += f" | Project: {project_id}"

        return await self.log_error(
            error=error,
            context=context,
            severity="ERROR"
        )

    async def log_system_event(self, event_type: str, message: str,
                              details: Optional[Dict[str, Any]] = None,
                              severity: str = "INFO") -> bool:
        """Log a system event."""
        context = f"System Event: {event_type} - {message}"
        if details:
            context += f" | Details: {json.dumps(details)}"

        return await self.log_error(
            error=Exception(message),  # Using Exception to fit the interface
            context=context,
            severity=severity
        )

    async def _send_to_audit_channel(self, error_info: Dict[str, Any], severity: str) -> bool:
        """Send error information to the configured audit log channel."""
        try:
            # Only log CRITICAL and ERROR severity to Discord
            if severity not in ["CRITICAL", "ERROR"]:
                return False

            guild_id = error_info.get('guild_id')
            if not guild_id:
                logger.warning("No guild_id provided for audit log, skipping Discord notification")
                return False

            audit_channel_id = bot_config.get_audit_log_channel(guild_id)
            if not audit_channel_id:
                logger.debug(f"No audit log channel configured for guild {guild_id}")
                return False

            channel = self.bot.get_channel(audit_channel_id)
            if not channel:
                logger.error(f"Audit log channel {audit_channel_id} not found")
                return False

            # Create error embed
            embed = await self._create_error_embed(error_info, severity)

            await channel.send(embed=embed)
            return True

        except Exception as e:
            logger.error(f"Failed to send error to audit channel: {e}")
            return False

    async def _create_error_embed(self, error_info: Dict[str, Any], severity: str) -> discord.Embed:
        """Create a detailed error embed for Discord."""
        # Color based on severity
        colors = {
            "CRITICAL": discord.Color.red(),
            "ERROR": discord.Color.orange(),
            "WARNING": discord.Color.yellow(),
            "INFO": discord.Color.blue()
        }

        embed = discord.Embed(
            title=f"🚨 {severity}: {error_info['error_type']}",
            description=error_info['error_message'],
            color=colors.get(severity, discord.Color.red()),
            timestamp=datetime.fromisoformat(error_info['timestamp'])
        )

        # Add fields
        if error_info.get('context'):
            embed.add_field(name="📋 Context", value=error_info['context'][:1024], inline=False)

        if error_info.get('command'):
            embed.add_field(name="🤖 Command", value=f"`/{error_info['command']}`", inline=True)

        if error_info.get('user_id'):
            embed.add_field(name="👤 User ID", value=str(error_info['user_id']), inline=True)

        if error_info.get('guild_id'):
            embed.add_field(name="🏠 Guild ID", value=str(error_info['guild_id']), inline=True)

        # Add footer with error ID or timestamp
        embed.set_footer(text=f"Error logged at {error_info['timestamp']}")

        return embed

    def get_error_stats(self, guild_id: Optional[int] = None) -> Dict[str, int]:
        """Get error statistics."""
        # This could be enhanced to track actual error counts
        return {
            'total_errors': len(self.error_counts),
            'total_warnings': len(self.warning_counts),
            'guild_specific': guild_id is not None
        }

# Global error logger instance (will be initialized with bot)
error_logger = None

def init_error_logger(bot):
    """Initialize the global error logger with the bot instance."""
    global error_logger
    error_logger = ErrorLogger(bot)
    return error_logger
