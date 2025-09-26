"""
Botsana - Discord Asana Bot
A Discord bot for managing Asana tasks directly from Discord.
"""

import os
import discord
from discord import app_commands
from discord.ext import commands
import asana
from dotenv import load_dotenv
import logging
from typing import Optional, List, Dict, Any
import asyncio
from asana.error import AsanaError, NotFoundError, ForbiddenError
from flask import Flask, request, jsonify
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json
import re
from datetime import datetime, timedelta
import httpx
from config import bot_config
from error_logger import init_error_logger
from database import db_manager, ErrorLog
from sqlalchemy import text

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_APPLICATION_ID = os.getenv('DISCORD_APPLICATION_ID')
ASANA_ACCESS_TOKEN = os.getenv('ASANA_ACCESS_TOKEN')
ASANA_WORKSPACE_ID = os.getenv('ASANA_WORKSPACE_ID')
ASANA_DEFAULT_PROJECT_ID = os.getenv('ASANA_DEFAULT_PROJECT_ID')
XAI_API_KEY = os.getenv('XAI_API_KEY')

# Validate required environment variables
required_vars = ['DISCORD_TOKEN', 'ASANA_ACCESS_TOKEN', 'ASANA_WORKSPACE_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Discord bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize Asana client
asana_client = asana.Client.access_token(ASANA_ACCESS_TOKEN)

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('------')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} command(s)')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use `/help` to see available commands.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    else:
        logger.error(f'Command error: {error}')
        await ctx.send(f"An error occurred: {str(error)}")

@bot.event
async def on_message(message):
    """Handle messages in designated chat channels."""
    # Ignore messages from bots (including ourselves)
    if message.author.bot:
        return

    # Check if this is in a designated chat channel
    chat_channel_config = db_manager.get_chat_channel(message.guild.id) if message.guild else None
    if not chat_channel_config or message.channel.id != chat_channel_config['channel_id']:
        return

    # Check if the bot is mentioned
    if bot.user not in message.mentions:
        return

    # Process the natural language task creation request
    await handle_chat_channel_request(message)

# Placeholder for Asana API functions (to be implemented)
class AsanaManager:
    """Manages Asana API interactions."""

    def __init__(self, client, workspace_id, default_project_id=None):
        self.client = client
        self.workspace_id = workspace_id
        self.default_project_id = default_project_id

    async def create_task(self, name: str, project_id: Optional[str] = None,
                         assignee: Optional[str] = None, due_date: Optional[str] = None,
                         notes: Optional[str] = None, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """Create a new task in Asana."""
        try:
            # Use default project if none specified
            if project_id is None:
                # First try guild-specific default project
                if guild_id:
                    guild_config = bot_config.get_guild_config(guild_id)
                    project_id = guild_config.get('default_project_id')

                # Fall back to environment variable default
                if not project_id:
                    project_id = self.default_project_id

                if not project_id:
                    raise ValueError("No project ID specified and no default project set. Use /set-default-project to set a default project.")

            # Prepare task data
            task_data = {
                'name': name,
                'projects': [project_id],
                'workspace': self.workspace_id
            }

            if assignee:
                task_data['assignee'] = assignee
            if due_date:
                task_data['due_on'] = due_date
            if notes:
                task_data['notes'] = notes

            # Create the task
            result = self.client.tasks.create_task(task_data)
            logger.info(f"Created task: {result['gid']} - {result['name']}")
            return result

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise

    async def update_task(self, task_id: str, name: Optional[str] = None,
                         assignee: Optional[str] = None, due_date: Optional[str] = None,
                         notes: Optional[str] = None, completed: Optional[bool] = None) -> Dict[str, Any]:
        """Update an existing task."""
        try:
            # Prepare update data
            update_data = {}

            if name is not None:
                update_data['name'] = name
            if assignee is not None:
                update_data['assignee'] = assignee
            if due_date is not None:
                update_data['due_on'] = due_date
            if notes is not None:
                update_data['notes'] = notes
            if completed is not None:
                update_data['completed'] = completed

            if not update_data:
                raise ValueError("No fields to update")

            # Update the task
            result = self.client.tasks.update_task(task_id, update_data)
            logger.info(f"Updated task: {task_id}")
            return result

        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            raise

    async def complete_task(self, task_id: str) -> Dict[str, Any]:
        """Mark a task as completed."""
        try:
            # Mark task as completed
            result = self.client.tasks.update_task(task_id, {'completed': True})
            logger.info(f"Completed task: {task_id}")
            return result

        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}")
            raise

    async def list_tasks(self, project_id: Optional[str] = None, assignee: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tasks from a project or assigned to a user."""
        try:
            tasks = []

            if project_id:
                # List tasks in a specific project
                result = self.client.tasks.get_tasks_for_project(project_id, opt_fields='name,due_on,assignee.name,completed,notes')
                tasks = [task for task in result if task is not None]
            elif assignee:
                # List tasks assigned to a user
                result = self.client.tasks.get_tasks_for_user(assignee, workspace=self.workspace_id, opt_fields='name,due_on,assignee.name,completed,notes,projects.name')
                tasks = [task for task in result if task is not None]
            else:
                # List all tasks in workspace (limited)
                if self.default_project_id:
                    result = self.client.tasks.get_tasks_for_project(self.default_project_id, opt_fields='name,due_on,assignee.name,completed,notes')
                    tasks = [task for task in result if task is not None]
                else:
                    raise ValueError("No project or assignee specified, and no default project set")

            logger.info(f"Retrieved {len(tasks)} valid tasks from Asana API")
            return tasks

        except Exception as e:
            logger.error(f"Error listing tasks: {e}")
            raise

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        try:
            # Delete the task
            self.client.tasks.delete_task(task_id)
            logger.info(f"Deleted task: {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            raise

    async def get_workspace_users(self) -> List[Dict[str, Any]]:
        """Get all users in the workspace."""
        try:
            # Get all users in the workspace
            result = self.client.users.get_users(workspace=self.workspace_id, opt_fields='name,email')
            users = list(result)
            logger.info(f"Retrieved {len(users)} users from Asana workspace")
            return users

        except Exception as e:
            logger.error(f"Error retrieving workspace users: {e}")
            raise

    async def search_tasks(self, query: str, project_id: Optional[str] = None, assignee: Optional[str] = None,
                          limit: int = 10) -> List[Dict[str, Any]]:
        """Search for tasks by name across projects or in a specific project."""
        try:
            tasks = []

            if project_id:
                # Search in specific project
                result = self.client.tasks.get_tasks_for_project(
                    project_id,
                    opt_fields='name,due_on,assignee.name,completed,notes,projects.name'
                )
                project_tasks = list(result)
                # Filter by query
                tasks = [task for task in project_tasks
                        if query.lower() in task.get('name', '').lower() and not task.get('completed', False)]
            else:
                # Search across all accessible projects (this is more complex in Asana API)
                # For now, search in default project and any projects the user has access to
                projects_to_search = []

                if self.default_project_id:
                    projects_to_search.append(self.default_project_id)

                # Try to get user's projects (this might require different API calls)
                try:
                    if assignee:
                        # If we have an assignee, we can get their tasks
                        user_tasks = self.client.tasks.get_tasks_for_user(
                            assignee,
                            workspace=self.workspace_id,
                            opt_fields='name,due_on,assignee.name,completed,notes,projects.name'
                        )
                        user_task_list = list(user_tasks)
                        tasks = [task for task in user_task_list
                                if query.lower() in task.get('name', '').lower() and not task.get('completed', False)]
                    else:
                        # Search in default project only for now
                        if self.default_project_id:
                            result = self.client.tasks.get_tasks_for_project(
                                self.default_project_id,
                                opt_fields='name,due_on,assignee.name,completed,notes,projects.name'
                            )
                            project_tasks = list(result)
                            tasks = [task for task in project_tasks
                                    if query.lower() in task.get('name', '').lower() and not task.get('completed', False)]
                except Exception as e:
                    logger.warning(f"Could not search across projects: {e}")
                    # Fall back to default project
                    if self.default_project_id:
                        result = self.client.tasks.get_tasks_for_project(
                            self.default_project_id,
                            opt_fields='name,due_on,assignee.name,completed,notes,projects.name'
                        )
                        project_tasks = list(result)
                        tasks = [task for task in project_tasks
                                if query.lower() in task.get('name', '').lower() and not task.get('completed', False)]

            # Limit results
            tasks = tasks[:limit]
            logger.info(f"Found {len(tasks)} tasks matching '{query}'")
            return tasks

        except Exception as e:
            logger.error(f"Error searching tasks: {e}")
            raise

    async def find_task_by_name(self, name: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a single task by exact name match."""
        try:
            tasks = await self.search_tasks(name, project_id, limit=5)

            # Look for exact match first
            for task in tasks:
                if task.get('name', '').strip().lower() == name.strip().lower():
                    return task

            # If no exact match, return the first partial match
            return tasks[0] if tasks else None

        except Exception as e:
            logger.error(f"Error finding task by name: {e}")
            return None

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get a specific task by ID."""
        try:
            # Get the task with detailed information
            result = self.client.tasks.get_task(task_id, opt_fields='name,due_on,assignee.name,completed,notes,projects.name')
            logger.info(f"Retrieved task: {task_id}")
            return result

        except Exception as e:
            logger.error(f"Error retrieving task {task_id}: {e}")
            raise

# Initialize Asana manager
asana_manager = AsanaManager(asana_client, ASANA_WORKSPACE_ID, ASANA_DEFAULT_PROJECT_ID)

# Discord UI Components
class AsanaUserSelect(discord.ui.Select):
    """Select menu for choosing Asana users to map to Discord users."""

    def __init__(self, discord_user: discord.Member, asana_users: List[Dict[str, Any]]):
        self.discord_user = discord_user
        self.asana_users = asana_users

        # Create options for the select menu
        options = []
        for user in asana_users[:25]:  # Discord limits to 25 options
            user_name = user.get('name', 'Unknown User')
            user_email = user.get('email', '')
            user_id = user.get('gid', user.get('id', 'unknown'))

            # Create a clean label (truncate if too long)
            label = user_name[:25] if len(user_name) <= 25 else user_name[:22] + "..."

            # Create description with email if available
            description = f"ID: {user_id}"
            if user_email:
                description += f" | {user_email}"

            # Truncate description if too long
            if len(description) > 50:
                description = description[:47] + "..."

            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=user_id
            ))

        super().__init__(
            placeholder="Select the Asana user to map...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle the user selection."""
        selected_asana_user_id = self.values[0]

        # Find the selected Asana user details
        selected_user = None
        for user in self.asana_users:
            if user.get('gid', user.get('id')) == selected_asana_user_id:
                selected_user = user
                break

        if not selected_user:
            await interaction.response.send_message("❌ Error: Selected user not found.", ephemeral=True)
            return

        asana_user_name = selected_user.get('name', 'Unknown User')

        # Create the user mapping
        success = db_manager.set_user_mapping(
            guild_id=interaction.guild.id,
            discord_user_id=self.discord_user.id,
            asana_user_id=selected_asana_user_id,
            discord_username=str(self.discord_user),
            asana_user_name=asana_user_name,
            created_by=interaction.user.id
        )

        if success:
            embed = discord.Embed(
                title="✅ User Mapping Created",
                description=f"Successfully mapped {self.discord_user.mention} to Asana user **{asana_user_name}**",
                color=discord.Color.green()
            )

            embed.add_field(
                name="Discord User",
                value=f"{self.discord_user.mention}\n`{self.discord_user.id}`",
                inline=True
            )

            embed.add_field(
                name="Asana User",
                value=f"`{asana_user_name}`\nID: `{selected_asana_user_id}`",
                inline=True
            )

            embed.set_footer(text="Tasks created by this user will now auto-assign to their Asana account")
        else:
            embed = discord.Embed(
                title="❌ Mapping Failed",
                description="Failed to create user mapping. Please try again.",
                color=discord.Color.red()
            )

        # Update the message with the result
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except discord.errors.InteractionResponded:
            # If interaction was already responded to, send a followup
            await interaction.followup.send(embed=embed, ephemeral=True)

class AsanaUserSelectView(discord.ui.View):
    """View containing the Asana user select menu."""

    def __init__(self, discord_user: discord.Member, asana_users: List[Dict[str, Any]]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.add_item(AsanaUserSelect(discord_user, asana_users))

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="⏰ Selection Timed Out",
            description="The user selection menu has expired. Please run `/map-user` again to try mapping this user.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass  # Message might have been deleted

# Initialize Flask app for webhooks
flask_app = Flask(__name__)

# Scheduler for periodic tasks
scheduler = AsyncIOScheduler()

# Audit channel configuration
AUDIT_CHANNELS = {
    'taskmaster': '📋 All task creations and deletions',
    'updates': '🔄 Task updates, comments, status changes, and assignments',
    'completed': '✅ Completed tasks',
    'due-soon': '⏰ Tasks due within 24 hours',
    'overdue': '🚨 Currently overdue tasks',
    'missed-deadline': '💀 Tasks that missed their deadline',
    'new-projects': '📁 New project creations',
    'attachments': '📎 Files added to tasks'
}

class AuditManager:
    """Manages audit channels and webhook events."""

    def __init__(self):
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', 'botsana_secret_2024')
        self.audit_channels = {}
        self.webhooks = []

    async def setup_audit_channels(self, guild: discord.Guild) -> discord.CategoryChannel:
        """Create the Botsana audit category and channels."""
        # Check if category already exists
        category = discord.utils.get(guild.categories, name="🤖 Botsana")

        if category:
            # Category exists, try to find existing channels
            await self._populate_existing_channels(guild, category)
        else:
            # Create new category
            category = await guild.create_category("🤖 Botsana")

        # Ensure all required channels exist
        for channel_name, description in AUDIT_CHANNELS.items():
            if channel_name not in self.audit_channels:
                # Channel doesn't exist or isn't accessible, create it
                try:
                    channel = await guild.create_text_channel(
                        channel_name,
                        category=category,
                        topic=description
                    )
                    self.audit_channels[channel_name] = channel
                except discord.Forbidden:
                    logger.error(f"Cannot create channel {channel_name}: Missing permissions")
                except Exception as e:
                    logger.error(f"Failed to create channel {channel_name}: {e}")

        return category

    async def _populate_existing_channels(self, guild: discord.Guild, category: discord.CategoryChannel):
        """Populate audit_channels dict with existing channels in the category."""
        for channel in category.channels:
            if isinstance(channel, discord.TextChannel):
                # Check if this is one of our audit channels
                for audit_name in AUDIT_CHANNELS.keys():
                    if channel.name == audit_name:
                        self.audit_channels[audit_name] = channel
                        break

    async def register_webhooks(self, base_url: str) -> bool:
        """Register Asana webhooks for the workspace."""
        webhook_url = f"{base_url}/webhook"

        # Register webhook for all task events in the workspace
        webhook_data = {
            'resource': ASANA_WORKSPACE_ID,
            'target': webhook_url,
            'filters': [
                {'resource_type': 'task', 'action': 'added'},
                {'resource_type': 'task', 'action': 'removed'},
                {'resource_type': 'task', 'action': 'changed'},
                {'resource_type': 'project', 'action': 'added'}
            ]
        }

        try:
            result = asana_client.webhooks.create_webhook(webhook_data)
            self.webhooks.append(result)
            logger.info(f"Registered webhook: {result['gid']} for URL: {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to register webhook: {e}")
            return False

    async def send_audit_embed(self, channel_name: str, embed: discord.Embed):
        """Send an embed to a specific audit channel."""
        if channel_name in self.audit_channels:
            channel = self.audit_channels[channel_name]
            try:
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send audit embed to {channel_name}: {e}")

    async def check_missed_deadlines(self):
        """Check for missed deadlines and send notifications."""
        try:
            # Get all tasks with due dates
            tasks = await asana_manager.list_tasks()

            yesterday = datetime.now() - timedelta(days=1)
            missed_tasks = []

            for task in tasks:
                if task.get('due_on'):
                    due_date = datetime.fromisoformat(task['due_on'])
                    if due_date.date() == yesterday.date() and not task.get('completed'):
                        missed_tasks.append(task)

            if missed_tasks:
                embed = discord.Embed(
                    title="💀 Missed Deadlines",
                    description=f"Found {len(missed_tasks)} tasks that missed their deadline yesterday",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )

                for task in missed_tasks[:10]:  # Limit to 10 tasks
                    assignee = task.get('assignee', {}).get('name', 'Unassigned')
                    embed.add_field(
                        name=f"📋 {task['name']}",
                        value=f"👤 {assignee} | 📅 Was due {task['due_on']} | ID: `{task['gid']}`",
                        inline=False
                    )

                await self.send_audit_embed('missed-deadline', embed)

        except Exception as e:
            logger.error(f"Error checking missed deadlines: {e}")

    async def check_due_soon(self):
        """Check for tasks due soon and send personalized reminders."""
        try:
            # Get all tasks with due dates
            tasks = await asana_manager.list_tasks()
            now = datetime.now()

            # Check different reminder intervals
            reminder_intervals = {
                '1_hour': timedelta(hours=1),
                '1_day': timedelta(days=1),
                '1_week': timedelta(days=7)
            }

            # Group tasks by assignee for personalized notifications
            tasks_by_assignee = {}

            for task in tasks:
                if task.get('due_on') and not task.get('completed'):
                    due_date = datetime.fromisoformat(task['due_on'])

                    # Skip if already past due
                    if due_date <= now:
                        continue

                    assignee_id = task.get('assignee', {}).get('gid')
                    if assignee_id:
                        if assignee_id not in tasks_by_assignee:
                            tasks_by_assignee[assignee_id] = []
                        tasks_by_assignee[assignee_id].append(task)

            # Send personalized reminders for each assignee
            for asana_assignee_id, assignee_tasks in tasks_by_assignee.items():
                for reminder_type, time_delta in reminder_intervals.items():
                    reminder_threshold = now + time_delta

                    # Find tasks that match this reminder interval
                    matching_tasks = []
                    for task in assignee_tasks:
                        due_date = datetime.fromisoformat(task['due_on'])
                        if due_date <= reminder_threshold:
                            matching_tasks.append(task)

                    # Send reminders for tasks in this interval
                    for task in matching_tasks:
                        await send_due_date_reminder(task, asana_assignee_id, reminder_type)

            # Also send the general audit channel notification (legacy behavior)
            tomorrow = now + timedelta(days=1)
            due_soon_tasks = []

            for task in tasks:
                if task.get('due_on') and not task.get('completed'):
                    due_date = datetime.fromisoformat(task['due_on'])
                    if due_date <= tomorrow and due_date > now:
                        due_soon_tasks.append(task)

            if due_soon_tasks:
                embed = discord.Embed(
                    title="⏰ Tasks Due Soon",
                    description=f"{len(due_soon_tasks)} tasks due within 24 hours",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )

                for task in due_soon_tasks[:10]:
                    assignee = task.get('assignee', {}).get('name', 'Unassigned')
                    due_time = datetime.fromisoformat(task['due_on'])
                    embed.add_field(
                        name=f"📋 {task['name']}",
                        value=f"👤 {assignee} | 📅 Due {due_time.strftime('%Y-%m-%d %H:%M')} | ID: `{task['gid']}`",
                        inline=False
                    )

                await self.send_audit_embed('due-soon', embed)

        except Exception as e:
            logger.error(f"Error checking due soon tasks: {e}")

# Initialize audit manager
audit_manager = AuditManager()

# Initialize error logger (will be set in main)
error_logger = None

# Flask webhook endpoints
@flask_app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming Asana webhooks."""
    try:
        # Verify webhook secret if provided
        secret = request.headers.get('X-Hook-Secret')
        if secret:
            # This is a webhook registration request
            response = jsonify({'status': 'ok'})
            response.headers['X-Hook-Secret'] = secret
            return response

        # Get webhook data
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400

        # Process webhook events asynchronously
        asyncio.run(process_webhook_events(data))

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

async def process_webhook_events(data):
    """Process webhook events and send to appropriate audit channels."""
    try:
        events = data.get('events', [])

        for event in events:
            event_type = event.get('type')
            resource_type = event.get('resource', {}).get('resource_type')
            action = event.get('action')

            if resource_type == 'task':
                await process_task_event(event)
            elif resource_type == 'project':
                await process_project_event(event)

    except Exception as e:
        logger.error(f"Error processing webhook events: {e}")

async def process_task_event(event):
    """Process task-related webhook events."""
    try:
        action = event.get('action')
        task_gid = event.get('resource', {}).get('gid')

        if not task_gid:
            return

        # Get task details
        task = await asana_manager.get_task(task_gid)

        if action == 'added':
            # Task created
            embed = discord.Embed(
                title="📋 Task Created",
                description=f"**{task['name']}**",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            if task.get('assignee'):
                embed.add_field(name="👤 Assignee", value=task['assignee']['name'], inline=True)
            if task.get('due_on'):
                embed.add_field(name="📅 Due Date", value=task['due_on'], inline=True)
            if task.get('projects'):
                project_names = [p['name'] for p in task['projects']]
                embed.add_field(name="📁 Projects", value=", ".join(project_names), inline=False)

            embed.set_footer(text=f"Task ID: {task['gid']}")
            await audit_manager.send_audit_embed('taskmaster', embed)

        elif action == 'removed':
            # Task deleted
            embed = discord.Embed(
                title="🗑️ Task Deleted",
                description=f"**{task['name']}** was deleted",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Task ID: {task_gid}")
            await audit_manager.send_audit_embed('taskmaster', embed)

        elif action == 'changed':
            # Task updated - check what changed
            changes = event.get('change', {})

            if changes.get('field') == 'completed' and changes.get('new_value') is True:
                # Task completed
                embed = discord.Embed(
                    title="✅ Task Completed",
                    description=f"**{task['name']}** has been completed!",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )

                if task.get('assignee'):
                    embed.add_field(name="👤 Completed by", value=task['assignee']['name'], inline=True)

                embed.set_footer(text=f"Task ID: {task['gid']}")
                await audit_manager.send_audit_embed('completed', embed)

            elif changes.get('field') == 'assignee':
                # Assignment changed
                old_assignee = changes.get('old_value', {}).get('name', 'Unassigned') if changes.get('old_value') else 'Unassigned'
                new_assignee = changes.get('new_value', {}).get('name', 'Unassigned') if changes.get('new_value') else 'Unassigned'

                embed = discord.Embed(
                    title="👥 Task Assignment Changed",
                    description=f"**{task['name']}**",
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )

                embed.add_field(name="📋 Task", value=task['name'], inline=False)
                embed.add_field(name="⬅️ From", value=old_assignee, inline=True)
                embed.add_field(name="➡️ To", value=new_assignee, inline=True)

                embed.set_footer(text=f"Task ID: {task['gid']}")
                await audit_manager.send_audit_embed('updates', embed)

                # Send assignment notification to the new assignee if enabled
                if changes.get('new_value') and new_assignee != 'Unassigned':
                    await send_assignment_notification(task, changes.get('new_value', {}).get('gid'))

            elif changes.get('field') in ['name', 'notes', 'due_on']:
                # Other task updates
                field_names = {
                    'name': '📝 Name',
                    'notes': '📝 Notes',
                    'due_on': '📅 Due Date'
                }

                embed = discord.Embed(
                    title=f"🔄 Task Updated - {field_names.get(changes.get('field'), 'Field')}",
                    description=f"**{task['name']}**",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )

                if changes.get('old_value'):
                    embed.add_field(name="⬅️ Old Value", value=str(changes['old_value'])[:1024], inline=False)
                if changes.get('new_value'):
                    embed.add_field(name="➡️ New Value", value=str(changes['new_value'])[:1024], inline=False)

                embed.set_footer(text=f"Task ID: {task['gid']}")
                await audit_manager.send_audit_embed('updates', embed)

    except Exception as e:
        logger.error(f"Error processing task event: {e}")

async def process_project_event(event):
    """Process project-related webhook events."""
    try:
        action = event.get('action')

        if action == 'added':
            # New project created
            project_gid = event.get('resource', {}).get('gid')

            # Get project details
            project = asana_client.projects.get_project(project_gid)

            embed = discord.Embed(
                title="📁 New Project Created",
                description=f"**{project['name']}**",
                color=discord.Color.teal(),
                timestamp=datetime.now()
            )

            embed.add_field(name="📋 Description", value=project.get('notes', 'No description')[:1024], inline=False)
            embed.set_footer(text=f"Project ID: {project['gid']}")

            await audit_manager.send_audit_embed('new-projects', embed)

    except Exception as e:
        logger.error(f"Error processing project event: {e}")

def run_flask_app():
    """Run Flask app in a separate thread."""
    flask_app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False, use_reloader=False)

def handle_asana_error(error: Exception) -> str:
    """Convert Asana API errors to user-friendly messages."""
    if isinstance(error, NotFoundError):
        return "❌ Task or resource not found. Please check the ID and try again."
    elif isinstance(error, ForbiddenError):
        return "❌ Access denied. You don't have permission to perform this action."
    elif isinstance(error, AsanaError):
        if hasattr(error, 'status') and error.status == 400:
            return "❌ Invalid request. Please check your input parameters."
        elif hasattr(error, 'status') and error.status == 429:
            return "❌ Rate limit exceeded. Please try again in a moment."
        elif hasattr(error, 'status') and error.status >= 500:
            return "❌ Asana service is temporarily unavailable. Please try again later."
        else:
            return f"❌ Asana API error: {str(error)}"
    elif isinstance(error, ValueError):
        return f"❌ Invalid input: {str(error)}"
    elif isinstance(error, ConnectionError):
        return "❌ Network error. Please check your connection and try again."
    else:
        logger.error(f"Unexpected error: {error}")
        return f"❌ An unexpected error occurred: {str(error)}"

# Slash commands

@bot.tree.command(name="create-task", description="Create a new task in Asana")
@app_commands.describe(
    name="Task name (required)",
    project="Project ID (optional, uses default if not specified)",
    assignee="Discord user to assign task to (optional, auto-assigns to you if not specified)",
    due_date="Due date in YYYY-MM-DD format (optional)",
    notes="Task notes/description (optional)"
)
async def create_task_command(
    interaction: discord.Interaction,
    name: str,
    project: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Create a new task in Asana."""
    await interaction.response.defer()

    try:
        # Resolve assignee - handle Discord user mentions and auto-assignment
        asana_assignee = None
        assignee_info = None

        if assignee:
            # User specified a Discord user - look up their Asana mapping
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
            if user_mapping:
                asana_assignee = user_mapping['asana_user_id']
                assignee_info = f"{assignee.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"
            else:
                # No mapping found for the mentioned user
                embed = discord.Embed(
                    title="❌ User Not Mapped",
                    description=f"{assignee.mention} is not mapped to an Asana user. An administrator needs to run `/map-user` first.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="How to Map Users",
                    value=f"Use `/map-user @{assignee.name} asana_user_id` to create the mapping.",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                return
        else:
            # No assignee specified - auto-assign to task creator
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            if user_mapping:
                asana_assignee = user_mapping['asana_user_id']
                assignee_info = f"Auto-assigned to {interaction.user.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"
            else:
                assignee_info = "No assignee (user not mapped to Asana)"

        task = await asana_manager.create_task(
            name=name,
            project_id=project,
            assignee=asana_assignee,
            due_date=due_date,
            notes=notes,
            guild_id=interaction.guild.id
        )

        embed = discord.Embed(
            title="✅ Task Created",
            description=f"**{task['name']}**",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        embed.add_field(name="📋 Task ID", value=f"`{task['gid']}`", inline=True)

        # Show project information
        if task.get('projects') and len(task['projects']) > 0:
            project_names = [p['name'] for p in task['projects']]
            embed.add_field(name="📁 Project", value=", ".join(project_names), inline=True)
        else:
            embed.add_field(name="📁 Project", value="Default project", inline=True)

        if task.get('assignee'):
            asana_assignee_name = task['assignee']['name']
            assignee_display = f"{asana_assignee_name}"
            if assignee_info and "Auto-assigned" in assignee_info:
                assignee_display += " (Auto-assigned)"
            embed.add_field(name="👤 Assignee", value=assignee_display, inline=True)
        elif assignee_info:
            # Show Discord mapping info even if Asana doesn't return assignee data
            embed.add_field(name="👤 Assignee Info", value=assignee_info, inline=False)

        if task.get('due_on'):
            embed.add_field(name="📅 Due Date", value=task['due_on'], inline=False)

        if task.get('notes'):
            # Truncate notes if too long
            notes = task['notes'][:200] + "..." if len(task['notes']) > 200 else task['notes']
            embed.add_field(name="📝 Notes", value=notes, inline=False)

        embed.set_footer(text=f"Created via Botsana • Task ID: {task['gid']}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        # Log error to audit channel
        await error_logger.log_command_error(interaction, e, "create-task")

        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Creating Task",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="update-task", description="Update an existing task in Asana")
@app_commands.describe(
    task="Task ID or task name to update (required)",
    name="New task name (optional)",
    assignee="New assignee Discord user (optional)",
    due_date="New due date in YYYY-MM-DD format (optional)",
    notes="New task notes/description (optional)"
)
async def update_task_command(
    interaction: discord.Interaction,
    task: str,
    name: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Update an existing task in Asana."""
    await interaction.response.defer()

    try:
        # Resolve assignee - handle Discord user mentions
        asana_assignee = None
        if assignee:
            # Special case: if assignee is the same as the command runner, use their mapping
            if assignee.id == interaction.user.id:
                user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
                if user_mapping:
                    asana_assignee = user_mapping['asana_user_id']
                else:
                    embed = discord.Embed(
                        title="❌ You Are Not Mapped",
                        description="You need to be mapped to an Asana user first. Use `/map-user @yourname` to map yourself.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
            else:
                # Regular user mapping lookup
                user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
                if user_mapping:
                    asana_assignee = user_mapping['asana_user_id']
                else:
                    embed = discord.Embed(
                        title="❌ User Not Mapped",
                        description=f"{assignee.mention} is not mapped to an Asana user. Use `/map-user @{assignee.name}` first.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return

        # Validate that at least one update parameter is provided
        if not any([name, assignee, due_date, notes]):
            embed = discord.Embed(
                title="❌ No Updates Specified",
                description="Please specify what you want to update in the task.",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="Available Update Options:",
                value="• `name` - Change the task name\n• `assignee` - Assign to a Discord user (@mention)\n• `due_date` - Set due date (YYYY-MM-DD)\n• `notes` - Update task description",
                inline=False
            )
            embed.add_field(
                name="Examples:",
                value="• `/update-task task:\"fix bug\" assignee:@developer`\n• `/update-task task:\"review code\" assignee:@nyte` (assign to yourself)\n• `/update-task task:\"task name\" due_date:\"2025-12-31\"`\n• `/update-task task:\"task name\" name:\"New task name\"`",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return

        # Find the task by ID or name
        task_id = None
        task_data = None

        # Check if it's a valid task ID (numeric)
        if task.isdigit():
            try:
                task_data = await asana_manager.get_task(task)
                task_id = task
            except Exception:
                pass  # Not a valid task ID, try searching by name

        # If not a valid ID or task not found, search by name
        if not task_data:
            # Get the user's Asana ID for searching their tasks
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            assignee_id = user_mapping['asana_user_id'] if user_mapping else None

            # Search for the task by name
            matching_tasks = await asana_manager.search_tasks(task, assignee=assignee_id, limit=5)

            if not matching_tasks:
                embed = discord.Embed(
                    title="❌ Task Not Found",
                    description=f"No active task found matching '{task}'.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 Try:",
                    value="• Use the exact task name\n• Use the task ID if you know it\n• Check that the task isn't already completed",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                return

            if len(matching_tasks) > 1:
                # Multiple matches - show options
                embed = discord.Embed(
                    title="🎯 Multiple Tasks Found",
                    description=f"Found {len(matching_tasks)} tasks matching '{task}'. Please be more specific or use the task ID.",
                    color=discord.Color.yellow()
                )

                for i, t in enumerate(matching_tasks[:3], 1):
                    task_name = t.get('name', 'Unknown Task')
                    task_id_match = t.get('gid', t.get('id', 'Unknown'))
                    embed.add_field(
                        name=f"Option {i}",
                        value=f"**{task_name}**\nID: `{task_id_match}`",
                        inline=True
                    )

                await interaction.followup.send(embed=embed)
                return

            # Single match
            task_data = matching_tasks[0]
            task_id = task_data.get('gid', task_data.get('id'))

        # Update the task
        updated_task = await asana_manager.update_task(
            task_id=task_id,
            name=name,
            assignee=asana_assignee,
            due_date=due_date,
            notes=notes
        )

        embed = discord.Embed(
            title="✅ Task Updated",
            description=f"**{updated_task['name']}**",
            color=discord.Color.blue()
        )

        embed.add_field(name="Task ID", value=updated_task.get('gid', task_id), inline=True)
        if updated_task.get('due_on'):
            embed.add_field(name="Due Date", value=updated_task['due_on'], inline=True)
        if updated_task.get('assignee'):
            embed.add_field(name="Assignee", value=updated_task['assignee']['name'], inline=True)

        # Show what was updated
        updates = []
        if name:
            updates.append(f"📝 Name: {name}")
        if assignee:
            updates.append(f"👤 Assignee: {assignee.mention}")
        if due_date:
            updates.append(f"📅 Due Date: {due_date}")
        if notes:
            updates.append(f"📋 Notes: Updated")

        if updates:
            embed.add_field(
                name="Changes Made",
                value="\n".join(updates),
                inline=False
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Updating Task",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="complete-task", description="Mark a task as completed in Asana")
@app_commands.describe(
    task="Task ID or task name to complete (required)"
)
async def complete_task_command(
    interaction: discord.Interaction,
    task: str
):
    """Mark a task as completed in Asana."""
    await interaction.response.defer()

    try:
        # Try to parse as task ID first
        task_id = None
        task_data = None

        # Check if it's a valid task ID (numeric)
        if task.isdigit():
            try:
                task_data = await asana_manager.get_task(task)
                task_id = task
            except Exception:
                pass  # Not a valid task ID, try searching by name

        # If not a valid ID or task not found, search by name
        if not task_data:
            # Get the user's Asana ID for searching their tasks
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            assignee_id = user_mapping['asana_user_id'] if user_mapping else None

            # Search for the task by name
            matching_tasks = await asana_manager.search_tasks(task, assignee=assignee_id, limit=5)

            if not matching_tasks:
                embed = discord.Embed(
                    title="❌ Task Not Found",
                    description=f"No active task found matching '{task}'.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 Try:",
                    value="• Use the exact task name\n• Use the task ID if you know it\n• Check that the task isn't already completed",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                return

            if len(matching_tasks) > 1:
                # Multiple matches - show options
                embed = discord.Embed(
                    title="🎯 Multiple Tasks Found",
                    description=f"Found {len(matching_tasks)} tasks matching '{task}'. Please be more specific or use the task ID.",
                    color=discord.Color.yellow()
                )

                for i, t in enumerate(matching_tasks[:3], 1):
                    task_name = t.get('name', 'Unknown Task')
                    task_id_match = t.get('gid', t.get('id', 'Unknown'))
                    embed.add_field(
                        name=f"Option {i}",
                        value=f"**{task_name}**\nID: `{task_id_match}`",
                        inline=True
                    )

                await interaction.followup.send(embed=embed)
                return

            # Single match
            task_data = matching_tasks[0]
            task_id = task_data.get('gid', task_data.get('id'))

        # Complete the task
        completed_task = await asana_manager.complete_task(task_id)

        embed = discord.Embed(
            title="✅ Task Completed",
            description=f"**{completed_task['name']}** has been marked as completed!",
            color=discord.Color.green()
        )

        embed.add_field(name="Task ID", value=completed_task.get('gid', task_id), inline=True)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Completing Task",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="list-tasks", description="List tasks from a project in Asana")
@app_commands.describe(
    project="Project ID to list tasks from (optional, uses default if not specified)",
    limit="Maximum number of tasks to show (optional, default 10)"
)
async def list_tasks_command(
    interaction: discord.Interaction,
    project: Optional[str] = None,
    limit: Optional[int] = 10
):
    """List tasks from a project in Asana."""
    await interaction.response.defer()

    try:
        if limit and limit > 25:
            limit = 25  # Discord embed limits

        tasks = await asana_manager.list_tasks(project_id=project)

        if not tasks:
            embed = discord.Embed(
                title="📋 No Tasks Found",
                description="No tasks found in the specified project.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 Tasks",
            description=f"Found {len(tasks)} tasks",
            color=discord.Color.blue()
        )

        # Filter out None tasks and ensure proper structure
        valid_tasks = [task for task in tasks if task is not None and isinstance(task, dict)]
        displayed_tasks = valid_tasks[:limit] if limit else valid_tasks

        if not displayed_tasks:
            embed = discord.Embed(
                title="📋 No Valid Tasks Found",
                description="Found tasks but none have valid data. This might be an API issue.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)
            return

        for i, task in enumerate(displayed_tasks, 1):
            # Safely access task properties
            task_name = task.get('name', 'Unnamed Task')
            completed = task.get('completed', False)
            status = "✅" if completed else "⏳"

            assignee_data = task.get('assignee')
            assignee = assignee_data.get('name', 'Unassigned') if assignee_data else 'Unassigned'

            due_date = task.get('due_on', 'No due date')
            task_id = task.get('gid', task.get('id', 'Unknown'))

            task_info = f"{status} **{task_name}**\n👤 {assignee} | 📅 {due_date} | ID: `{task_id}`"
            if len(task_info) > 1024:
                task_info = task_info[:1021] + "..."

            embed.add_field(
                name=f"Task {i}",
                value=task_info,
                inline=False
            )

        if len(tasks) > limit:
            embed.set_footer(text=f"Showing first {limit} tasks. Total: {len(tasks)}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Listing Tasks",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="delete-task", description="Delete a task from Asana")
@app_commands.describe(
    task="Task ID or task name to delete (required)"
)
async def delete_task_command(
    interaction: discord.Interaction,
    task: str
):
    """Delete a task from Asana."""
    await interaction.response.defer()

    try:
        # Find the task by ID or name
        task_id = None
        task_data = None

        # Check if it's a valid task ID (numeric)
        if task.isdigit():
            try:
                task_data = await asana_manager.get_task(task)
                task_id = task
            except Exception:
                pass  # Not a valid task ID, try searching by name

        # If not a valid ID or task not found, search by name
        if not task_data:
            # Get the user's Asana ID for searching their tasks
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            assignee_id = user_mapping['asana_user_id'] if user_mapping else None

            # Search for the task by name
            matching_tasks = await asana_manager.search_tasks(task, assignee=assignee_id, limit=5)

            if not matching_tasks:
                embed = discord.Embed(
                    title="❌ Task Not Found",
                    description=f"No active task found matching '{task}'.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 Try:",
                    value="• Use the exact task name\n• Use the task ID if you know it\n• Check that the task isn't already completed",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                return

            if len(matching_tasks) > 1:
                # Multiple matches - show options
                embed = discord.Embed(
                    title="🎯 Multiple Tasks Found",
                    description=f"Found {len(matching_tasks)} tasks matching '{task}'. Please be more specific or use the task ID.",
                    color=discord.Color.yellow()
                )

                for i, t in enumerate(matching_tasks[:3], 1):
                    task_name = t.get('name', 'Unknown Task')
                    task_id_match = t.get('gid', t.get('id', 'Unknown'))
                    embed.add_field(
                        name=f"Option {i}",
                        value=f"**{task_name}**\nID: `{task_id_match}`",
                        inline=True
                    )

                await interaction.followup.send(embed=embed)
                return

            # Single match
            task_data = matching_tasks[0]
            task_id = task_data.get('gid', task_data.get('id'))

        # Get task details before deletion for confirmation
        task_details = await asana_manager.get_task(task_id)
        task_name = task_details.get('name', 'Unknown Task')

        # Delete the task
        await asana_manager.delete_task(task_id)

        embed = discord.Embed(
            title="🗑️ Task Deleted",
            description=f"**{task_name}** has been deleted from Asana.",
            color=discord.Color.red()
        )

        embed.add_field(name="Task ID", value=task_id, inline=True)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Deleting Task",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="view-task", description="View details of a specific task")
@app_commands.describe(
    task_id="Task ID to view (required)"
)
async def view_task_command(
    interaction: discord.Interaction,
    task_id: str
):
    """View details of a specific task."""
    await interaction.response.defer()

    try:
        task = await asana_manager.get_task(task_id)

        if not task:
            embed = discord.Embed(
                title="❌ Task Not Found",
                description=f"No task found with ID `{task_id}`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        task_name = task.get('name', 'Unnamed Task')
        task_id_display = task.get('gid', task.get('id', task_id))

        embed = discord.Embed(
            title=f"📋 {task_name}",
            color=discord.Color.blue()
        )

        embed.add_field(name="Task ID", value=task_id_display, inline=True)
        embed.add_field(name="Status", value="✅ Completed" if task.get('completed') else "⏳ In Progress", inline=True)

        assignee_data = task.get('assignee')
        if assignee_data and isinstance(assignee_data, dict):
            embed.add_field(name="Assignee", value=assignee_data.get('name', 'Unknown'), inline=True)

        if task.get('due_on'):
            embed.add_field(name="Due Date", value=task['due_on'], inline=True)

        projects_data = task.get('projects')
        if projects_data and isinstance(projects_data, list):
            project_names = [p.get('name', 'Unknown Project') for p in projects_data if p]
            if project_names:
                embed.add_field(name="Projects", value=", ".join(project_names), inline=False)

        if task.get('notes'):
            notes = task['notes']
            if len(notes) > 1024:
                notes = notes[:1021] + "..."
            embed.add_field(name="Notes", value=notes, inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        error_embed = discord.Embed(
            title="❌ Error Viewing Task",
            description=error_message,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="help", description="Show available commands and usage")
async def help_command(interaction: discord.Interaction):
    """Show help information for Botsana."""
    embed = discord.Embed(
        title="🤖 Botsana - Discord Asana Bot",
        description="Manage your Asana tasks directly from Discord!",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="🤖 AI-Powered Chat Channel",
        value="""Designate a channel for natural language task creation
• Mention @Botsana in the chat channel to create tasks
• Use conversational language like "Create a task to fix the login bug due tomorrow"
• Supports due dates, assignments, and project mentions
• AI-powered parsing with confirmation""",
        inline=False
    )

    embed.add_field(
        name="📝 Task Management",
        value="""`create-task` - Create a new task
`update-task` - Update existing tasks
`complete-task` - Mark tasks as completed
`view-task` - View task details
`list-tasks` - List tasks from a project
`delete-task` - Delete tasks""",
        inline=False
    )

    embed.add_field(
        name="⚙️ Bulk Operations",
        value="""`bulk-select` - Select multiple tasks for batch operations
• Complete multiple tasks at once
• Reassign tasks to different users
• Update due dates in bulk
• Search and select from task lists""",
        inline=False
    )

    embed.add_field(
        name="📋 Task Templates",
        value="""`create-template` - Create reusable task configurations
`list-templates` - Browse available task templates
`use-template` - Create tasks from saved templates
`delete-template` - Remove templates (Admin only)""",
        inline=False
    )

    embed.add_field(
        name="🔍 Advanced Search",
        value="""`search-tasks` - Search tasks with advanced filters
`save-search` - Save search configurations for reuse
`load-search` - Run a previously saved search
`list-searches` - Browse all saved searches
`delete-search` - Delete saved searches""",
        inline=False
    )

    embed.add_field(
        name="🕐 Time Tracking",
        value="""`clock-in` - Start tracking work time
`clock-out` - End session with time proof link
`time-status` - Check your current time tracking status
`time-history` - View your recent time entries
`timeclock-status` - View all active sessions (Admin only)""",
        inline=False
    )

    embed.add_field(
        name="⚙️ Timeclock Channel (Admin Only)",
        value="""`set-timeclock-channel` - Designate channel for time tracking
`remove-timeclock-channel` - Remove timeclock channel restriction""",
        inline=False
    )

    embed.add_field(
        name="⚙️ Configuration (Admin Only)",
        value="""`set-chat-channel` - Designate a channel for AI chat
`remove-chat-channel` - Disable AI chat channel
`set-default-project` - Set default Asana project
`set-audit-log` - Configure error logging channel
`audit-setup` - Set up audit channels for monitoring""",
        inline=False
    )

    embed.add_field(
        name="🔔 Notifications",
        value="""`notification-settings` - Manage your notification preferences
• Customize due date reminders (1 hour, 1 day, 1 week)
• Control assignment notifications
• Receive personalized DM alerts
• Opt-in/opt-out of different notification types""",
        inline=False
    )

    embed.add_field(
        name="💡 Tips",
        value="""• Task IDs are long numbers (e.g., 1234567890123456)
• Project IDs can be found in Asana URLs
• Dates should be in YYYY-MM-DD format
• Use the default project if you don't specify one""",
        inline=False
    )

    embed.add_field(
        name="🔧 Configuration",
        value="Contact your bot administrator to configure default projects and workspace settings.",
        inline=False
    )

    embed.set_footer(text="For more help, check the README or contact support")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="audit-setup", description="Set up Botsana audit channels for monitoring Asana activity")
@discord.app_commands.checks.has_permissions(administrator=True)
async def audit_setup_command(interaction: discord.Interaction):
    """Set up the Botsana audit system with dedicated channels."""
    await interaction.response.defer()

    try:
        # Create audit channels (this will repair if needed)
        category = await audit_manager.setup_audit_channels(interaction.guild)

        # Check how many channels we actually have
        working_channels = len(audit_manager.audit_channels)
        total_channels = len(AUDIT_CHANNELS)

        # Register webhooks
        base_url = os.getenv('HEROKU_URL', f"https://{os.getenv('HEROKU_APP_NAME', 'botsana-discord-bot')}.herokuapp.com")
        webhook_result = await audit_manager.register_webhooks(base_url)

        # Start periodic tasks
        scheduler.add_job(audit_manager.check_missed_deadlines, 'cron', hour=9, minute=0)  # Daily at 9 AM
        scheduler.add_job(audit_manager.check_due_soon, 'interval', hours=1)  # Every hour

        if not scheduler.running:
            scheduler.start()

        # Create response embed
        if working_channels == total_channels:
            embed = discord.Embed(
                title="✅ Audit System Setup Complete",
                description="Botsana audit channels have been created and configured!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="⚠️ Audit System Setup Partial",
                description=f"Audit system setup completed, but only {working_channels}/{total_channels} channels are accessible.",
                color=discord.Color.yellow()
            )

        embed.add_field(
            name="📁 Category",
            value=category.mention,
            inline=True
        )

        embed.add_field(
            name="📺 Working Channels",
            value=f"{working_channels}/{total_channels}",
            inline=True
        )

        # Show webhook status
        if webhook_result:
            embed.add_field(
                name="🔗 Webhooks",
                value=f"✅ Registered {len(audit_manager.webhooks)} webhook(s)",
                inline=True
            )
        else:
            embed.add_field(
                name="🔗 Webhooks",
                value="⚠️ Failed to register webhooks",
                inline=True
            )

        channels_list = "\n".join([f"• `{name}` - {'✅' if name in audit_manager.audit_channels else '❌'} {desc}" for name, desc in AUDIT_CHANNELS.items()])
        embed.add_field(
            name="📋 Channel Status",
            value=channels_list,
            inline=False
        )

        embed.set_footer(text="Use /test-audit to verify all channels are working properly")

        await interaction.followup.send(embed=embed)

    except discord.Forbidden:
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="I don't have permission to create channels. Please give me the 'Manage Channels' permission.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_message = handle_asana_error(e)
        embed = discord.Embed(
            title="❌ Setup Failed",
            description=f"Failed to set up audit system: {error_message}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@audit_setup_command.error
async def audit_setup_error(interaction: discord.Interaction, error):
    """Handle audit setup command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to set up the audit system.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Audit setup error: {error}")

@bot.tree.command(name="set-audit-log", description="Set the audit log channel for error reporting")
@discord.app_commands.checks.has_permissions(administrator=True)
async def set_audit_log_command(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the audit log channel for comprehensive error reporting."""
    await interaction.response.defer()

    try:
        # Validate that the bot can send messages to this channel
        test_permissions = channel.permissions_for(interaction.guild.me)
        if not test_permissions.send_messages or not test_permissions.embed_links:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="I don't have permission to send messages and embeds in that channel. Please check my permissions.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Set the audit log channel
        bot_config.set_audit_log_channel(interaction.guild.id, channel.id)

        embed = discord.Embed(
            title="✅ Audit Log Channel Set",
            description=f"Error logging has been configured to send to {channel.mention}",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📺 Channel",
            value=channel.mention,
            inline=True
        )

        embed.add_field(
            name="🔧 Configuration",
            value="Critical errors and system events will now be logged here",
            inline=False
        )

        embed.set_footer(text="Use /audit-setup to create the full audit system")

        await interaction.followup.send(embed=embed)

        # Send a test message to the audit log channel
        test_embed = discord.Embed(
            title="🧪 Audit Log Test",
            description="This channel has been configured for Botsana error logging.",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        test_embed.add_field(name="👑 Configured by", value=interaction.user.mention, inline=True)
        test_embed.add_field(name="🏠 Guild", value=interaction.guild.name, inline=True)

        await channel.send(embed=test_embed)

    except Exception as e:
        if error_logger:
            await error_logger.log_command_error(interaction, e, "set-audit-log")

        embed = discord.Embed(
            title="❌ Configuration Failed",
            description=f"Failed to set audit log channel: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@set_audit_log_command.error
async def set_audit_log_error(interaction: discord.Interaction, error):
    """Handle set audit log command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to configure the audit log channel.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        if error_logger:
            await error_logger.log_error(error, "set-audit-log command error", severity="ERROR")
        logger.error(f"Set audit log error: {error}")

@bot.tree.command(name="set-default-project", description="Set the default Asana project for task creation")
@discord.app_commands.checks.has_permissions(administrator=True)
async def set_default_project_command(interaction: discord.Interaction, project_id: str):
    """Set the default Asana project ID for this server."""
    await interaction.response.defer()

    try:
        # Validate the project ID by attempting to get project info
        try:
            project = asana_client.projects.get_project(project_id)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Invalid Project ID",
                description=f"Could not find project with ID `{project_id}`. Please check the ID and try again.",
                color=discord.Color.red()
            )
            embed.add_field(name="🔍 Error", value=str(e), inline=False)
            await interaction.followup.send(embed=embed)
            return

        # Set the default project for this guild
        bot_config.set_guild_config(interaction.guild.id, 'default_project_id', project_id)

        embed = discord.Embed(
            title="✅ Default Project Set",
            description=f"Default project has been set to **{project['name']}**",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📁 Project",
            value=f"{project['name']} (`{project_id}`)",
            inline=True
        )

        embed.add_field(
            name="🎯 Impact",
            value="All new tasks created without specifying a project will use this default",
            inline=False
        )

        await interaction.followup.send(embed=embed)

        # Log the configuration change
        await error_logger.log_system_event(
            "config_change",
            f"Default project set to {project['name']} ({project_id})",
            {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "project_id": project_id},
            "INFO"
        )

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "set-default-project")

        embed = discord.Embed(
            title="❌ Configuration Failed",
            description=f"Failed to set default project: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@set_default_project_command.error
async def set_default_project_error(interaction: discord.Interaction, error):
    """Handle set default project command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to set the default project.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        if error_logger:
            await error_logger.log_error(error, "set-default-project command error", severity="ERROR")
        logger.error(f"Set default project error: {error}")

@bot.tree.command(name="view-error-logs", description="View recent error logs (Admin only)")
@discord.app_commands.checks.has_permissions(administrator=True)
async def view_error_logs_command(interaction: discord.Interaction, limit: Optional[int] = 10):
    """View recent error logs for this server."""
    await interaction.response.defer()

    try:
        if limit > 25:
            limit = 25  # Discord embed limits

        with db_manager.get_session() as session:
            error_logs = session.query(ErrorLog).filter(
                ErrorLog.guild_id == interaction.guild.id
            ).order_by(ErrorLog.created_at.desc()).limit(limit).all()

        if not error_logs:
            embed = discord.Embed(
                title="📋 Error Logs",
                description="No error logs found for this server.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 Recent Error Logs",
            description=f"Showing last {len(error_logs)} errors",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

        for i, error_log in enumerate(error_logs[:10], 1):  # Limit to 10 in embed
            severity_emoji = {
                "CRITICAL": "🚨",
                "ERROR": "❌",
                "WARNING": "⚠️",
                "INFO": "ℹ️"
            }.get(error_log.severity, "❓")

            timestamp = error_log.created_at.strftime("%m/%d %H:%M")
            command_info = f" (`/{error_log.command}`)" if error_log.command else ""

            error_summary = f"{severity_emoji} **{error_log.error_type}**{command_info}\n"
            error_summary += f"📅 {timestamp} | 👤 <@{error_log.user_id}>\n"
            error_summary += f"💬 {error_log.error_message[:100]}{'...' if len(error_log.error_message) > 100 else ''}"

            embed.add_field(
                name=f"Error #{i}",
                value=error_summary,
                inline=False
            )

        if len(error_logs) > 10:
            embed.set_footer(text=f"Showing first 10 of {len(error_logs)} total errors")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "view-error-logs")

        embed = discord.Embed(
            title="❌ Failed to Load Error Logs",
            description=f"Could not retrieve error logs: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@view_error_logs_command.error
async def view_error_logs_error(interaction: discord.Interaction, error):
    """Handle view error logs command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to view error logs.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"View error logs error: {error}")

@bot.tree.command(name="test-audit", description="Test the audit system by sending a test message")
@discord.app_commands.checks.has_permissions(administrator=True)
async def test_audit_command(interaction: discord.Interaction):
    """Test the audit system by sending a test message to all audit channels."""
    await interaction.response.defer()

    try:
        embed = discord.Embed(
            title="🧪 Audit System Test",
            description="Testing Botsana audit channels...",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.add_field(
            name="👤 Tester",
            value=interaction.user.mention,
            inline=True
        )

        embed.add_field(
            name="🏠 Server",
            value=interaction.guild.name,
            inline=True
        )

        embed.add_field(
            name="⏰ Time",
            value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            inline=True
        )

        # Test each audit channel
        test_results = {}
        for channel_name, description in AUDIT_CHANNELS.items():
            try:
                if channel_name in audit_manager.audit_channels:
                    success = await audit_manager.send_audit_embed(channel_name, embed)
                    test_results[channel_name] = "✅" if success else "❌"
                else:
                    test_results[channel_name] = "❌ (Not found)"
            except Exception as e:
                test_results[channel_name] = f"❌ ({str(e)[:20]}...)"

        # Create results summary
        result_embed = discord.Embed(
            title="🧪 Audit Test Results",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        results_text = ""
        for channel_name, result in test_results.items():
            results_text += f"• `{channel_name}`: {result}\n"

        result_embed.add_field(
            name="📺 Channel Tests",
            value=results_text,
            inline=False
        )

        # Check webhook status
        webhook_count = len(audit_manager.webhooks) if hasattr(audit_manager, 'webhooks') else 0
        result_embed.add_field(
            name="🔗 Webhook Status",
            value=f"Registered: {webhook_count} webhook(s)",
            inline=True
        )

        result_embed.set_footer(text="Audit system test completed")

        await interaction.followup.send(embed=result_embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "test-audit")

        embed = discord.Embed(
            title="❌ Audit Test Failed",
            description=f"Failed to test audit system: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@test_audit_command.error
async def test_audit_error(interaction: discord.Interaction, error):
    """Handle test audit command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to test the audit system.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Test audit error: {error}")

@bot.tree.command(name="repair-audit", description="Repair/reset the audit system")
@discord.app_commands.checks.has_permissions(administrator=True)
async def repair_audit_command(interaction: discord.Interaction):
    """Repair or reset the audit system by clearing the channel cache and re-setup."""
    await interaction.response.defer()

    try:
        # Clear the audit channels cache
        audit_manager.audit_channels.clear()

        # Re-run setup
        category = await audit_manager.setup_audit_channels(interaction.guild)

        working_channels = len(audit_manager.audit_channels)
        total_channels = len(AUDIT_CHANNELS)

        embed = discord.Embed(
            title="🔧 Audit System Repaired",
            description="Audit system has been reset and repaired.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📁 Category",
            value=category.mention,
            inline=True
        )

        embed.add_field(
            name="📺 Channels Repaired",
            value=f"{working_channels}/{total_channels}",
            inline=True
        )

        # Show status of each channel
        channel_status = []
        for name in AUDIT_CHANNELS.keys():
            status = "✅" if name in audit_manager.audit_channels else "❌"
            channel_status.append(f"• `{name}`: {status}")

        embed.add_field(
            name="📋 Channel Status",
            value="\n".join(channel_status),
            inline=False
        )

        embed.set_footer(text="Run /test-audit to verify everything is working")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "repair-audit")

        embed = discord.Embed(
            title="❌ Repair Failed",
            description=f"Failed to repair audit system: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@repair_audit_command.error
async def repair_audit_error(interaction: discord.Interaction, error):
    """Handle repair audit command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to repair the audit system.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Repair audit error: {error}")

@bot.tree.command(name="map-user", description="Map a Discord user to an Asana user for task assignment")
@discord.app_commands.checks.has_permissions(administrator=True)
async def map_user_command(interaction: discord.Interaction, discord_user: discord.Member):
    """Map a Discord user to an Asana user for automatic task assignment."""
    await interaction.response.defer()

    try:
        # Check if user is already mapped
        existing_mapping = db_manager.get_user_mapping(interaction.guild.id, discord_user.id)
        if existing_mapping:
            embed = discord.Embed(
                title="⚠️ User Already Mapped",
                description=f"{discord_user.mention} is already mapped to Asana user `{existing_mapping['asana_user_name'] or existing_mapping['asana_user_id']}`",
                color=discord.Color.yellow()
            )
            embed.add_field(
                name="Options",
                value="• Use `/unmap-user @user` to remove the current mapping first\n• Or map a different Discord user",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return

        # Fetch all Asana users
        embed = discord.Embed(
            title="🔄 Loading Asana Users...",
            description="Fetching users from your Asana workspace...",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

        asana_users = await asana_manager.get_workspace_users()

        if not asana_users:
            error_embed = discord.Embed(
                title="❌ No Asana Users Found",
                description="Could not retrieve any users from your Asana workspace. Please check your Asana credentials and permissions.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=error_embed)
            return

        # Create the user selection interface
        view = AsanaUserSelectView(discord_user, asana_users)

        selection_embed = discord.Embed(
            title=f"👥 Select Asana User for {discord_user.display_name}",
            description=f"Choose the Asana user to map to {discord_user.mention}.\n\nFound **{len(asana_users)}** user(s) in your Asana workspace.",
            color=discord.Color.blue()
        )

        selection_embed.add_field(
            name="📋 Instructions",
            value="• Select the correct Asana user from the dropdown below\n• The menu will expire in 5 minutes\n• Only users with Asana access will appear",
            inline=False
        )

        # Store the message reference for the view
        view.message = await interaction.edit_original_response(embed=selection_embed, view=view)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "map-user")

        embed = discord.Embed(
            title="❌ Failed to Load Users",
            description=f"An error occurred while fetching Asana users: {str(e)}\n\nPlease check your Asana credentials and try again.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@map_user_command.error
async def map_user_error(interaction: discord.Interaction, error):
    """Handle map user command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to map users.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Map user error: {error}")

@bot.tree.command(name="unmap-user", description="Remove a Discord user's Asana mapping")
@discord.app_commands.checks.has_permissions(administrator=True)
async def unmap_user_command(interaction: discord.Interaction, discord_user: discord.Member):
    """Remove a Discord user's Asana mapping."""
    await interaction.response.defer()

    try:
        success = db_manager.remove_user_mapping(interaction.guild.id, discord_user.id)

        if success:
            embed = discord.Embed(
                title="✅ User Mapping Removed",
                description=f"Successfully removed Asana mapping for {discord_user.mention}",
                color=discord.Color.green()
            )

            embed.add_field(
                name="Discord User",
                value=f"{discord_user.mention}\n`{discord_user.id}`",
                inline=True
            )

            embed.set_footer(text="This user will no longer have automatic task assignment")
        else:
            embed = discord.Embed(
                title="⚠️ No Mapping Found",
                description=f"No Asana mapping found for {discord_user.mention}",
                color=discord.Color.yellow()
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "unmap-user")

        embed = discord.Embed(
            title="❌ Unmapping Failed",
            description=f"An error occurred while removing the user mapping: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@unmap_user_command.error
async def unmap_user_error(interaction: discord.Interaction, error):
    """Handle unmap user command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to unmap users.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Unmap user error: {error}")

@bot.tree.command(name="list-mappings", description="List all Discord-Asana user mappings")
@discord.app_commands.checks.has_permissions(administrator=True)
async def list_mappings_command(interaction: discord.Interaction):
    """List all user mappings for this server."""
    await interaction.response.defer()

    try:
        mappings = db_manager.list_user_mappings(interaction.guild.id)

        if not mappings:
            embed = discord.Embed(
                title="📋 User Mappings",
                description="No user mappings have been configured for this server.",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="How to Add Mappings",
                value="Use `/map-user @user asana_user_id` to map Discord users to Asana users.",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 User Mappings",
            description=f"Found {len(mappings)} user mapping(s) for this server.",
            color=discord.Color.blue()
        )

        for i, mapping in enumerate(mappings, 1):
            # Try to get the Discord user object
            discord_user = interaction.guild.get_member(mapping['discord_user_id'])
            user_mention = discord_user.mention if discord_user else f"Unknown User ({mapping['discord_user_id']})"

            mapping_info = f"**Discord:** {user_mention}\n**Asana:** `{mapping['asana_user_name'] or 'Unknown'}`\n**ID:** `{mapping['asana_user_id']}`"

            embed.add_field(
                name=f"Mapping {i}",
                value=mapping_info,
                inline=True
            )

        embed.set_footer(text="These mappings enable automatic task assignment")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "list-mappings")

        embed = discord.Embed(
            title="❌ Failed to List Mappings",
            description=f"An error occurred while listing user mappings: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@list_mappings_command.error
async def list_mappings_error(interaction: discord.Interaction, error):
    """Handle list mappings command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to list user mappings.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"List mappings error: {error}")

@bot.tree.command(name="set-chat-channel", description="Designate a channel for natural language task creation")
@discord.app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="The channel where the bot will respond to natural language task requests"
)
async def set_chat_channel_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    """Designate a channel for natural language task creation."""
    await interaction.response.defer()

    try:
        # Validate that the bot can send messages to this channel
        test_permissions = channel.permissions_for(interaction.guild.me)
        if not test_permissions.send_messages or not test_permissions.embed_links:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="I don't have permission to send messages and embeds in that channel. Please check my permissions.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Set the chat channel
        success = db_manager.set_chat_channel(
            guild_id=interaction.guild.id,
            channel_id=channel.id,
            channel_name=channel.name,
            created_by=interaction.user.id
        )

        if success:
            embed = discord.Embed(
                title="✅ Chat Channel Set",
                description=f"Natural language task creation has been enabled in {channel.mention}",
                color=discord.Color.green()
            )

            embed.add_field(
                name="🎯 How It Works",
                value="• Mention me (@Botsana) in that channel to create tasks\n• Use natural language like 'Create a task to fix the login bug due tomorrow'\n• I'll parse your request and ask for confirmation before creating tasks",
                inline=False
            )

            embed.add_field(
                name="📺 Channel",
                value=channel.mention,
                inline=True
            )

            embed.add_field(
                name="👑 Set by",
                value=interaction.user.mention,
                inline=True
            )

            embed.set_footer(text="Use /remove-chat-channel to disable this feature")

            await interaction.followup.send(embed=embed)

            # Send a welcome message to the channel
            welcome_embed = discord.Embed(
                title="🤖 Botsana Chat Channel Activated!",
                description="This channel is now designated for natural language task creation.",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )

            welcome_embed.add_field(
                name="💬 How to Use",
                value="• Mention me (@Botsana) to create tasks\n• Example: `@Botsana Create a task to fix the login bug due tomorrow`\n• I'll parse your request and ask for confirmation",
                inline=False
            )

            welcome_embed.set_footer(text="Set by " + str(interaction.user))

            await channel.send(embed=welcome_embed)

            # Log the configuration change
            await error_logger.log_system_event(
                "config_change",
                f"Chat channel set to {channel.name} ({channel.id})",
                {"guild_id": interaction.guild.id, "user_id": interaction.user.id, "channel_id": channel.id},
                "INFO"
            )

        else:
            embed = discord.Embed(
                title="❌ Configuration Failed",
                description="Failed to set the chat channel. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "set-chat-channel")

        embed = discord.Embed(
            title="❌ Configuration Failed",
            description=f"Failed to set chat channel: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@set_chat_channel_command.error
async def set_chat_channel_error(interaction: discord.Interaction, error):
    """Handle set chat channel command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to set the chat channel.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Set chat channel error: {error}")

@bot.tree.command(name="remove-chat-channel", description="Remove the designated chat channel")
@discord.app_commands.checks.has_permissions(administrator=True)
async def remove_chat_channel_command(interaction: discord.Interaction):
    """Remove the designated chat channel."""
    await interaction.response.defer()

    try:
        success = db_manager.remove_chat_channel(interaction.guild.id)

        if success:
            embed = discord.Embed(
                title="✅ Chat Channel Removed",
                description="Natural language task creation has been disabled. The bot will no longer respond to mentions in the designated channel.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="⚠️ No Chat Channel Set",
                description="No chat channel was configured for this server.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "remove-chat-channel")

        embed = discord.Embed(
            title="❌ Removal Failed",
            description=f"Failed to remove chat channel: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@remove_chat_channel_command.error
async def remove_chat_channel_error(interaction: discord.Interaction, error):
    """Handle remove chat channel command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to remove the chat channel.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Remove chat channel error: {error}")

@bot.tree.command(name="set-timeclock-channel", description="Designate a channel for time tracking (Admin only)")
@discord.app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="The channel to designate for time tracking commands"
)
async def set_timeclock_channel_command(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the designated channel for time tracking."""
    await interaction.response.defer()

    try:
        # Check if a timeclock channel is already set
        existing = db_manager.get_timeclock_channel(interaction.guild.id)

        success = db_manager.set_timeclock_channel(
            guild_id=interaction.guild.id,
            channel_id=channel.id,
            channel_name=channel.name,
            created_by=interaction.user.id
        )

        if success:
            embed = discord.Embed(
                title="✅ Timeclock Channel Set",
                description=f"Time tracking commands are now restricted to {channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="📍 Channel",
                value=f"{channel.mention} (`#{channel.name}`)",
                inline=True
            )

            embed.add_field(
                name="👤 Set By",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="🕐 Commands Available",
                value="• `/clock-in`\n• `/clock-out`\n• `/time-status`\n• `/time-history`",
                inline=False
            )

            if existing:
                embed.add_field(
                    name="ℹ️ Previous Channel",
                    value=f"Replaced previous designation",
                    inline=True
                )

            embed.set_footer(text="Only these commands will work in the designated timeclock channel")

            await interaction.followup.send(embed=embed)

            # Log the channel setting
            await error_logger.log_system_event(
                "timeclock_channel_set",
                f"Timeclock channel set to #{channel.name} by {interaction.user.display_name}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "channel_id": channel.id, "channel_name": channel.name},
                "INFO"
            )

        else:
            embed = discord.Embed(
                title="❌ Failed to Set Channel",
                description="Could not set the timeclock channel. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "set-timeclock-channel")

        embed = discord.Embed(
            title="❌ Channel Setup Failed",
            description=f"An error occurred while setting the channel: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="remove-timeclock-channel", description="Remove the designated timeclock channel (Admin only)")
@discord.app_commands.checks.has_permissions(administrator=True)
async def remove_timeclock_channel_command(interaction: discord.Interaction):
    """Remove the designated timeclock channel."""
    await interaction.response.defer()

    try:
        existing = db_manager.get_timeclock_channel(interaction.guild.id)

        if not existing:
            embed = discord.Embed(
                title="❌ No Timeclock Channel Set",
                description="There is no timeclock channel currently designated for this server.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)
            return

        success = db_manager.remove_timeclock_channel(interaction.guild.id)

        if success:
            embed = discord.Embed(
                title="✅ Timeclock Channel Removed",
                description="Time tracking commands are now available in all channels",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="👤 Removed By",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="ℹ️ Commands Now Available",
                value="Time tracking commands can now be used in any channel",
                inline=False
            )

            embed.set_footer(text="Use /set-timeclock-channel to designate a specific channel again")

            await interaction.followup.send(embed=embed)

            # Log the channel removal
            await error_logger.log_system_event(
                "timeclock_channel_removed",
                f"Timeclock channel removed by {interaction.user.display_name}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id},
                "WARNING"
            )

        else:
            embed = discord.Embed(
                title="❌ Failed to Remove Channel",
                description="Could not remove the timeclock channel. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "remove-timeclock-channel")

        embed = discord.Embed(
            title="❌ Channel Removal Failed",
            description=f"An error occurred while removing the channel: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@remove_timeclock_channel_command.error
async def remove_timeclock_channel_error(interaction: discord.Interaction, error):
    """Handle remove timeclock channel command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to remove the timeclock channel.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Remove timeclock channel error: {error}")

@set_timeclock_channel_command.error
async def set_timeclock_channel_error(interaction: discord.Interaction, error):
    """Handle set timeclock channel command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to set the timeclock channel.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Set timeclock channel error: {error}")

@bot.tree.command(name="search-tasks", description="Advanced search for Asana tasks with filters")
@app_commands.describe(
    query="Search text in task names and descriptions",
    assignee="Filter by Discord user assignee",
    project="Filter by Asana project ID",
    status="Filter by task status (completed, incomplete)",
    due_date="Filter by due date (overdue, today, tomorrow, week, month)",
    sort_by="Sort results by (created_at, modified_at, due_on, name)",
    sort_order="Sort order (asc, desc)",
    limit="Maximum results to show (default: 10, max: 25)"
)
async def search_tasks_command(
    interaction: discord.Interaction,
    query: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    limit: Optional[int] = 10
):
    """Advanced search for Asana tasks with comprehensive filtering."""
    await interaction.response.defer()

    try:
        # Validate parameters
        if limit > 25:
            limit = 25
        elif limit < 1:
            limit = 1

        if sort_by not in ['created_at', 'modified_at', 'due_on', 'name']:
            sort_by = 'created_at'

        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'

        if status and status not in ['completed', 'incomplete']:
            embed = discord.Embed(
                title="❌ Invalid Status",
                description="Status must be either 'completed' or 'incomplete'",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        if due_date and due_date not in ['overdue', 'today', 'tomorrow', 'week', 'month']:
            embed = discord.Embed(
                title="❌ Invalid Due Date Filter",
                description="Due date filter must be: overdue, today, tomorrow, week, or month",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Resolve assignee to Asana user ID
        assignee_asana_id = None
        assignee_display = None
        if assignee:
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
            if user_mapping:
                assignee_asana_id = user_mapping['asana_user_id']
                assignee_display = f"{assignee.mention}"
            else:
                embed = discord.Embed(
                    title="⚠️ User Not Mapped",
                    description=f"{assignee.mention} is not mapped to an Asana user. Search will exclude assignee filter.",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed)

        # Build search parameters for Asana API
        search_params = {}

        # Add text query if provided
        if query:
            search_params['text'] = query

        # Add assignee filter
        if assignee_asana_id:
            search_params['assignee'] = assignee_asana_id

        # Add project filter
        if project:
            search_params['projects'] = [project]

        # Add status filter
        if status:
            search_params['completed'] = status == 'completed'

        # Add due date filters
        if due_date:
            today = datetime.now().date()
            if due_date == 'overdue':
                search_params['due_on.before'] = str(today)
                search_params['completed'] = False
            elif due_date == 'today':
                search_params['due_on'] = str(today)
            elif due_date == 'tomorrow':
                tomorrow = today + timedelta(days=1)
                search_params['due_on'] = str(tomorrow)
            elif due_date == 'week':
                week_end = today + timedelta(days=7)
                search_params['due_on.before'] = str(week_end + timedelta(days=1))
                search_params['due_on.after'] = str(today - timedelta(days=1))
            elif due_date == 'month':
                month_end = today + timedelta(days=30)
                search_params['due_on.before'] = str(month_end + timedelta(days=1))
                search_params['due_on.after'] = str(today - timedelta(days=1))

        # Add sorting
        search_params['sort_by'] = sort_by
        search_params['sort_ascending'] = sort_order == 'asc'

        # Limit results
        search_params['limit'] = limit

        # Perform the search
        try:
            tasks = asana_client.tasks.search_tasks(search_params)
            tasks_list = list(tasks)
        except Exception as e:
            await error_logger.log_command_error(interaction, e, "search-tasks")
            embed = discord.Embed(
                title="❌ Search Failed",
                description=f"Failed to search Asana tasks: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Create results embed
        embed = discord.Embed(
            title="🔍 Task Search Results",
            description=f"Found {len(tasks_list)} task{'s' if len(tasks_list) != 1 else ''}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        # Add search criteria
        criteria = []
        if query:
            criteria.append(f"Query: `{query}`")
        if assignee_display:
            criteria.append(f"Assignee: {assignee_display}")
        if project:
            criteria.append(f"Project: `{project}`")
        if status:
            criteria.append(f"Status: {status}")
        if due_date:
            criteria.append(f"Due: {due_date}")
        criteria.append(f"Sort: {sort_by} ({sort_order})")
        criteria.append(f"Limit: {limit}")

        if criteria:
            embed.add_field(
                name="📋 Search Criteria",
                value="\n".join(criteria),
                inline=False
            )

        # Add results
        if tasks_list:
            for i, task in enumerate(tasks_list[:10], 1):  # Limit to 10 in embed
                task_info = f"**{task['name']}**\n"
                task_info += f"ID: `{task['gid']}`\n"

                if task.get('assignee'):
                    task_info += f"👤 {task['assignee']['name']}\n"

                if task.get('due_on'):
                    due_date_obj = datetime.fromisoformat(task['due_on']).date()
                    today = datetime.now().date()
                    if due_date_obj < today:
                        task_info += f"📅 ⚠️ {task['due_on']} (Overdue)\n"
                    elif due_date_obj == today:
                        task_info += f"📅 📍 Today ({task['due_on']})\n"
                    else:
                        task_info += f"📅 {task['due_on']}\n"

                if task.get('completed'):
                    task_info += "✅ Completed"
                else:
                    task_info += "⏳ Incomplete"

                embed.add_field(
                    name=f"{i}. {task['name'][:50]}{'...' if len(task['name']) > 50 else ''}",
                    value=task_info,
                    inline=False
                )

            if len(tasks_list) > 10:
                embed.set_footer(text=f"Showing first 10 of {len(tasks_list)} results")

        else:
            embed.add_field(
                name="📭 No Results",
                value="No tasks found matching your search criteria.",
                inline=False
            )

            embed.add_field(
                name="💡 Tips",
                value="• Try broader search terms\n• Check your project ID\n• Verify user mappings\n• Adjust date filters",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "search-tasks")

        embed = discord.Embed(
            title="❌ Search Failed",
            description=f"An error occurred while searching: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="save-search", description="Save a task search configuration for quick reuse")
@app_commands.describe(
    name="Name for your saved search (e.g., 'My Overdue Tasks')",
    description="Optional description of what this search does",
    query="Search text in task names and descriptions",
    assignee="Filter by Discord user assignee",
    project="Filter by Asana project ID",
    status="Filter by task status (completed, incomplete)",
    due_date="Filter by due date (overdue, today, tomorrow, week, month)",
    sort_by="Sort results by (created_at, modified_at, due_on, name)",
    sort_order="Sort order (asc, desc)",
    max_results="Maximum results to show when running this search (default: 10, max: 25)"
)
async def save_search_command(
    interaction: discord.Interaction,
    name: str,
    description: Optional[str] = None,
    query: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    max_results: Optional[int] = 10
):
    """Save a task search configuration for quick reuse."""
    await interaction.response.defer()

    try:
        # Validate parameters
        if max_results > 25:
            max_results = 25
        elif max_results < 1:
            max_results = 1

        if sort_by not in ['created_at', 'modified_at', 'due_on', 'name']:
            sort_by = 'created_at'

        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'

        if status and status not in ['completed', 'incomplete']:
            embed = discord.Embed(
                title="❌ Invalid Status",
                description="Status must be either 'completed' or 'incomplete'",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        if due_date and due_date not in ['overdue', 'today', 'tomorrow', 'week', 'month']:
            embed = discord.Embed(
                title="❌ Invalid Due Date Filter",
                description="Due date filter must be: overdue, today, tomorrow, week, or month",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Check if search name already exists
        existing_searches = db_manager.get_saved_searches(interaction.guild.id)
        if any(s['name'].lower() == name.lower() for s in existing_searches):
            embed = discord.Embed(
                title="❌ Search Name Already Exists",
                description=f"A saved search with the name '{name}' already exists. Please choose a different name.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Resolve assignee to Asana user ID
        assignee_asana_id = None
        if assignee:
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
            if user_mapping:
                assignee_asana_id = user_mapping['asana_user_id']
            else:
                embed = discord.Embed(
                    title="⚠️ User Not Mapped",
                    description=f"{assignee.mention} is not mapped to an Asana user. The search will be saved without assignee filter.",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed)

        # Create the saved search
        search_params = {
            'description': description,
            'search_query': query,
            'assignee_user_id': assignee.id if assignee else None,
            'assignee_asana_id': assignee_asana_id,
            'project_id': project,
            'status_filter': status,
            'due_date_filter': due_date,
            'sort_by': sort_by,
            'sort_order': sort_order,
            'max_results': max_results
        }

        success = db_manager.create_saved_search(
            guild_id=interaction.guild.id,
            name=name,
            created_by=interaction.user.id,
            **search_params
        )

        if success:
            embed = discord.Embed(
                title="✅ Search Saved",
                description=f"Search '{name}' has been saved and is ready to use!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="🔍 Search Name",
                value=f"`{name}`",
                inline=True
            )

            embed.add_field(
                name="👤 Created By",
                value=interaction.user.mention,
                inline=True
            )

            # Show search criteria
            criteria = []
            if query:
                criteria.append(f"Query: `{query}`")
            if assignee and assignee_asana_id:
                criteria.append(f"Assignee: {assignee.mention}")
            if project:
                criteria.append(f"Project: `{project}`")
            if status:
                criteria.append(f"Status: {status}")
            if due_date:
                criteria.append(f"Due: {due_date}")
            criteria.append(f"Sort: {sort_by} ({sort_order})")
            criteria.append(f"Max Results: {max_results}")

            if criteria:
                embed.add_field(
                    name="📋 Search Criteria",
                    value="\n".join(criteria),
                    inline=False
                )

            embed.add_field(
                name="🚀 How to Use",
                value=f"Use `/load-search search:\"{name}\"` to run this search",
                inline=False
            )

            await interaction.followup.send(embed=embed)

            # Log search creation
            await error_logger.log_system_event(
                "search_saved",
                f"Saved search '{name}' created by {interaction.user.display_name}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "search_name": name},
                "INFO"
            )

        else:
            embed = discord.Embed(
                title="❌ Save Failed",
                description="Failed to save the search configuration. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "save-search")

        embed = discord.Embed(
            title="❌ Save Failed",
            description=f"An error occurred while saving the search: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="load-search", description="Run a previously saved task search")
@app_commands.describe(
    search="Name of the saved search to run"
)
async def load_search_command(interaction: discord.Interaction, search: str):
    """Run a previously saved task search."""
    await interaction.response.defer()

    try:
        # Find the saved search by name
        saved_searches = db_manager.get_saved_searches(interaction.guild.id)
        saved_search = None

        # Try exact match first, then case-insensitive match
        for s in saved_searches:
            if s['name'].lower() == search.lower():
                saved_search = s
                break

        if not saved_search:
            embed = discord.Embed(
                title="❌ Search Not Found",
                description=f"No saved search found with name '{search}'.",
                color=discord.Color.red()
            )

            # Suggest similar searches
            similar = [s['name'] for s in saved_searches if search.lower() in s['name'].lower()]
            if similar:
                embed.add_field(
                    name="💡 Did you mean?",
                    value="\n".join(f"• `{name}`" for name in similar[:3]),
                    inline=False
                )

            embed.add_field(
                name="📋 Available Searches",
                value="Use `/list-searches` to see all available saved searches",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        # Update usage count
        db_manager.update_saved_search_usage(saved_search['id'])

        # Build search parameters for Asana API
        search_params = {}

        # Add text query if provided
        if saved_search['search_query']:
            search_params['text'] = saved_search['search_query']

        # Add assignee filter
        if saved_search['assignee_asana_id']:
            search_params['assignee'] = saved_search['assignee_asana_id']

        # Add project filter
        if saved_search['project_id']:
            search_params['projects'] = [saved_search['project_id']]

        # Add status filter
        if saved_search['status_filter']:
            search_params['completed'] = saved_search['status_filter'] == 'completed'

        # Add due date filters
        if saved_search['due_date_filter']:
            today = datetime.now().date()
            if saved_search['due_date_filter'] == 'overdue':
                search_params['due_on.before'] = str(today)
                search_params['completed'] = False
            elif saved_search['due_date_filter'] == 'today':
                search_params['due_on'] = str(today)
            elif saved_search['due_date_filter'] == 'tomorrow':
                tomorrow = today + timedelta(days=1)
                search_params['due_on'] = str(tomorrow)
            elif saved_search['due_date_filter'] == 'week':
                week_end = today + timedelta(days=7)
                search_params['due_on.before'] = str(week_end + timedelta(days=1))
                search_params['due_on.after'] = str(today - timedelta(days=1))
            elif saved_search['due_date_filter'] == 'month':
                month_end = today + timedelta(days=30)
                search_params['due_on.before'] = str(month_end + timedelta(days=1))
                search_params['due_on.after'] = str(today - timedelta(days=1))

        # Add sorting
        search_params['sort_by'] = saved_search['sort_by']
        search_params['sort_ascending'] = saved_search['sort_order'] == 'asc'

        # Limit results
        search_params['limit'] = saved_search['max_results']

        # Perform the search
        try:
            tasks = asana_client.tasks.search_tasks(search_params)
            tasks_list = list(tasks)
        except Exception as e:
            await error_logger.log_command_error(interaction, e, "load-search")
            embed = discord.Embed(
                title="❌ Search Failed",
                description=f"Failed to run saved search: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Create results embed
        embed = discord.Embed(
            title=f"🔍 Saved Search: {saved_search['name']}",
            description=f"Found {len(tasks_list)} task{'s' if len(tasks_list) != 1 else ''}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if saved_search['description']:
            embed.add_field(
                name="📋 Description",
                value=saved_search['description'],
                inline=False
            )

        # Add search criteria
        criteria = []
        if saved_search['search_query']:
            criteria.append(f"Query: `{saved_search['search_query']}`")
        if saved_search['assignee_user_id']:
            user = interaction.guild.get_member(saved_search['assignee_user_id'])
            if user:
                criteria.append(f"Assignee: {user.mention}")
        if saved_search['project_id']:
            criteria.append(f"Project: `{saved_search['project_id']}`")
        if saved_search['status_filter']:
            criteria.append(f"Status: {saved_search['status_filter']}")
        if saved_search['due_date_filter']:
            criteria.append(f"Due: {saved_search['due_date_filter']}")
        criteria.append(f"Sort: {saved_search['sort_by']} ({saved_search['sort_order']})")
        criteria.append(f"Max Results: {saved_search['max_results']}")

        if criteria:
            embed.add_field(
                name="📋 Search Criteria",
                value="\n".join(criteria),
                inline=False
            )

        # Add results
        if tasks_list:
            for i, task in enumerate(tasks_list[:10], 1):  # Limit to 10 in embed
                task_info = f"**{task['name']}**\n"
                task_info += f"ID: `{task['gid']}`\n"

                if task.get('assignee'):
                    task_info += f"👤 {task['assignee']['name']}\n"

                if task.get('due_on'):
                    due_date_obj = datetime.fromisoformat(task['due_on']).date()
                    today = datetime.now().date()
                    if due_date_obj < today:
                        task_info += f"📅 ⚠️ {task['due_on']} (Overdue)\n"
                    elif due_date_obj == today:
                        task_info += f"📅 📍 Today ({task['due_on']})\n"
                    else:
                        task_info += f"📅 {task['due_on']}\n"

                if task.get('completed'):
                    task_info += "✅ Completed"
                else:
                    task_info += "⏳ Incomplete"

                embed.add_field(
                    name=f"{i}. {task['name'][:50]}{'...' if len(task['name']) > 50 else ''}",
                    value=task_info,
                    inline=False
                )

            if len(tasks_list) > 10:
                embed.set_footer(text=f"Showing first 10 of {len(tasks_list)} results • Used {saved_search['usage_count'] + 1} times")

        else:
            embed.add_field(
                name="📭 No Results",
                value="No tasks found matching this saved search.",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "load-search")

        embed = discord.Embed(
            title="❌ Search Failed",
            description=f"An error occurred while running the search: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="list-searches", description="Browse all saved task searches")
async def list_searches_command(interaction: discord.Interaction):
    """Browse all saved task searches."""
    await interaction.response.defer()

    try:
        saved_searches = db_manager.get_saved_searches(interaction.guild.id)

        if not saved_searches:
            embed = discord.Embed(
                title="🔍 Saved Searches",
                description="No saved searches have been created for this server yet.",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="🚀 Create Your First Search",
                value="Use `/save-search` to save common task search configurations",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="🔍 Saved Task Searches",
            description=f"Found {len(saved_searches)} saved search{'es' if len(saved_searches) != 1 else ''} for this server",
            color=discord.Color.blue()
        )

        for i, search in enumerate(saved_searches[:10], 1):  # Limit to 10 searches in embed
            search_info = f"**{search['name']}**"
            if search['description']:
                search_info += f"\n{search['description'][:100]}{'...' if len(search['description']) > 100 else ''}"

            criteria = []
            if search['search_query']:
                criteria.append(f"Query: `{search['search_query'][:30]}{'...' if len(search['search_query']) > 30 else ''}`")
            if search['assignee_user_id']:
                user = interaction.guild.get_member(search['assignee_user_id'])
                if user:
                    criteria.append(f"Assignee: {user.display_name}")
            if search['project_id']:
                criteria.append(f"Project: `{search['project_id']}`")
            if search['status_filter']:
                criteria.append(f"Status: {search['status_filter']}")
            if search['due_date_filter']:
                criteria.append(f"Due: {search['due_date_filter']}")
            if criteria:
                search_info += f"\n{' • '.join(criteria[:2])}"
            if len(criteria) > 2:
                search_info += f" • +{len(criteria) - 2} more"

            search_info += f"\n📊 Used {search['usage_count']} time{'s' if search['usage_count'] != 1 else ''}"

            embed.add_field(
                name=f"{i}. {search['name']}",
                value=search_info,
                inline=False
            )

        embed.add_field(
            name="🚀 How to Use",
            value="Use `/load-search search:\"Search Name\"` to run any saved search",
            inline=False
        )

        if len(saved_searches) > 10:
            embed.set_footer(text=f"Showing first 10 searches. Total: {len(saved_searches)}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "list-searches")

        embed = discord.Embed(
            title="❌ Failed to Load Searches",
            description=f"Could not load saved searches: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="delete-search", description="Delete a saved task search")
@app_commands.describe(
    search="Name of the saved search to delete"
)
async def delete_search_command(interaction: discord.Interaction, search: str):
    """Delete a saved task search."""
    await interaction.response.defer()

    try:
        # Find the saved search by name
        saved_searches = db_manager.get_saved_searches(interaction.guild.id, active_only=False)
        target_search = None
        search_id = None

        for s in saved_searches:
            if s['name'].lower() == search.lower():
                target_search = s
                search_id = s['id']
                break

        if not target_search:
            embed = discord.Embed(
                title="❌ Search Not Found",
                description=f"No saved search found with name '{search}'.",
                color=discord.Color.red()
            )

            embed.add_field(
                name="📋 Available Searches",
                value="Use `/list-searches` to see all available saved searches",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        # Check if user created this search or is admin
        is_admin = interaction.user.guild_permissions.administrator
        is_creator = target_search['created_by'] == interaction.user.id

        if not (is_admin or is_creator):
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You can only delete searches that you created, or ask an administrator to delete it.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Confirm deletion
        embed = discord.Embed(
            title="🗑️ Confirm Search Deletion",
            description=f"Are you sure you want to delete the saved search **{target_search['name']}**?",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="⚠️ This action cannot be undone",
            value=f"This search has been used {target_search['usage_count']} time{'s' if target_search['usage_count'] != 1 else ''}.",
            inline=False
        )

        view = SearchDeletionView(search_id, target_search['name'], interaction)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "delete-search")

        embed = discord.Embed(
            title="❌ Deletion Failed",
            description=f"Failed to delete search: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="create-template", description="Create a reusable task template")
@app_commands.describe(
    name="Template name (e.g., 'Bug Report', 'Feature Request')",
    task_name="Default task name with optional variables like {description} or {priority}",
    description="Template description for users",
    assignee="Default assignee Discord user (optional)",
    project="Default Asana project ID (optional)",
    due_date_offset="Days from creation date (e.g., 7 for 1 week)",
    notes="Default task description/notes (optional)"
)
async def create_template_command(
    interaction: discord.Interaction,
    name: str,
    task_name: str,
    description: str = None,
    assignee: Optional[discord.Member] = None,
    project: Optional[str] = None,
    due_date_offset: Optional[int] = None,
    notes: Optional[str] = None
):
    """Create a reusable task template."""
    await interaction.response.defer()

    try:
        # Validate due date offset
        if due_date_offset and (due_date_offset < 0 or due_date_offset > 365):
            embed = discord.Embed(
                title="❌ Invalid Due Date Offset",
                description="Due date offset must be between 0 and 365 days.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Resolve assignee to Asana user ID
        asana_assignee = None
        if assignee:
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
            if user_mapping:
                asana_assignee = user_mapping['asana_user_id']
            else:
                embed = discord.Embed(
                    title="⚠️ User Not Mapped",
                    description=f"{assignee.mention} is not mapped to an Asana user. The template will be created without a default assignee.",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed)

        # Validate project ID if provided
        if project:
            try:
                project_info = asana_client.projects.get_project(project)
                project_name = project_info['name']
            except Exception:
                embed = discord.Embed(
                    title="❌ Invalid Project ID",
                    description=f"Could not find Asana project with ID `{project}`. Please check the ID and try again.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return

        # Create the template
        success = db_manager.create_task_template(
            guild_id=interaction.guild.id,
            name=name,
            task_name_template=task_name,
            description=description,
            default_assignee=asana_assignee,
            default_project=project,
            default_notes=notes,
            due_date_offset=due_date_offset,
            created_by=interaction.user.id
        )

        if success:
            embed = discord.Embed(
                title="✅ Task Template Created",
                description=f"Template **{name}** has been created and is ready to use!",
                color=discord.Color.green()
            )

            embed.add_field(
                name="📝 Task Name Template",
                value=f"`{task_name}`",
                inline=False
            )

            if description:
                embed.add_field(
                    name="📋 Description",
                    value=description,
                    inline=False
                )

            if assignee and asana_assignee:
                embed.add_field(
                    name="👤 Default Assignee",
                    value=f"{assignee.mention}",
                    inline=True
                )

            if project:
                embed.add_field(
                    name="📁 Default Project",
                    value=f"`{project}`",
                    inline=True
                )

            if due_date_offset:
                embed.add_field(
                    name="📅 Due Date Offset",
                    value=f"{due_date_offset} day{'s' if due_date_offset != 1 else ''}",
                    inline=True
                )

            embed.add_field(
                name="🚀 How to Use",
                value=f"Use `/use-template template:\"{name}\"` to create tasks from this template",
                inline=False
            )

            embed.set_footer(text=f"Created by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

            # Log template creation
            await error_logger.log_system_event(
                "template_created",
                f"Task template '{name}' created by {interaction.user.display_name}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "template_name": name},
                "INFO"
            )

        else:
            embed = discord.Embed(
                title="❌ Template Creation Failed",
                description="Failed to create the task template. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "create-template")

        embed = discord.Embed(
            title="❌ Template Creation Failed",
            description=f"An error occurred while creating the template: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="list-templates", description="List available task templates")
async def list_templates_command(interaction: discord.Interaction):
    """List all available task templates for this server."""
    await interaction.response.defer()

    try:
        templates = db_manager.get_task_templates(interaction.guild.id)

        if not templates:
            embed = discord.Embed(
                title="📋 Task Templates",
                description="No task templates have been created for this server yet.",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="🚀 Create Your First Template",
                value="Use `/create-template` to create reusable task configurations",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 Available Task Templates",
            description=f"Found {len(templates)} template{'s' if len(templates) != 1 else ''} for this server",
            color=discord.Color.blue()
        )

        for i, template in enumerate(templates[:10], 1):  # Limit to 10 templates in embed
            template_info = f"**{template['name']}**"
            if template['description']:
                template_info += f"\n{template['description'][:100]}{'...' if len(template['description']) > 100 else ''}"

            template_info += f"\n📝 `{template['task_name_template']}`"

            if template['default_assignee']:
                template_info += f"\n👤 Has default assignee"
            if template['default_project']:
                template_info += f"\n📁 Has default project"
            if template['due_date_offset']:
                template_info += f"\n📅 Due in {template['due_date_offset']} day{'s' if template['due_date_offset'] != 1 else ''}"
            if template['usage_count'] > 0:
                template_info += f"\n📊 Used {template['usage_count']} time{'s' if template['usage_count'] != 1 else ''}"

            embed.add_field(
                name=f"{i}. {template['name']}",
                value=template_info,
                inline=False
            )

        embed.add_field(
            name="🚀 How to Use",
            value="Use `/use-template template:\"Template Name\"` to create a task from any template",
            inline=False
        )

        if len(templates) > 10:
            embed.set_footer(text=f"Showing first 10 templates. Total: {len(templates)}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "list-templates")

        embed = discord.Embed(
            title="❌ Failed to Load Templates",
            description=f"Could not load task templates: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="use-template", description="Create a task using a saved template")
@app_commands.describe(
    template="Template name to use (use /list-templates to see available templates)",
    custom_name="Custom task name (optional - overrides template default)",
    assignee="Custom assignee (optional - overrides template default)",
    project="Custom project ID (optional - overrides template default)",
    due_date="Custom due date YYYY-MM-DD (optional - overrides template default)",
    notes="Custom notes (optional - will be appended to template notes)"
)
async def use_template_command(
    interaction: discord.Interaction,
    template: str,
    custom_name: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
    project: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Create a task using a saved template."""
    await interaction.response.defer()

    try:
        # Find the template by name
        templates = db_manager.get_task_templates(interaction.guild.id)
        template_data = None

        # Try exact match first, then case-insensitive match
        for t in templates:
            if t['name'].lower() == template.lower():
                template_data = t
                break

        if not template_data:
            embed = discord.Embed(
                title="❌ Template Not Found",
                description=f"No template found with name '{template}'.",
                color=discord.Color.red()
            )

            # Suggest similar templates
            similar = [t['name'] for t in templates if template.lower() in t['name'].lower()]
            if similar:
                embed.add_field(
                    name="💡 Did you mean?",
                    value="\n".join(f"• `{name}`" for name in similar[:3]),
                    inline=False
                )

            embed.add_field(
                name="📋 Available Templates",
                value="Use `/list-templates` to see all available templates",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        # Start with template defaults
        task_name = custom_name or template_data['task_name_template']
        task_assignee = template_data['default_assignee']
        task_project = project or template_data['default_project']
        task_notes = template_data['default_notes'] or ""
        task_due_date = due_date

        # Apply customizations
        if assignee:
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, assignee.id)
            if user_mapping:
                task_assignee = user_mapping['asana_user_id']
            else:
                embed = discord.Embed(
                    title="⚠️ User Not Mapped",
                    description=f"{assignee.mention} is not mapped to an Asana user. Using template default assignee instead.",
                    color=discord.Color.yellow()
                )
                await interaction.followup.send(embed=embed)

        # Calculate due date from offset if no custom date provided
        if not task_due_date and template_data['due_date_offset']:
            task_due_date = (datetime.now() + timedelta(days=template_data['due_date_offset'])).strftime('%Y-%m-%d')

        # Append custom notes
        if notes:
            if task_notes:
                task_notes += "\n\n" + notes
            else:
                task_notes = notes

        # Show what will be created
        embed = discord.Embed(
            title="📋 Task from Template",
            description=f"Creating task using template **{template_data['name']}**",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📝 Task Name",
            value=task_name,
            inline=False
        )

        if task_assignee:
            # Try to find the Discord user for display
            assignee_info = "Template default assignee"
            for mapping in db_manager.list_user_mappings(interaction.guild.id):
                if mapping['asana_user_id'] == task_assignee:
                    discord_user = interaction.guild.get_member(mapping['discord_user_id'])
                    if discord_user:
                        assignee_info = f"{discord_user.mention}"
                    break
            embed.add_field(name="👤 Assignee", value=assignee_info, inline=True)

        if task_project:
            embed.add_field(name="📁 Project", value=f"`{task_project}`", inline=True)

        if task_due_date:
            embed.add_field(name="📅 Due Date", value=task_due_date, inline=True)

        if task_notes:
            embed.add_field(name="📋 Notes", value=task_notes[:500] + "..." if len(task_notes) > 500 else task_notes, inline=False)

        embed.add_field(
            name="✅ Confirm Creation?",
            value="React with ✅ to create this task, or ❌ to cancel.",
            inline=False
        )

        # Create confirmation view
        view = TemplateTaskConfirmationView(template_data, task_name, task_assignee, task_project, task_due_date, task_notes, interaction)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "use-template")

        embed = discord.Embed(
            title="❌ Template Usage Failed",
            description=f"Failed to create task from template: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="delete-template", description="Delete a task template (Admin only)")
@discord.app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    template="Name of the template to delete"
)
async def delete_template_command(interaction: discord.Interaction, template: str):
    """Delete a task template."""
    await interaction.response.defer()

    try:
        # Find the template by name
        templates = db_manager.get_task_templates(interaction.guild.id, active_only=False)
        template_data = None
        template_id = None

        for t in templates:
            if t['name'].lower() == template.lower():
                template_data = t
                template_id = t['id']
                break

        if not template_data:
            embed = discord.Embed(
                title="❌ Template Not Found",
                description=f"No template found with name '{template}'.",
                color=discord.Color.red()
            )

            embed.add_field(
                name="📋 Available Templates",
                value="Use `/list-templates` to see all available templates",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        # Confirm deletion
        embed = discord.Embed(
            title="🗑️ Confirm Template Deletion",
            description=f"Are you sure you want to delete the template **{template_data['name']}**?",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="⚠️ This action cannot be undone",
            value=f"This template has been used {template_data['usage_count']} time{'s' if template_data['usage_count'] != 1 else ''}.",
            inline=False
        )

        view = TemplateDeletionView(template_id, template_data['name'], interaction)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "delete-template")

        embed = discord.Embed(
            title="❌ Deletion Failed",
            description=f"Failed to delete template: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@delete_template_command.error
async def delete_template_error(interaction: discord.Interaction, error):
    """Handle delete template command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to delete task templates.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Delete template error: {error}")

@bot.tree.command(name="clock-in", description="Clock in to start tracking work time")
async def clock_in_command(interaction: discord.Interaction):
    """Clock in to start tracking work time."""
    # Check if command is being used in the designated timeclock channel
    if not check_timeclock_channel(interaction):
        return

    await interaction.response.defer()

    try:
        # Check if user is already clocked in
        active_entry = db_manager.get_active_time_entry(interaction.guild.id, interaction.user.id)

        if active_entry:
            # User is already clocked in
            clock_in_time = active_entry['clock_in_time']
            duration = datetime.utcnow() - clock_in_time.replace(tzinfo=None)

            embed = discord.Embed(
                title="⚠️ Already Clocked In",
                description="You are already clocked in for work.",
                color=discord.Color.yellow()
            )

            embed.add_field(
                name="🕐 Clock In Time",
                value=f"<t:{int(clock_in_time.timestamp())}:F>",
                inline=True
            )

            embed.add_field(
                name="⏱️ Current Session",
                value=format_duration(int(duration.total_seconds())),
                inline=True
            )

            embed.add_field(
                name="💡 To Clock Out",
                value="Use `/clock-out` with your time proof link",
                inline=False
            )

            await interaction.followup.send(embed=embed)
            return

        # Clock in the user
        entry_id = db_manager.create_time_entry(
            guild_id=interaction.guild.id,
            discord_user_id=interaction.user.id,
            discord_username=str(interaction.user)
        )

        if entry_id:
            embed = discord.Embed(
                title="🕐 Successfully Clocked In!",
                description="Your work session has started.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="👤 Employee",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="🕐 Start Time",
                value=f"<t:{int(datetime.utcnow().timestamp())}:F>",
                inline=True
            )

            embed.add_field(
                name="📍 Location",
                value=f"#{interaction.channel.name}" if hasattr(interaction.channel, 'name') else "Direct Message",
                inline=True
            )

            embed.set_footer(text="Use /clock-out when finished to log your time")

            await interaction.followup.send(embed=embed)

            # Log the clock in event
            await error_logger.log_system_event(
                "clock_in",
                f"{interaction.user.display_name} clocked in",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "entry_id": entry_id},
                "INFO"
            )

            # Create Asana task for time tracking
            await create_timeclock_asana_task(interaction, entry_id, "clock_in")

        else:
            embed = discord.Embed(
                title="❌ Clock In Failed",
                description="Failed to clock you in. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "clock-in")

        embed = discord.Embed(
            title="❌ Clock In Failed",
            description=f"An error occurred while clocking in: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="clock-out", description="Clock out and provide time proof link")
@app_commands.describe(
    time_proof_link="Link to your work proof (Google Sheets, screenshots, etc.)",
    notes="Optional notes about your work session"
)
async def clock_out_command(
    interaction: discord.Interaction,
    time_proof_link: str,
    notes: Optional[str] = None
):
    """Clock out with time proof link."""
    # Check if command is being used in the designated timeclock channel
    if not check_timeclock_channel(interaction):
        return

    await interaction.response.defer()

    try:
        # Check if user is clocked in
        active_entry = db_manager.get_active_time_entry(interaction.guild.id, interaction.user.id)

        if not active_entry:
            embed = discord.Embed(
                title="❌ Not Clocked In",
                description="You are not currently clocked in. Use `/clock-in` to start your work session.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # Validate time proof link
        if not time_proof_link.startswith(('http://', 'https://')):
            embed = discord.Embed(
                title="❌ Invalid Time Proof Link",
                description="Please provide a valid URL for your time proof (must start with http:// or https://).",
                color=discord.Color.red()
            )
            embed.add_field(
                name="💡 Examples",
                value="• Google Sheets: `https://docs.google.com/spreadsheets/...`\n• Screenshots: `https://imgur.com/...`\n• Documents: `https://drive.google.com/...`",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return

        # Clock out the user
        success = db_manager.clock_out_time_entry(
            entry_id=active_entry['id'],
            time_proof_link=time_proof_link,
            notes=notes
        )

        if success:
            # Get the completed entry to show duration
            completed_entries = db_manager.get_user_time_entries(interaction.guild.id, interaction.user.id, limit=1)
            if completed_entries:
                entry = completed_entries[0]
                duration = format_duration(entry['duration_seconds'])

                embed = discord.Embed(
                    title="🕐 Successfully Clocked Out!",
                    description="Your work session has ended.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )

                embed.add_field(
                    name="👤 Employee",
                    value=interaction.user.mention,
                    inline=True
                )

                embed.add_field(
                    name="⏱️ Session Duration",
                    value=duration,
                    inline=True
                )

                embed.add_field(
                    name="🕐 Clock In",
                    value=f"<t:{int(entry['clock_in_time'].timestamp())}:t>",
                    inline=True
                )

                embed.add_field(
                    name="🕐 Clock Out",
                    value=f"<t:{int(entry['clock_out_time'].timestamp())}:t>",
                    inline=True
                )

                embed.add_field(
                    name="🔗 Time Proof",
                    value=f"[View Proof]({time_proof_link})",
                    inline=False
                )

                if notes:
                    embed.add_field(
                        name="📝 Notes",
                        value=notes,
                        inline=False
                    )

                embed.set_footer(text=f"Entry ID: {entry['id']} • Have a great day!")

                await interaction.followup.send(embed=embed)

                # Log the clock out event
                await error_logger.log_system_event(
                    "clock_out",
                    f"{interaction.user.display_name} clocked out after {duration}",
                    {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "entry_id": active_entry['id'], "duration": duration, "time_proof": time_proof_link},
                    "INFO"
                )

                # Update Asana task with clock out info
                await create_timeclock_asana_task(interaction, active_entry['id'], "clock_out", time_proof_link, notes)

            else:
                # Fallback success message
                embed = discord.Embed(
                    title="🕐 Successfully Clocked Out!",
                    description="Your work session has ended and time proof has been logged.",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="🔗 Time Proof",
                    value=f"[View Proof]({time_proof_link})",
                    inline=False
                )
                await interaction.followup.send(embed=embed)

        else:
            embed = discord.Embed(
                title="❌ Clock Out Failed",
                description="Failed to clock you out. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "clock-out")

        embed = discord.Embed(
            title="❌ Clock Out Failed",
            description=f"An error occurred while clocking out: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="time-status", description="Check your current time tracking status")
async def time_status_command(interaction: discord.Interaction):
    """Check current time tracking status."""
    # Check if command is being used in the designated timeclock channel
    if not check_timeclock_channel(interaction):
        return

    await interaction.response.defer()

    try:
        # Check if user is currently clocked in
        active_entry = db_manager.get_active_time_entry(interaction.guild.id, interaction.user.id)

        if active_entry:
            # User is clocked in
            clock_in_time = active_entry['clock_in_time']
            current_duration = datetime.utcnow() - clock_in_time.replace(tzinfo=None)

            embed = discord.Embed(
                title="🕐 Currently Clocked In",
                description="You are actively tracking time.",
                color=discord.Color.green()
            )

            embed.add_field(
                name="🕐 Clock In Time",
                value=f"<t:{int(clock_in_time.timestamp())}:F>",
                inline=True
            )

            embed.add_field(
                name="⏱️ Current Session",
                value=format_duration(int(current_duration.total_seconds())),
                inline=True
            )

            embed.add_field(
                name="📊 Today's Total",
                value=await get_today_total_time(interaction.guild.id, interaction.user.id),
                inline=True
            )

            embed.add_field(
                name="💡 To Clock Out",
                value="Use `/clock-out time_proof_link:\"https://...\"` when finished",
                inline=False
            )

        else:
            # User is not clocked in - show recent sessions
            recent_entries = db_manager.get_user_time_entries(interaction.guild.id, interaction.user.id, limit=3)

            embed = discord.Embed(
                title="🕐 Not Currently Clocked In",
                description="Use `/clock-in` to start tracking time.",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="📊 Today's Total",
                value=await get_today_total_time(interaction.guild.id, interaction.user.id),
                inline=True
            )

            if recent_entries:
                embed.add_field(
                    name="🕐 Recent Sessions",
                    value="\n".join([
                        f"• {entry['clock_in_time'].strftime('%m/%d')} {format_duration(entry['duration_seconds'] or 0)}"
                        for entry in recent_entries[:3]
                    ]),
                    inline=False
                )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "time-status")

        embed = discord.Embed(
            title="❌ Status Check Failed",
            description=f"Could not check your time status: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="time-history", description="View your recent time tracking history")
@app_commands.describe(
    limit="Number of recent entries to show (default: 5, max: 10)"
)
async def time_history_command(interaction: discord.Interaction, limit: Optional[int] = 5):
    """View recent time tracking history."""
    # Check if command is being used in the designated timeclock channel
    if not check_timeclock_channel(interaction):
        return

    await interaction.response.defer()

    try:
        if limit > 10:
            limit = 10
        elif limit < 1:
            limit = 1

        entries = db_manager.get_user_time_entries(interaction.guild.id, interaction.user.id, limit=limit)

        if not entries:
            embed = discord.Embed(
                title="📊 Time History",
                description="No time entries found. Use `/clock-in` to start tracking time.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="📊 Time Tracking History",
            description=f"Your last {len(entries)} time entr{'y' if len(entries) == 1 else 'ies'}",
            color=discord.Color.blue()
        )

        total_time = 0
        for entry in entries:
            if entry['status'] == 'completed' and entry['duration_seconds']:
                total_time += entry['duration_seconds']

                entry_info = f"🕐 <t:{int(entry['clock_in_time'].timestamp())}:D>\n"
                entry_info += f"⏱️ {format_duration(entry['duration_seconds'])}\n"
                if entry['time_proof_link']:
                    entry_info += f"🔗 [Proof]({entry['time_proof_link']})"

                embed.add_field(
                    name=f"Session #{entry['id']}",
                    value=entry_info,
                    inline=True
                )

        # Add summary
        embed.add_field(
            name="📈 Summary",
            value=f"**Total Sessions:** {len([e for e in entries if e['status'] == 'completed'])}\n"
                  f"**Total Time:** {format_duration(total_time)}\n"
                  f"**Average Session:** {format_duration(total_time // max(1, len([e for e in entries if e['status'] == 'completed'])))}",
            inline=False
        )

        embed.set_footer(text="Use /clock-in to start a new session")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "time-history")

        embed = discord.Embed(
            title="❌ History Check Failed",
            description=f"Could not load your time history: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="timeclock-status", description="View all currently active time clock sessions (Admin only)")
@discord.app_commands.checks.has_permissions(administrator=True)
async def timeclock_status_command(interaction: discord.Interaction):
    """View all currently active time clock sessions."""
    await interaction.response.defer()

    try:
        active_entries = db_manager.get_all_active_entries(interaction.guild.id)

        embed = discord.Embed(
            title="🕐 Active Time Clock Sessions",
            description=f"Currently {len(active_entries)} user{' is' if len(active_entries) == 1 else 's are'} clocked in",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if active_entries:
            for entry in active_entries[:10]:  # Limit to 10 for embed size
                user = interaction.guild.get_member(entry['discord_user_id'])
                username = user.display_name if user else entry['discord_username'] or f"User {entry['discord_user_id']}"

                clock_in_duration = datetime.utcnow() - entry['clock_in_time'].replace(tzinfo=None)

                embed.add_field(
                    name=username,
                    value=f"🕐 Clocked in: <t:{int(entry['clock_in_time'].timestamp())}:R>\n"
                          f"⏱️ Duration: {format_duration(int(clock_in_duration.total_seconds()))}",
                    inline=True
                )

            if len(active_entries) > 10:
                embed.set_footer(text=f"Showing first 10 of {len(active_entries)} active sessions")
        else:
            embed.add_field(
                name="📊 Status",
                value="No users are currently clocked in",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "timeclock-status")

        embed = discord.Embed(
            title="❌ Status Check Failed",
            description=f"Could not load active sessions: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@timeclock_status_command.error
async def timeclock_status_error(interaction: discord.Interaction, error):
    """Handle timeclock status command errors."""
    if isinstance(error, discord.app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Administrator Required",
            description="You need Administrator permissions to view all active time clock sessions.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    else:
        logger.error(f"Timeclock status error: {error}")

@bot.tree.command(name="bulk-select", description="Select multiple tasks for batch operations (complete, update, etc.)")
@app_commands.describe(
    search="Search term to find tasks (optional - shows recent tasks if empty)",
    limit="Maximum number of tasks to show for selection (default 10, max 25)"
)
async def bulk_select_command(
    interaction: discord.Interaction,
    search: Optional[str] = None,
    limit: Optional[int] = 10
):
    """Select multiple tasks for batch operations."""
    await interaction.response.defer()

    try:
        if limit > 25:
            limit = 25

        # Find tasks based on search criteria
        tasks = []
        search_description = ""

        if search:
            # Search by name or assignee
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            assignee_id = user_mapping['asana_user_id'] if user_mapping else None

            tasks = await asana_manager.search_tasks(search, assignee=assignee_id, limit=limit)
            search_description = f"matching '{search}'"
        else:
            # Show recent tasks from default project or user's tasks
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            assignee_id = user_mapping['asana_user_id'] if user_mapping else None

            tasks = await asana_manager.list_tasks(assignee=assignee_id)
            tasks = [task for task in tasks if not task.get('completed', False)][:limit]  # Only incomplete tasks
            search_description = "recent incomplete tasks"

        if not tasks:
            embed = discord.Embed(
                title="❌ No Tasks Found",
                description=f"No tasks found {search_description}.",
                color=discord.Color.yellow()
            )
            if search:
                embed.add_field(
                    name="💡 Try:",
                    value="• Use a broader search term\n• Check spelling\n• Remove filters to see recent tasks",
                    inline=False
                )
            await interaction.followup.send(embed=embed)
            return

        # Create task selection interface
        view = BulkTaskSelectionView(tasks, interaction)
        view.message = await interaction.followup.send(
            f"🎯 Found {len(tasks)} tasks {search_description}. Select the tasks you want to operate on:",
            view=view
        )

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "bulk-select")

        error_embed = discord.Embed(
            title="❌ Bulk Selection Failed",
            description=f"Failed to search for tasks: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="notification-settings", description="Manage your notification preferences for task updates")
async def notification_settings_command(interaction: discord.Interaction):
    """Manage notification preferences for task updates."""
    await interaction.response.defer()

    try:
        # Get current user preferences
        user_prefs = db_manager.get_notification_preferences(interaction.user.id, interaction.guild.id)

        embed = discord.Embed(
            title="🔔 Notification Settings",
            description="Configure when you want to be notified about task updates.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📅 Due Date Reminders",
            value="Get notified when tasks are approaching their due dates.",
            inline=False
        )

        # Due date reminder options
        due_reminder_options = [
            ("1_day", "1 day before due date", "⏰"),
            ("1_hour", "1 hour before due date", "⏱️"),
            ("1_week", "1 week before due date", "📅"),
            ("disabled", "Disable due date reminders", "🚫")
        ]

        current_due_pref = user_prefs.get('due_date_reminder', '1_day') if user_prefs else '1_day'

        embed.add_field(
            name="Current Due Date Reminder",
            value=f"**{next((opt[1] for opt in due_reminder_options if opt[0] == current_due_pref), '1 day before')}**",
            inline=True
        )

        embed.add_field(
            name="👥 Assignment Notifications",
            value="Get notified when tasks are assigned to you.",
            inline=False
        )

        # Assignment notification options
        assignment_options = [
            ("enabled", "Notify when assigned to tasks", "✅"),
            ("disabled", "Disable assignment notifications", "🚫")
        ]

        current_assignment_pref = user_prefs.get('assignment_notifications', 'enabled') if user_prefs else 'enabled'

        embed.add_field(
            name="Current Assignment Notifications",
            value=f"**{next((opt[1] for opt in assignment_options if opt[0] == current_assignment_pref), 'Enabled')}**",
            inline=True
        )

        # Create settings view
        view = NotificationSettingsView(user_prefs or {}, interaction)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await error_logger.log_command_error(interaction, e, "notification-settings")

        error_embed = discord.Embed(
            title="❌ Failed to Load Settings",
            description=f"Could not load your notification settings: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="status", description="Check Botsana's comprehensive system status")
async def status_command(interaction: discord.Interaction):
    """Display comprehensive bot status and health information."""
    await interaction.response.defer()

    try:
        embed = discord.Embed(
            title="🤖 Botsana System Status",
            description="Comprehensive health check and system information",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        # Bot Information
        embed.add_field(
            name="🤖 Bot Status",
            value="✅ Online and responding",
            inline=True
        )

        embed.add_field(
            name="🏠 Guild",
            value=f"{interaction.guild.name} ({interaction.guild.id})",
            inline=True
        )

        # Discord Connection
        latency = round(bot.latency * 1000, 2) if bot.latency else "Unknown"
        embed.add_field(
            name="🌐 Discord Connection",
            value=f"✅ Connected\n📡 Latency: {latency}ms",
            inline=True
        )

        # Asana Connection Test
        asana_status = await test_asana_connection()
        embed.add_field(
            name="📋 Asana API",
            value=asana_status,
            inline=True
        )

        # Database Connection Test
        db_status = await test_database_connection()
        embed.add_field(
            name="🗄️ Database",
            value=db_status,
            inline=True
        )

        # AI System Status
        ai_status = await get_ai_system_status()
        embed.add_field(
            name="🧠 AI System",
            value=ai_status,
            inline=True
        )

        # Chat Channel Status
        chat_channel_status = await get_chat_channel_status(interaction.guild.id)
        embed.add_field(
            name="🤖 Chat Channel",
            value=chat_channel_status,
            inline=True
        )

        # Audit System Status
        audit_status = await get_audit_system_status(interaction.guild.id)
        embed.add_field(
            name="📊 Audit System",
            value=audit_status,
            inline=True
        )

        # Error Statistics
        error_stats = await get_error_statistics(interaction.guild.id)
        embed.add_field(
            name="🚨 Recent Errors",
            value=error_stats,
            inline=False
        )

        # Bot Statistics
        bot_stats = await get_bot_statistics()
        embed.add_field(
            name="📈 Bot Statistics",
            value=bot_stats,
            inline=False
        )

        # System Information
        system_info = get_system_info()
        embed.add_field(
            name="⚙️ System Info",
            value=system_info,
            inline=False
        )

        embed.set_footer(text="Botsana Health Check | Use /help for command list")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        # Fallback status if something goes wrong
        error_embed = discord.Embed(
            title="❌ Status Check Failed",
            description=f"Unable to perform full status check: {str(e)}",
            color=discord.Color.red()
        )

        # At least show we're online
        error_embed.add_field(
            name="🤖 Bot Status",
            value="✅ Bot is responding",
            inline=True
        )

        await interaction.followup.send(embed=error_embed)

async def test_asana_connection() -> str:
    """Test connection to Asana API."""
    try:
        # Try to get user info to test API connection
        user_info = asana_client.users.get_user('me')
        return f"✅ Connected\n👤 {user_info['name']}"
    except Exception as e:
        return f"❌ Connection Failed\n💬 {str(e)[:50]}..."

async def test_database_connection() -> str:
    """Test database connection."""
    try:
        with db_manager.get_session() as session:
            # Simple query to test connection
            result = session.execute(text("SELECT 1")).scalar()
            return "✅ Connected"
    except Exception as e:
        return f"❌ Connection Failed\n💬 {str(e)[:50]}..."

async def get_ai_system_status() -> str:
    """Get AI system status."""
    try:
        if XAI_API_KEY:
            # Test AI connectivity
            try:
                test_response = await call_grok_api("Hello", "")
                if test_response:
                    return "✅ Active\n🤖 Grok-4-Fast-Reasoning"
                else:
                    return "⚠️ API Key Set\n🤖 Connection Failed"
            except Exception:
                return "⚠️ API Key Set\n🤖 Connection Failed"
        else:
            return "❌ Not configured\n💡 Set XAI_API_KEY"
    except Exception as e:
        return f"❌ Error: {str(e)[:30]}..."

async def get_chat_channel_status(guild_id: int) -> str:
    """Get chat channel status for the guild."""
    try:
        chat_channel_config = db_manager.get_chat_channel(guild_id)
        if chat_channel_config:
            chat_channel = bot.get_channel(chat_channel_config['channel_id'])
            if chat_channel:
                return f"✅ Active\n📺 {chat_channel.mention}"
            else:
                return "⚠️ Channel not found"
        else:
            return "❌ Not configured\n💡 Use `/set-chat-channel`"
    except Exception as e:
        return f"❌ Error: {str(e)[:30]}..."

async def get_audit_system_status(guild_id: int) -> str:
    """Get audit system status for the guild."""
    try:
        audit_channel_id = bot_config.get_audit_log_channel(guild_id)
        if audit_channel_id:
            audit_channel = bot.get_channel(audit_channel_id)
            if audit_channel:
                return f"✅ Configured\n📺 {audit_channel.mention}"
            else:
                return "⚠️ Channel not found"
        else:
            return "❌ Not configured\n💡 Use `/set-audit-log`"
    except Exception as e:
        return f"❌ Error: {str(e)[:30]}..."

async def get_error_statistics(guild_id: int) -> str:
    """Get recent error statistics for the guild."""
    try:
        with db_manager.get_session() as session:
            # Get error count from last 24 hours
            yesterday = datetime.now() - timedelta(days=1)
            error_count = session.query(ErrorLog).filter(
                ErrorLog.guild_id == guild_id,
                ErrorLog.created_at >= yesterday
            ).count()

            if error_count == 0:
                return "✅ No errors in last 24h"
            elif error_count == 1:
                return "⚠️ 1 error in last 24h"
            else:
                return f"⚠️ {error_count} errors in last 24h"
    except Exception as e:
        return f"❌ Unable to check: {str(e)[:30]}..."

async def get_bot_statistics() -> str:
    """Get general bot statistics."""
    try:
        guild_count = len(bot.guilds)
        user_count = sum(len(guild.members) for guild in bot.guilds)

        return f"🏠 {guild_count} servers\n👥 {user_count} users"
    except Exception as e:
        return f"❌ Unable to get stats: {str(e)[:30]}..."

def get_system_info() -> str:
    """Get system information."""
    try:
        import platform
        python_version = platform.python_version()

        return f"🐍 Python {python_version}\n⚡ discord.py {discord.__version__}"
    except Exception:
        return "ℹ️ System info unavailable"

# xAI/Grok API Integration
async def call_grok_api(prompt: str, user_context: str = "") -> Optional[str]:
    """Call Grok API for natural language processing."""
    if not XAI_API_KEY:
        logger.warning("XAI_API_KEY not configured, falling back to regex parsing")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-4-fast-reasoning",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert at parsing natural language requests to create Asana tasks. Extract task information and return it in a specific JSON format. Be precise and only extract what's clearly stated."
                        },
                        {
                            "role": "user",
                            "content": f"{user_context}\n\nParse this task request: {prompt}"
                        }
                    ],
                    "temperature": 0.1,  # Low temperature for consistent parsing
                    "max_tokens": 500
                }
            )

            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                logger.info(f"Grok API response: {content}")
                return content
            else:
                logger.error(f"Grok API error: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Error calling Grok API: {e}")
        return None

async def parse_task_with_grok(message: str, interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
    """Parse task using Grok AI instead of regex."""
    try:
        # Create context about available Discord users for assignment
        user_context = "Available Discord users for assignment:"
        if interaction.guild:
            members = interaction.guild.members[:50]  # Limit to avoid token limits
            for member in members:
                user_context += f"\n- {member.display_name} (@{member.name}) - ID: {member.id}"

        # Create detailed prompt for Grok
        prompt = f"""
Parse this natural language task request into structured Asana task data.

Return ONLY a valid JSON object with this exact format:
{{
    "task_name": "string - the main task description/title",
    "due_date": "YYYY-MM-DD format or null if no date mentioned",
    "assignee_discord_id": "number - Discord user ID for assignment, or null",
    "assignee_name": "string - Discord username if assigned, or null",
    "project_name": "string - project name if mentioned, or null",
    "notes": "string - additional notes/description, or null",
    "confidence": "high|medium|low - how confident you are in this parsing"
}}

Rules:
- task_name should be concise but descriptive
- due_date should be in YYYY-MM-DD format, use today's date if "today", tomorrow for "tomorrow", etc.
- assignee_discord_id should be the Discord user ID number from the available users list
- If no assignee mentioned, set assignee fields to null
- If no project mentioned, set project_name to null
- If no notes/details beyond task name, set notes to null
- Be conservative - only extract what's clearly stated

Task request: "{message}"
"""

        ai_response = await call_grok_api(prompt, user_context)

        if not ai_response:
            return None

        # Try to parse the JSON response
        try:
            # Clean up the response - sometimes AI adds extra text
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = ai_response[json_start:json_end]
                parsed_data = json.loads(json_str)
            else:
                logger.error(f"Could not find JSON in Grok response: {ai_response}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Grok JSON response: {ai_response} - Error: {e}")
            return None

        # Validate the parsed data
        if not parsed_data.get('task_name'):
            logger.warning("Grok did not extract a task name")
            return None

        # Convert to our internal format
        parsed_task = {
            'name': parsed_data['task_name'],
            'assignee': None,
            'assignee_info': 'Auto-assigned to you',
            'due_date': parsed_data.get('due_date'),
            'notes': parsed_data.get('notes'),
            'project_id': None,
            'project_info': parsed_data.get('project_name', 'Default project') if parsed_data.get('project_name') else 'Default project',
            'interpreted_as': message,
            'confidence': parsed_data.get('confidence', 'medium')
        }

        # Handle assignee
        if parsed_data.get('assignee_discord_id'):
            discord_user_id = parsed_data['assignee_discord_id']
            discord_user = interaction.guild.get_member(discord_user_id) if interaction.guild else None

            if discord_user:
                user_mapping = db_manager.get_user_mapping(interaction.guild.id, discord_user_id)
                if user_mapping:
                    parsed_task['assignee'] = user_mapping['asana_user_id']
                    parsed_task['assignee_info'] = f"{discord_user.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"
                else:
                    parsed_task['assignee_info'] = f"⚠️ {discord_user.mention} (not mapped to Asana user)"
        else:
            # Auto-assign to current user if they have a mapping
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            if user_mapping:
                parsed_task['assignee'] = user_mapping['asana_user_id']
                parsed_task['assignee_info'] = f"Auto-assigned to {interaction.user.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"

        logger.info(f"Successfully parsed task with Grok: {parsed_task['name']} (confidence: {parsed_task.get('confidence', 'unknown')})")
        return parsed_task

    except Exception as e:
        logger.error(f"Error parsing task with Grok: {e}")
        return None

# Natural Language Processing Functions (Fallback to regex if AI fails)
async def parse_natural_language_task(message: str, interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
    """Parse natural language task creation requests using AI first, then regex fallback."""
    # Try AI parsing first
    ai_parsed = await parse_task_with_grok(message, interaction)
    if ai_parsed:
        return ai_parsed

    # Fall back to regex parsing if AI fails or isn't configured
    logger.info("AI parsing failed or not configured, falling back to regex parsing")
    return await parse_natural_language_task_regex(message, interaction)

async def parse_natural_language_task_regex(message: str, interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
    """Parse natural language task creation requests using regex (fallback)."""
    try:
        message_lower = message.lower().strip()

        # Initialize parsed task structure
        parsed_task = {
            'name': None,
            'assignee': None,
            'assignee_info': 'Auto-assigned to you',
            'due_date': None,
            'notes': None,
            'project_id': None,
            'project_info': 'Default project',
            'interpreted_as': message
        }

        # Extract task name - look for common patterns
        task_name_patterns = [
            # "Create a task to [task description]"
            r'create\s+a\s+task\s+to\s+(.+?)(?:\s+(?:for|by|due|assigned|assign)|\s*$)',
            # "Add a task [task description]"
            r'add\s+(?:a\s+)?task\s+(.+?)(?:\s+(?:for|by|due|assigned|assign)|\s*$)',
            # "I need to [task description]"
            r'i\s+need\s+to\s+(.+?)(?:\s+(?:by|due|tomorrow|today|next|\d+|\@)|\s*$)',
            # "Schedule [task description]"
            r'schedule\s+(.+?)(?:\s+(?:for|by|due|at)|\s*$)',
            # "Remind me to [task description]"
            r'remind\s+me\s+to\s+(.+?)(?:\s+(?:by|due|tomorrow|today|next|\d+|\@)|\s*$)',
            # Simple task name in quotes
            r'"([^"]+)"',
            # Simple task name
            r'^(.+?)(?:\s+(?:due|by|tomorrow|today|next|\d+|assigned|assign|@)|\s*$)'
        ]

        task_name = None
        for pattern in task_name_patterns:
            match = re.search(pattern, message_lower)
            if match:
                task_name = match.group(1).strip()
                # Clean up the task name
                task_name = re.sub(r'\s+', ' ', task_name)
                break

        if not task_name:
            return None

        parsed_task['name'] = task_name

        # Extract due date
        due_date = parse_due_date(message)
        if due_date:
            parsed_task['due_date'] = due_date.strftime('%Y-%m-%d')

        # Extract assignee from Discord mentions
        assignee_match = re.search(r'<@!?(\d+)>', message)
        if assignee_match:
            discord_user_id = int(assignee_match.group(1))
            discord_user = interaction.guild.get_member(discord_user_id)

            if discord_user:
                user_mapping = db_manager.get_user_mapping(interaction.guild.id, discord_user_id)
                if user_mapping:
                    parsed_task['assignee'] = user_mapping['asana_user_id']
                    parsed_task['assignee_info'] = f"{discord_user.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"
                else:
                    parsed_task['assignee_info'] = f"⚠️ {discord_user.mention} (not mapped to Asana user)"
        else:
            # Auto-assign to current user if they have a mapping
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, interaction.user.id)
            if user_mapping:
                parsed_task['assignee'] = user_mapping['asana_user_id']
                parsed_task['assignee_info'] = f"Auto-assigned to {interaction.user.mention} → Asana user `{user_mapping['asana_user_name'] or user_mapping['asana_user_id']}`"

        # Extract project if mentioned (basic implementation)
        project_patterns = [
            r'in\s+(?:the\s+)?(.+?)\s+project',
            r'for\s+(?:the\s+)?(.+?)\s+project',
            r'project\s+(.+?)(?:\s|$|due|by|assigned)'
        ]

        for pattern in project_patterns:
            match = re.search(pattern, message_lower)
            if match:
                project_name = match.group(1).strip()
                parsed_task['project_info'] = f"Project: {project_name}"
                break

        # Extract notes/description (anything after "with notes" or "description")
        notes_patterns = [
            r'(?:with\s+notes?|description|notes?)\s*[:\-]?\s*(.+)$',
            r'(?:notes?|description)\s*[:\-]?\s*(.+)$'
        ]

        for pattern in notes_patterns:
            match = re.search(pattern, message_lower)
            if match:
                parsed_task['notes'] = match.group(1).strip()
                break

        return parsed_task

    except Exception as e:
        logger.error(f"Error parsing natural language task: {e}")
        return None

def parse_due_date(message: str) -> Optional[datetime]:
    """Parse due date from natural language."""
    try:
        message_lower = message.lower()
        today = datetime.now().date()

        # Tomorrow
        if 'tomorrow' in message_lower:
            return datetime.combine(today + timedelta(days=1), datetime.min.time())

        # Today
        if 'today' in message_lower:
            return datetime.combine(today, datetime.min.time())

        # Next week
        if 'next week' in message_lower:
            return datetime.combine(today + timedelta(days=7), datetime.min.time())

        # Next month
        if 'next month' in message_lower:
            next_month = today.replace(day=1) + timedelta(days=32)
            next_month = next_month.replace(day=1)
            return datetime.combine(next_month, datetime.min.time())

        # Day names
        day_names = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        for day_name, day_num in day_names.items():
            if f'next {day_name}' in message_lower or f'on {day_name}' in message_lower:
                days_ahead = (day_num - today.weekday()) % 7
                if days_ahead == 0:  # If it's today, get next week
                    days_ahead = 7
                target_date = today + timedelta(days=days_ahead)
                return datetime.combine(target_date, datetime.min.time())

            if day_name in message_lower and f'next {day_name}' not in message_lower:
                days_ahead = (day_num - today.weekday()) % 7
                if days_ahead == 0 and 'this' not in message_lower:  # If it's today and not explicitly "this", get next week
                    days_ahead = 7
                target_date = today + timedelta(days=days_ahead)
                return datetime.combine(target_date, datetime.min.time())

        # Specific date patterns (MM/DD, DD/MM, YYYY-MM-DD)
        date_patterns = [
            r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?',  # MM/DD/YYYY or DD/MM/YYYY
            r'(\d{4})-(\d{1,2})-(\d{1,2})',          # YYYY-MM-DD
        ]

        for pattern in date_patterns:
            match = re.search(pattern, message)
            if match:
                try:
                    if len(match.groups()) == 3 and match.group(3):  # YYYY-MM-DD
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                    else:  # MM/DD or DD/MM - assume MM/DD for now
                        month = int(match.group(1))
                        day = int(match.group(2))
                        year = today.year

                        # If the date has passed this year, assume next year
                        test_date = datetime(year, month, day).date()
                        if test_date < today:
                            year += 1

                    return datetime.combine(datetime(year, month, day).date(), datetime.min.time())
                except ValueError:
                    continue  # Invalid date, try next pattern

        # Relative days (in 3 days, 2 weeks, etc.)
        relative_patterns = [
            (r'in\s+(\d+)\s+days?', lambda m: today + timedelta(days=int(m.group(1)))),
            (r'in\s+(\d+)\s+weeks?', lambda m: today + timedelta(weeks=int(m.group(1)))),
            (r'in\s+(\d+)\s+months?', lambda m: today.replace(day=1) + timedelta(days=32 * int(m.group(1))).replace(day=1)),
        ]

        for pattern, date_func in relative_patterns:
            match = re.search(pattern, message_lower)
            if match:
                target_date = date_func(match)
                return datetime.combine(target_date, datetime.min.time())

        return None

    except Exception as e:
        logger.error(f"Error parsing due date: {e}")
        return None

# Task Confirmation View
class TaskConfirmationView(discord.ui.View):
    """View for confirming task creation from natural language."""

    def __init__(self, parsed_task: Dict[str, Any], interaction: discord.Interaction):
        super().__init__(timeout=300)  # 5 minute timeout
        self.parsed_task = parsed_task
        self.interaction = interaction

    @discord.ui.button(label="✅ Create Task", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and create the task."""
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            # Create the task
            task = await asana_manager.create_task(
                name=self.parsed_task['name'],
                project_id=self.parsed_task.get('project_id'),
                assignee=self.parsed_task.get('assignee'),
                due_date=self.parsed_task.get('due_date'),
                notes=self.parsed_task.get('notes'),
                guild_id=interaction.guild.id
            )

            # Success embed
            success_embed = discord.Embed(
                title="✅ Task Created Successfully!",
                description=f"**{task['name']}** has been created using AI-powered natural language processing!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            success_embed.add_field(name="📋 Task ID", value=f"`{task['gid']}`", inline=True)

            if task.get('projects') and len(task['projects']) > 0:
                project_names = [p['name'] for p in task['projects']]
                success_embed.add_field(name="📁 Project", value=", ".join(project_names), inline=True)
            else:
                success_embed.add_field(name="📁 Project", value="Default project", inline=True)

            if task.get('assignee'):
                asana_assignee_name = task['assignee']['name']
                assignee_display = asana_assignee_name
                if self.parsed_task.get('assignee_info') and "Auto-assigned" in self.parsed_task['assignee_info']:
                    assignee_display += " (Auto-assigned)"
                success_embed.add_field(name="👤 Assignee", value=assignee_display, inline=True)
            elif self.parsed_task.get('assignee_info'):
                success_embed.add_field(name="👤 Assignee Info", value=self.parsed_task['assignee_info'], inline=False)

            if task.get('due_on'):
                success_embed.add_field(name="📅 Due Date", value=task['due_on'], inline=False)

            if task.get('notes'):
                notes = task['notes'][:200] + "..." if len(task['notes']) > 200 else task['notes']
                success_embed.add_field(name="📝 Notes", value=notes, inline=False)

            success_embed.set_footer(text="🤖 Created via Natural Language Processing • Use /chat-create for more AI-powered task creation!")

            await interaction.followup.send(embed=success_embed)

            # Log successful AI task creation
            await error_logger.log_system_event(
                "ai_task_created",
                f"Natural language task creation successful: '{self.parsed_task['interpreted_as']}' -> Task {task['gid']}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "task_id": task['gid'], "parsed_task": self.parsed_task},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "confirm_task_creation")

            error_embed = discord.Embed(
                title="❌ Task Creation Failed",
                description=f"Failed to create the task: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel task creation."""
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_embed = discord.Embed(
            title="❌ Task Creation Cancelled",
            description="The task creation has been cancelled. Use `/chat-create` to try again with different wording.",
            color=discord.Color.grey()
        )
        await interaction.followup.send(embed=cancel_embed)

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        timeout_embed = discord.Embed(
            title="⏰ Confirmation Timed Out",
            description="The task confirmation has expired. Use `/chat-create` to try again.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=timeout_embed, view=self)
        except:
            pass  # Message might have been deleted

# Bulk Task Operations Views
class BulkTaskSelectionView(discord.ui.View):
    """View for selecting multiple tasks for bulk operations."""

    def __init__(self, tasks: List[Dict[str, Any]], interaction: discord.Interaction):
        super().__init__(timeout=600)  # 10 minute timeout
        self.tasks = tasks
        self.interaction = interaction
        self.selected_tasks = set()

        # Create select menu with tasks
        options = []
        for i, task in enumerate(tasks[:25], 1):  # Discord limit of 25 options
            task_name = task.get('name', 'Unnamed Task')
            task_id = task.get('gid', task.get('id', 'Unknown'))

            # Truncate name if too long
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            assignee = task.get('assignee', {}).get('name', 'Unassigned')
            due_date = task.get('due_on', 'No due date')

            label = f"{i}. {task_name}"
            description = f"👤 {assignee} | 📅 {due_date}"

            if len(description) > 50:
                description = description[:47] + "..."

            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=task_id
            ))

        select_menu = BulkTaskSelect(self.tasks, self.selected_tasks)
        self.add_item(select_menu)

    @discord.ui.button(label="✅ Proceed with Selected", style=discord.ButtonStyle.green, disabled=True)
    async def proceed_with_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Proceed to bulk operations with selected tasks."""
        if not self.selected_tasks:
            await interaction.response.send_message("❌ Please select at least one task first.", ephemeral=True)
            return

        # Create bulk operations view
        operations_view = BulkOperationsView(list(self.selected_tasks), self.tasks, interaction)

        selected_count = len(self.selected_tasks)
        embed = discord.Embed(
            title=f"⚙️ Bulk Operations - {selected_count} Task{'s' if selected_count != 1 else ''} Selected",
            description="Choose what operation you want to perform on the selected tasks:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📋 Selected Tasks",
            value="\n".join([f"• {next((t['name'] for t in self.tasks if t.get('gid') == tid or t.get('id') == tid), 'Unknown Task')}" for tid in list(self.selected_tasks)[:5]]),
            inline=False
        )

        if len(self.selected_tasks) > 5:
            embed.set_footer(text=f"And {len(self.selected_tasks) - 5} more tasks...")

        await interaction.response.edit_message(embed=embed, view=operations_view)

    @discord.ui.button(label="🔄 Clear Selection", style=discord.ButtonStyle.secondary)
    async def clear_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clear all selected tasks."""
        self.selected_tasks.clear()
        self.children[0].max_values = min(25, len(self.tasks))  # Reset select menu
        self.children[1].disabled = True  # Disable proceed button

        embed = discord.Embed(
            title="🔄 Selection Cleared",
            description="All tasks have been deselected. Choose the tasks you want to operate on:",
            color=discord.Color.blue()
        )

        await interaction.response.edit_message(embed=embed, view=self)

class BulkTaskSelect(discord.ui.Select):
    """Select menu for choosing multiple tasks."""

    def __init__(self, tasks: List[Dict[str, Any]], selected_tasks: set):
        self.all_tasks = tasks
        self.selected_tasks = selected_tasks

        # Create options for the select menu
        options = []
        for i, task in enumerate(tasks[:25], 1):  # Discord limits to 25 options
            task_name = task.get('name', 'Unnamed Task')
            task_id = task.get('gid', task.get('id', 'Unknown'))

            # Truncate name if too long
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            assignee = task.get('assignee', {}).get('name', 'Unassigned')
            due_date = task.get('due_on', 'No due date')

            label = f"{i}. {task_name}"
            description = f"👤 {assignee} | 📅 {due_date}"

            if len(description) > 50:
                description = description[:47] + "..."

            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=task_id
            ))

        super().__init__(
            placeholder=f"Select tasks to operate on (0/{len(tasks)} selected)",
            min_values=0,
            max_values=min(25, len(tasks)),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle task selection."""
        # Update selected tasks
        self.selected_tasks.clear()
        self.selected_tasks.update(self.values)

        # Update placeholder and button state
        parent_view = self.view
        selected_count = len(self.selected_tasks)

        self.placeholder = f"Select tasks to operate on ({selected_count}/{len(self.all_tasks)} selected)"

        # Enable/disable proceed button
        proceed_button = next((item for item in parent_view.children if hasattr(item, 'label') and "Proceed" in item.label), None)
        if proceed_button:
            proceed_button.disabled = selected_count == 0

        await interaction.response.edit_message(view=parent_view)

class BulkOperationsView(discord.ui.View):
    """View for choosing bulk operations to perform."""

    def __init__(self, selected_task_ids: List[str], all_tasks: List[Dict[str, Any]], interaction: discord.Interaction):
        super().__init__(timeout=600)  # 10 minute timeout
        self.selected_task_ids = selected_task_ids
        self.all_tasks = all_tasks
        self.interaction = interaction

    @discord.ui.button(label="✅ Complete All", style=discord.ButtonStyle.green, emoji="✅")
    async def complete_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark all selected tasks as completed."""
        await interaction.response.defer()

        try:
            completed_count = 0
            failed_tasks = []

            for task_id in self.selected_task_ids:
                try:
                    await asana_manager.complete_task(task_id)
                    completed_count += 1
                except Exception as e:
                    task_name = next((t['name'] for t in self.all_tasks if t.get('gid') == task_id or t.get('id') == task_id), 'Unknown Task')
                    failed_tasks.append(f"{task_name}: {str(e)}")

            # Create results embed
            embed = discord.Embed(
                title="✅ Bulk Completion Results",
                description=f"Successfully completed {completed_count} out of {len(self.selected_task_ids)} tasks.",
                color=discord.Color.green() if completed_count > 0 else discord.Color.red(),
                timestamp=datetime.now()
            )

            if failed_tasks:
                embed.add_field(
                    name="❌ Failed Tasks",
                    value="\n".join(failed_tasks[:5]),  # Limit to 5 failures
                    inline=False
                )

            embed.set_footer(text="Tasks completed via bulk operations")

            await interaction.followup.send(embed=embed)

            # Log bulk operation
            await error_logger.log_system_event(
                "bulk_operation",
                f"Bulk completion: {completed_count}/{len(self.selected_task_ids)} tasks completed",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "operation": "complete", "success_count": completed_count, "total_count": len(self.selected_task_ids)},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "bulk_complete")

            error_embed = discord.Embed(
                title="❌ Bulk Completion Failed",
                description=f"Failed to complete tasks: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

    @discord.ui.button(label="👤 Reassign All", style=discord.ButtonStyle.primary, emoji="👤")
    async def reassign_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reassign all selected tasks to a new user."""
        # Create reassignment modal
        modal = BulkReassignmentModal(self.selected_task_ids, self.all_tasks)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📅 Update Due Dates", style=discord.ButtonStyle.primary, emoji="📅")
    async def update_due_dates(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Update due dates for all selected tasks."""
        # Create due date update modal
        modal = BulkDueDateModal(self.selected_task_ids, self.all_tasks)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_operation(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the bulk operation."""
        cancel_embed = discord.Embed(
            title="❌ Bulk Operation Cancelled",
            description="The bulk operation has been cancelled.",
            color=discord.Color.grey()
        )
        await interaction.response.edit_message(embed=cancel_embed, view=None)

class BulkReassignmentModal(discord.ui.Modal, title="Bulk Reassign Tasks"):
    """Modal for bulk reassignment of tasks."""

    assignee = discord.ui.TextInput(
        label="New Assignee (Discord @mention or Asana ID)",
        placeholder="@username or Asana User ID",
        required=True,
        max_length=100
    )

    def __init__(self, selected_task_ids: List[str], all_tasks: List[Dict[str, Any]]):
        super().__init__()
        self.selected_task_ids = selected_task_ids
        self.all_tasks = all_tasks

    async def on_submit(self, interaction: discord.Interaction):
        """Handle bulk reassignment submission."""
        await interaction.response.defer()

        try:
            # Parse assignee
            assignee_input = str(self.assignee).strip()
            asana_assignee = None

            # Check if it's a Discord mention
            mention_match = re.search(r'<@!?(\d+)>', assignee_input)
            if mention_match:
                discord_user_id = int(mention_match.group(1))
                discord_user = interaction.guild.get_member(discord_user_id)

                if discord_user:
                    user_mapping = db_manager.get_user_mapping(interaction.guild.id, discord_user_id)
                    if user_mapping:
                        asana_assignee = user_mapping['asana_user_id']
                        assignee_display = f"{discord_user.mention} → Asana user `{user_mapping['asana_user_name']}`"
                    else:
                        error_embed = discord.Embed(
                            title="❌ User Not Mapped",
                            description=f"{discord_user.mention} is not mapped to an Asana user. Use `/map-user` first.",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=error_embed)
                        return
                else:
                    error_embed = discord.Embed(
                        title="❌ User Not Found",
                        description="The mentioned user was not found in this server.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=error_embed)
                    return
            else:
                # Assume it's an Asana user ID
                asana_assignee = assignee_input
                assignee_display = f"Asana user ID: `{asana_assignee}`"

            # Perform bulk reassignment
            reassigned_count = 0
            failed_tasks = []

            for task_id in self.selected_task_ids:
                try:
                    await asana_manager.update_task(task_id=task_id, assignee=asana_assignee)
                    reassigned_count += 1
                except Exception as e:
                    task_name = next((t['name'] for t in self.all_tasks if t.get('gid') == task_id or t.get('id') == task_id), 'Unknown Task')
                    failed_tasks.append(f"{task_name}: {str(e)}")

            # Create results embed
            embed = discord.Embed(
                title="👤 Bulk Reassignment Results",
                description=f"Successfully reassigned {reassigned_count} out of {len(self.selected_task_ids)} tasks to {assignee_display}.",
                color=discord.Color.green() if reassigned_count > 0 else discord.Color.red(),
                timestamp=datetime.now()
            )

            if failed_tasks:
                embed.add_field(
                    name="❌ Failed Tasks",
                    value="\n".join(failed_tasks[:3]),  # Limit to 3 failures
                    inline=False
                )

            embed.set_footer(text="Tasks reassigned via bulk operations")

            await interaction.followup.send(embed=embed)

            # Log bulk operation
            await error_logger.log_system_event(
                "bulk_operation",
                f"Bulk reassignment: {reassigned_count}/{len(self.selected_task_ids)} tasks reassigned",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "operation": "reassign", "assignee": assignee_display, "success_count": reassigned_count},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "bulk_reassign")

            error_embed = discord.Embed(
                title="❌ Bulk Reassignment Failed",
                description=f"Failed to reassign tasks: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

class BulkDueDateModal(discord.ui.Modal, title="Bulk Update Due Dates"):
    """Modal for bulk due date updates."""

    due_date = discord.ui.TextInput(
        label="New Due Date (YYYY-MM-DD format)",
        placeholder="2025-12-31",
        required=True,
        max_length=10
    )

    def __init__(self, selected_task_ids: List[str], all_tasks: List[Dict[str, Any]]):
        super().__init__()
        self.selected_task_ids = selected_task_ids
        self.all_tasks = all_tasks

    async def on_submit(self, interaction: discord.Interaction):
        """Handle bulk due date update submission."""
        await interaction.response.defer()

        try:
            due_date_str = str(self.due_date).strip()

            # Validate date format
            try:
                datetime.strptime(due_date_str, '%Y-%m-%d')
            except ValueError:
                error_embed = discord.Embed(
                    title="❌ Invalid Date Format",
                    description="Please use YYYY-MM-DD format (e.g., 2025-12-31).",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed)
                return

            # Perform bulk due date update
            updated_count = 0
            failed_tasks = []

            for task_id in self.selected_task_ids:
                try:
                    await asana_manager.update_task(task_id=task_id, due_date=due_date_str)
                    updated_count += 1
                except Exception as e:
                    task_name = next((t['name'] for t in self.all_tasks if t.get('gid') == task_id or t.get('id') == task_id), 'Unknown Task')
                    failed_tasks.append(f"{task_name}: {str(e)}")

            # Create results embed
            embed = discord.Embed(
                title="📅 Bulk Due Date Update Results",
                description=f"Successfully updated due dates for {updated_count} out of {len(self.selected_task_ids)} tasks to **{due_date_str}**.",
                color=discord.Color.green() if updated_count > 0 else discord.Color.red(),
                timestamp=datetime.now()
            )

            if failed_tasks:
                embed.add_field(
                    name="❌ Failed Tasks",
                    value="\n".join(failed_tasks[:3]),  # Limit to 3 failures
                    inline=False
                )

            embed.set_footer(text="Due dates updated via bulk operations")

            await interaction.followup.send(embed=embed)

            # Log bulk operation
            await error_logger.log_system_event(
                "bulk_operation",
                f"Bulk due date update: {updated_count}/{len(self.selected_task_ids)} tasks updated to {due_date_str}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "operation": "update_due_date", "due_date": due_date_str, "success_count": updated_count},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "bulk_update_due_date")

            error_embed = discord.Embed(
                title="❌ Bulk Due Date Update Failed",
                description=f"Failed to update due dates: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

# Enhanced Notification Functions
async def send_assignment_notification(task: Dict[str, Any], asana_assignee_id: str):
    """Send assignment notification to Discord user if they have notifications enabled."""
    try:
        # Find Discord user mapping for this Asana user
        user_mapping = db_manager.get_user_mapping_by_asana_id(asana_assignee_id)
        if not user_mapping:
            return  # No Discord user mapped to this Asana user

        # Check notification preferences
        prefs = db_manager.get_notification_preferences(user_mapping['discord_user_id'], user_mapping['guild_id'])
        if not prefs or prefs.get('assignment_notifications') == 'disabled':
            return  # User has disabled assignment notifications

        # Get Discord user and guild
        guild = bot.get_guild(user_mapping['guild_id'])
        if not guild:
            return

        discord_user = guild.get_member(user_mapping['discord_user_id'])
        if not discord_user:
            return

        # Create notification embed
        embed = discord.Embed(
            title="📋 Task Assigned to You",
            description=f"You have been assigned to **{task['name']}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.add_field(name="📝 Task", value=task['name'], inline=False)

        if task.get('due_on'):
            embed.add_field(name="📅 Due Date", value=task['due_on'], inline=True)

        if task.get('notes'):
            notes = task['notes'][:200] + "..." if len(task['notes']) > 200 else task['notes']
            embed.add_field(name="📋 Notes", value=notes, inline=False)

        embed.add_field(name="🔗 View Task", value=f"Use `/view-task task_id:{task['gid']}` to see full details", inline=False)

        embed.set_footer(text=f"Task ID: {task['gid']} • Use /notification-settings to change preferences")

        # Try to send DM to user
        try:
            await discord_user.send(embed=embed)
        except discord.Forbidden:
            # If DM fails, we could send to a notification channel, but for now we'll just skip
            pass

    except Exception as e:
        logger.error(f"Error sending assignment notification: {e}")

async def send_due_date_reminder(task: Dict[str, Any], asana_assignee_id: str, reminder_type: str):
    """Send due date reminder based on user preferences."""
    try:
        # Find Discord user mapping for this Asana user
        user_mapping = db_manager.get_user_mapping_by_asana_id(asana_assignee_id)
        if not user_mapping:
            return

        # Check notification preferences
        prefs = db_manager.get_notification_preferences(user_mapping['discord_user_id'], user_mapping['guild_id'])
        if not prefs or prefs.get('due_date_reminder') == 'disabled':
            return

        # Check if this reminder type matches user preference
        if prefs.get('due_date_reminder') != reminder_type:
            return

        # Get Discord user and guild
        guild = bot.get_guild(user_mapping['guild_id'])
        if not guild:
            return

        discord_user = guild.get_member(user_mapping['discord_user_id'])
        if not discord_user:
            return

        # Create reminder embed
        reminder_messages = {
            '1_hour': ('⏱️ Task Due in 1 Hour', 'This task is due within the next hour!'),
            '1_day': ('⏰ Task Due Tomorrow', 'This task is due within the next 24 hours.'),
            '1_week': ('📅 Task Due in 1 Week', 'This task is due within the next 7 days.')
        }

        title, description = reminder_messages.get(reminder_type, ('📅 Task Due Soon', 'This task is approaching its due date.'))

        embed = discord.Embed(
            title=title,
            description=f"{description}\n\n**{task['name']}**",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )

        embed.add_field(name="📅 Due Date", value=task['due_on'], inline=True)
        embed.add_field(name="⏰ Time Remaining", value=get_time_until_due(task['due_on']), inline=True)
        embed.add_field(name="🔗 View Task", value=f"Use `/view-task task_id:{task['gid']}` to see details", inline=False)

        embed.set_footer(text=f"Task ID: {task['gid']} • Use /notification-settings to adjust reminders")

        # Try to send DM to user
        try:
            await discord_user.send(embed=embed)
        except discord.Forbidden:
            pass

    except Exception as e:
        logger.error(f"Error sending due date reminder: {e}")

def get_time_until_due(due_date_str: str) -> str:
    """Get human-readable time until due date."""
    try:
        due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
        now = datetime.now(due_date.tzinfo) if due_date.tzinfo else datetime.now()

        if due_date <= now:
            return "Overdue!"

        delta = due_date - now

        if delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''}"

        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"

        minutes = delta.seconds // 60
        if minutes > 0:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"

        return "Less than 1 minute"

    except Exception:
        return "Unknown"

def format_duration(seconds: int) -> str:
    """Format seconds into human readable duration."""
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"

    hours = minutes // 60
    minutes = minutes % 60

    if hours < 24:
        return f"{hours}h {minutes}m"

    days = hours // 24
    hours = hours % 24

    return f"{days}d {hours}h {minutes}m"

def check_timeclock_channel(interaction: discord.Interaction) -> bool:
    """Check if the command is being used in the designated timeclock channel."""
    timeclock_channel = db_manager.get_timeclock_channel(interaction.guild.id)

    if timeclock_channel and interaction.channel.id != timeclock_channel['channel_id']:
        # Get the channel object for mention
        channel = interaction.guild.get_channel(timeclock_channel['channel_id'])
        channel_mention = f"#{timeclock_channel['channel_name']}" if channel else f"#{timeclock_channel['channel_name']}"

        embed = discord.Embed(
            title="❌ Wrong Channel",
            description="Time tracking commands can only be used in the designated timeclock channel.",
            color=discord.Color.red()
        )

        embed.add_field(
            name="📍 Designated Channel",
            value=channel_mention,
            inline=True
        )

        embed.add_field(
            name="🕐 Available Commands",
            value="• `/clock-in`\n• `/clock-out`\n• `/time-status`\n• `/time-history`",
            inline=False
        )

        embed.set_footer(text="Use /set-timeclock-channel to change the designated channel (Admin only)")

        # Send response without deferring since we're rejecting the command
        if not interaction.response.is_done():
            interaction.response.send_message(embed=embed)
        else:
            interaction.followup.send(embed=embed)

        return False

    return True

async def get_today_total_time(guild_id: int, discord_user_id: int) -> str:
    """Get total time worked today for a user."""
    try:
        from datetime import date

        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())

        # Get all entries for today
        with db_manager.get_session() as session:
            entries = session.query(TimeEntry).filter(
                TimeEntry.guild_id == guild_id,
                TimeEntry.discord_user_id == discord_user_id,
                TimeEntry.clock_in_time >= today_start,
                TimeEntry.status == 'completed'
            ).all()

            total_seconds = sum(entry.duration_seconds or 0 for entry in entries)
            return format_duration(total_seconds)

    except Exception as e:
        logger.error(f"Error calculating today's total time: {e}")
        return "Unknown"

async def create_timeclock_asana_task(interaction, entry_id: int, event_type: str, time_proof_link: str = None, notes: str = None):
    """Create or update Asana task for timeclock events."""
    try:
        # Try to find or create a "timeclock" project in Asana
        timeclock_project_name = "TimeClock"

        # Check if project already exists
        try:
            projects = asana_client.projects.get_projects({'workspace': ASANA_WORKSPACE_ID})
            timeclock_project = None

            for project in projects:
                if project['name'].lower() == timeclock_project_name.lower():
                    timeclock_project = project
                    break

            # Create project if it doesn't exist
            if not timeclock_project:
                timeclock_project = asana_client.projects.create_project({
                    'name': timeclock_project_name,
                    'workspace': ASANA_WORKSPACE_ID,
                    'notes': 'Automated time tracking for Discord timeclock sessions'
                })
                logger.info(f"Created Asana project: {timeclock_project_name}")

        except Exception as e:
            logger.warning(f"Could not create/access Asana timeclock project: {e}")
            return

        # Get time entry details
        with db_manager.get_session() as session:
            entry = session.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
            if not entry:
                return

            # Create task name based on event type
            if event_type == "clock_in":
                task_name = f"🕐 {entry.discord_username or 'Unknown User'} - Time Session Started"
                task_notes = f"**Clock In Event**\n"
                task_notes += f"**Employee:** {entry.discord_username or 'Unknown User'}\n"
                task_notes += f"**Start Time:** {entry.clock_in_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                task_notes += f"**Discord User ID:** {entry.discord_user_id}\n"
                task_notes += f"**Entry ID:** {entry.id}\n\n"
                task_notes += "This task will be updated when the user clocks out."

            elif event_type == "clock_out":
                task_name = f"🕐 {entry.discord_username or 'Unknown User'} - Time Session Completed"
                duration = format_duration(entry.duration_seconds or 0)
                task_notes = f"**Clock Out Event**\n"
                task_notes += f"**Employee:** {entry.discord_username or 'Unknown User'}\n"
                task_notes += f"**Start Time:** {entry.clock_in_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                task_notes += f"**End Time:** {entry.clock_out_time.strftime('%Y-%m-%d %H:%M:%S UTC') if entry.clock_out_time else 'Unknown'}\n"
                task_notes += f"**Duration:** {duration}\n"
                task_notes += f"**Discord User ID:** {entry.discord_user_id}\n"
                task_notes += f"**Entry ID:** {entry.id}\n"

                if time_proof_link:
                    task_notes += f"**Time Proof:** {time_proof_link}\n"

                if notes:
                    task_notes += f"**Notes:** {notes}\n"

                if entry.duration_seconds:
                    # Mark task as completed if session was over 30 minutes
                    if entry.duration_seconds > 1800:  # 30 minutes
                        task_notes += f"\n**Status:** Completed session ({duration})"

            else:
                return

            # Create Asana task
            task_data = {
                'name': task_name,
                'notes': task_notes,
                'projects': [timeclock_project['gid']],
                'workspace': ASANA_WORKSPACE_ID
            }

            # Try to assign to Asana user if mapped
            user_mapping = db_manager.get_user_mapping(interaction.guild.id, entry.discord_user_id)
            if user_mapping:
                task_data['assignee'] = user_mapping['asana_user_id']

            # Create the task
            asana_task = asana_client.tasks.create_task(task_data)

            # Update the time entry with the Asana task ID
            entry.asana_task_gid = asana_task['gid']
            session.commit()

            logger.info(f"Created Asana task for time entry {entry_id}: {asana_task['gid']}")

    except Exception as e:
        logger.error(f"Error creating Asana task for timeclock event: {e}")

# Chat Channel Message Handling
async def handle_chat_channel_request(message):
    """Handle natural language task creation requests in designated chat channels."""
    try:
        # Extract the message content, removing the bot mention
        content = message.content

        # Remove the bot mention from the content
        # This handles both <@123456789> and <@!123456789> formats
        content = re.sub(r'<@!?' + str(bot.user.id) + r'>', '', content).strip()

        # If the message is empty after removing the mention, provide help
        if not content:
            embed = discord.Embed(
                title="🤖 How to Create Tasks",
                description="I can help you create Asana tasks using natural language!",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="💬 Examples",
                value="• `Create a task to fix the login bug due tomorrow`\n• `Add a new task called review code assigned to @developer`\n• `Schedule a meeting with the team for Friday`\n• `Remind me to update documentation next week`",
                inline=False
            )
            embed.add_field(
                name="📝 What I Understand",
                value="• Task names and descriptions\n• Due dates (tomorrow, next week, specific dates)\n• @mentions for assignment\n• Project references",
                inline=False
            )
            await message.reply(embed=embed)
            return

        # Create a mock interaction object for compatibility with existing parsing functions
        class MockInteraction:
            def __init__(self, message):
                self.guild = message.guild
                self.user = message.author
                self.message = message

        mock_interaction = MockInteraction(message)

        # Parse the natural language message
        parsed_task = await parse_natural_language_task(content, mock_interaction)

        if not parsed_task:
            embed = discord.Embed(
                title="❓ Couldn't Understand Request",
                description="I couldn't parse your task request. Try rephrasing it!",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="💡 Examples of what I understand:",
                value="• 'Create a task to fix the login bug due tomorrow'\n• 'Add a new task called review code assigned to @developer'\n• 'Schedule a meeting with the team for Friday'\n• 'Remind me to update documentation next week'",
                inline=False
            )
            embed.add_field(
                name="🔧 Alternative",
                value="You can also use `/create-task` with specific parameters if natural language doesn't work.",
                inline=False
            )
            await message.reply(embed=embed)
            return

        # Show what was parsed with confirmation buttons
        confirmation_embed = discord.Embed(
            title="🤖 Task Parsed from Your Message",
            description=f"I interpreted your request as: **{parsed_task['interpreted_as']}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        confirmation_embed.add_field(
            name="📋 Task Details",
            value=f"**Name:** {parsed_task['name']}\n"
                  f"**Assignee:** {parsed_task.get('assignee_info', 'Auto-assigned to you')}\n"
                  f"**Due Date:** {parsed_task.get('due_date', 'No due date')}\n"
                  f"**Project:** {parsed_task.get('project_info', 'Default project')}",
            inline=False
        )

        confirmation_embed.add_field(
            name="✅ Confirm Creation?",
            value="React with ✅ to create this task, or ❌ to cancel.",
            inline=False
        )

        # Create confirmation view
        view = ChatTaskConfirmationView(parsed_task, message)
        await message.reply(embed=confirmation_embed, view=view)

        # Log the AI interpretation
        await error_logger.log_system_event(
            "ai_interpretation",
            f"Chat channel task creation: '{content}' -> '{parsed_task['interpreted_as']}'",
            {"user_id": message.author.id, "guild_id": message.guild.id, "channel_id": message.channel.id, "parsed_task": parsed_task},
            "INFO"
        )

    except Exception as e:
        logger.error(f"Error handling chat channel request: {e}")

        embed = discord.Embed(
            title="❌ Processing Failed",
            description=f"I encountered an error while processing your request: {str(e)}",
            color=discord.Color.red()
        )
        await message.reply(embed=embed)

# Chat Channel Task Confirmation View
class ChatTaskConfirmationView(discord.ui.View):
    """View for confirming task creation from chat channel messages."""

    def __init__(self, parsed_task: Dict[str, Any], message: discord.Message):
        super().__init__(timeout=300)  # 5 minute timeout
        self.parsed_task = parsed_task
        self.message = message

    @discord.ui.button(label="✅ Create Task", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and create the task."""
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            # Create the task
            task = await asana_manager.create_task(
                name=self.parsed_task['name'],
                project_id=self.parsed_task.get('project_id'),
                assignee=self.parsed_task.get('assignee'),
                due_date=self.parsed_task.get('due_date'),
                notes=self.parsed_task.get('notes'),
                guild_id=interaction.guild.id
            )

            # Success embed
            success_embed = discord.Embed(
                title="✅ Task Created Successfully!",
                description=f"**{task['name']}** has been created using AI-powered natural language processing!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            success_embed.add_field(name="📋 Task ID", value=f"`{task['gid']}`", inline=True)

            if task.get('projects') and len(task['projects']) > 0:
                project_names = [p['name'] for p in task['projects']]
                success_embed.add_field(name="📁 Project", value=", ".join(project_names), inline=True)
            else:
                success_embed.add_field(name="📁 Project", value="Default project", inline=True)

            if task.get('assignee'):
                asana_assignee_name = task['assignee']['name']
                assignee_display = asana_assignee_name
                if self.parsed_task.get('assignee_info') and "Auto-assigned" in self.parsed_task['assignee_info']:
                    assignee_display += " (Auto-assigned)"
                success_embed.add_field(name="👤 Assignee", value=assignee_display, inline=True)
            elif self.parsed_task.get('assignee_info'):
                success_embed.add_field(name="👤 Assignee Info", value=self.parsed_task['assignee_info'], inline=False)

            if task.get('due_on'):
                success_embed.add_field(name="📅 Due Date", value=task['due_on'], inline=False)

            if task.get('notes'):
                notes = task['notes'][:200] + "..." if len(task['notes']) > 200 else task['notes']
                success_embed.add_field(name="📝 Notes", value=notes, inline=False)

            success_embed.set_footer(text="🤖 Created via Chat Channel • Use @Botsana for more natural language task creation!")

            await interaction.followup.send(embed=success_embed)

            # Log successful AI task creation
            await error_logger.log_system_event(
                "ai_task_created",
                f"Chat channel task creation successful: '{self.parsed_task['interpreted_as']}' -> Task {task['gid']}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "task_id": task['gid'], "parsed_task": self.parsed_task},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "confirm_chat_task_creation")

            error_embed = discord.Embed(
                title="❌ Task Creation Failed",
                description=f"Failed to create the task: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel task creation."""
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_embed = discord.Embed(
            title="❌ Task Creation Cancelled",
            description="The task creation has been cancelled.",
            color=discord.Color.grey()
        )
        await interaction.followup.send(embed=cancel_embed)

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        timeout_embed = discord.Embed(
            title="⏰ Confirmation Timed Out",
            description="The task confirmation has expired. Mention me again to try creating a task.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=timeout_embed, view=self)
        except:
            pass  # Message might have been deleted

# Template Task Confirmation View
class TemplateTaskConfirmationView(discord.ui.View):
    """View for confirming task creation from a template."""

    def __init__(self, template_data, task_name, task_assignee, task_project, task_due_date, task_notes, interaction):
        super().__init__(timeout=300)  # 5 minute timeout
        self.template_data = template_data
        self.task_name = task_name
        self.task_assignee = task_assignee
        self.task_project = task_project
        self.task_due_date = task_due_date
        self.task_notes = task_notes
        self.interaction = interaction

    @discord.ui.button(label="✅ Create Task", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and create the task from template."""
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            # Create the task
            task = await asana_manager.create_task(
                name=self.task_name,
                project_id=self.task_project,
                assignee=self.task_assignee,
                due_date=self.task_due_date,
                notes=self.task_notes,
                guild_id=interaction.guild.id
            )

            # Update template usage count
            db_manager.update_task_template_usage(self.template_data['id'])

            # Success embed
            success_embed = discord.Embed(
                title="✅ Task Created from Template!",
                description=f"**{task['name']}** has been created using template **{self.template_data['name']}**!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            success_embed.add_field(name="📋 Task ID", value=f"`{task['gid']}`", inline=True)

            if task.get('projects') and len(task['projects']) > 0:
                project_names = [p['name'] for p in task['projects']]
                success_embed.add_field(name="📁 Project", value=", ".join(project_names), inline=True)
            else:
                success_embed.add_field(name="📁 Project", value="Default project", inline=True)

            if task.get('assignee'):
                asana_assignee_name = task['assignee']['name']
                assignee_display = asana_assignee_name
                if self.task_assignee and "Auto-assigned" not in assignee_display:
                    assignee_display += " (From template)"
                success_embed.add_field(name="👤 Assignee", value=assignee_display, inline=True)

            if task.get('due_on'):
                success_embed.add_field(name="📅 Due Date", value=task['due_on'], inline=False)

            if task.get('notes'):
                notes = task['notes'][:200] + "..." if len(task['notes']) > 200 else task['notes']
                success_embed.add_field(name="📝 Notes", value=notes, inline=False)

            success_embed.set_footer(text=f"🤖 Created from template • Template used {self.template_data['usage_count'] + 1} time(s)")

            await interaction.followup.send(embed=success_embed)

            # Log successful template usage
            await error_logger.log_system_event(
                "template_used",
                f"Task template '{self.template_data['name']}' used to create task {task['gid']}",
                {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "template_id": self.template_data['id'], "task_id": task['gid']},
                "INFO"
            )

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "confirm_template_task_creation")

            error_embed = discord.Embed(
                title="❌ Task Creation Failed",
                description=f"Failed to create task from template: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel task creation."""
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_embed = discord.Embed(
            title="❌ Task Creation Cancelled",
            description="The task creation has been cancelled.",
            color=discord.Color.grey()
        )
        await interaction.followup.send(embed=cancel_embed)

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        timeout_embed = discord.Embed(
            title="⏰ Confirmation Timed Out",
            description="The task confirmation has expired. Use `/use-template` again to try creating a task.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=timeout_embed, view=self)
        except:
            pass  # Message might have been deleted

# Template Deletion Confirmation View
class TemplateDeletionView(discord.ui.View):
    """View for confirming template deletion."""

    def __init__(self, template_id, template_name, interaction):
        super().__init__(timeout=300)  # 5 minute timeout
        self.template_id = template_id
        self.template_name = template_name
        self.interaction = interaction

    @discord.ui.button(label="🗑️ Delete Template", style=discord.ButtonStyle.red, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm template deletion."""
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            # Delete the template
            success = db_manager.delete_task_template(self.template_id)

            if success:
                embed = discord.Embed(
                    title="✅ Template Deleted",
                    description=f"Template **{self.template_name}** has been permanently deleted.",
                    color=discord.Color.green()
                )

                embed.set_footer(text="This action cannot be undone")

                await interaction.followup.send(embed=embed)

                # Log template deletion
                await error_logger.log_system_event(
                    "template_deleted",
                    f"Task template '{self.template_name}' deleted by {interaction.user.display_name}",
                    {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "template_name": self.template_name},
                    "WARNING"
                )
            else:
                embed = discord.Embed(
                    title="❌ Deletion Failed",
                    description="Failed to delete the template. It may have already been deleted.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "confirm_template_deletion")

            error_embed = discord.Embed(
                title="❌ Deletion Failed",
                description=f"An error occurred while deleting the template: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel template deletion."""
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_embed = discord.Embed(
            title="❌ Deletion Cancelled",
            description="The template deletion has been cancelled.",
            color=discord.Color.grey()
        )
        await interaction.followup.send(embed=cancel_embed)

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        timeout_embed = discord.Embed(
            title="⏰ Deletion Timed Out",
            description="The template deletion confirmation has expired. The template was not deleted.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=timeout_embed, view=self)
        except:
            pass  # Message might have been deleted

# Search Deletion Confirmation View
class SearchDeletionView(discord.ui.View):
    """View for confirming search deletion."""

    def __init__(self, search_id, search_name, interaction):
        super().__init__(timeout=300)  # 5 minute timeout
        self.search_id = search_id
        self.search_name = search_name
        self.interaction = interaction

    @discord.ui.button(label="🗑️ Delete Search", style=discord.ButtonStyle.red, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm search deletion."""
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            # Delete the search
            success = db_manager.delete_saved_search(self.search_id)

            if success:
                embed = discord.Embed(
                    title="✅ Search Deleted",
                    description=f"Saved search **{self.search_name}** has been permanently deleted.",
                    color=discord.Color.green()
                )

                embed.set_footer(text="This action cannot be undone")

                await interaction.followup.send(embed=embed)

                # Log search deletion
                await error_logger.log_system_event(
                    "search_deleted",
                    f"Saved search '{self.search_name}' deleted by {interaction.user.display_name}",
                    {"user_id": interaction.user.id, "guild_id": interaction.guild.id, "search_name": self.search_name},
                    "WARNING"
                )
            else:
                embed = discord.Embed(
                    title="❌ Deletion Failed",
                    description="Failed to delete the search. It may have already been deleted.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await error_logger.log_command_error(interaction, e, "confirm_search_deletion")

            error_embed = discord.Embed(
                title="❌ Deletion Failed",
                description=f"An error occurred while deleting the search: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel search deletion."""
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_embed = discord.Embed(
            title="❌ Deletion Cancelled",
            description="The search deletion has been cancelled.",
            color=discord.Color.grey()
        )
        await interaction.followup.send(embed=cancel_embed)

    async def on_timeout(self):
        """Handle when the view times out."""
        # Disable all components
        for item in self.children:
            item.disabled = True

        timeout_embed = discord.Embed(
            title="⏰ Deletion Timed Out",
            description="The search deletion confirmation has expired. The search was not deleted.",
            color=discord.Color.yellow()
        )

        try:
            await self.message.edit(embed=timeout_embed, view=self)
        except:
            pass  # Message might have been deleted

# Notification Settings View
class NotificationSettingsView(discord.ui.View):
    """View for managing notification preferences."""

    def __init__(self, current_prefs: Dict[str, Any], interaction: discord.Interaction):
        super().__init__(timeout=600)  # 10 minute timeout
        self.current_prefs = current_prefs
        self.interaction = interaction

    @discord.ui.select(
        placeholder="Choose due date reminder timing...",
        options=[
            discord.SelectOption(label="1 day before due date", value="1_day", emoji="⏰", description="Get reminded 24 hours before tasks are due"),
            discord.SelectOption(label="1 hour before due date", value="1_hour", emoji="⏱️", description="Get reminded 1 hour before tasks are due"),
            discord.SelectOption(label="1 week before due date", value="1_week", emoji="📅", description="Get reminded 7 days before tasks are due"),
            discord.SelectOption(label="Disable due date reminders", value="disabled", emoji="🚫", description="Turn off due date reminders")
        ]
    )
    async def due_date_reminder_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle due date reminder preference selection."""
        selected_value = select.values[0]

        # Update preferences
        success = db_manager.set_notification_preferences(
            discord_user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            due_date_reminder=selected_value,
            assignment_notifications=self.current_prefs.get('assignment_notifications', 'enabled')
        )

        if success:
            embed = discord.Embed(
                title="✅ Due Date Reminder Updated",
                description=f"Your due date reminder preference has been set to: **{select.selected_options[0].label}**",
                color=discord.Color.green()
            )

            # Update current prefs
            self.current_prefs['due_date_reminder'] = selected_value

            await interaction.response.edit_message(embed=embed, view=self)
        else:
            error_embed = discord.Embed(
                title="❌ Update Failed",
                description="Failed to update your due date reminder preference. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    @discord.ui.select(
        placeholder="Choose assignment notification setting...",
        options=[
            discord.SelectOption(label="Notify when assigned to tasks", value="enabled", emoji="✅", description="Get notified when tasks are assigned to you"),
            discord.SelectOption(label="Disable assignment notifications", value="disabled", emoji="🚫", description="Turn off assignment notifications")
        ]
    )
    async def assignment_notification_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle assignment notification preference selection."""
        selected_value = select.values[0]

        # Update preferences
        success = db_manager.set_notification_preferences(
            discord_user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            due_date_reminder=self.current_prefs.get('due_date_reminder', '1_day'),
            assignment_notifications=selected_value
        )

        if success:
            embed = discord.Embed(
                title="✅ Assignment Notification Updated",
                description=f"Your assignment notification preference has been set to: **{select.selected_options[0].label}**",
                color=discord.Color.green()
            )

            # Update current prefs
            self.current_prefs['assignment_notifications'] = selected_value

            await interaction.response.edit_message(embed=embed, view=self)
        else:
            error_embed = discord.Embed(
                title="❌ Update Failed",
                description="Failed to update your assignment notification preference. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    @discord.ui.button(label="🔄 Reset to Defaults", style=discord.ButtonStyle.secondary)
    async def reset_to_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset preferences to defaults."""
        success = db_manager.set_notification_preferences(
            discord_user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            due_date_reminder='1_day',
            assignment_notifications='enabled'
        )

        if success:
            embed = discord.Embed(
                title="🔄 Preferences Reset",
                description="Your notification preferences have been reset to defaults:\n• Due date reminders: 1 day before\n• Assignment notifications: Enabled",
                color=discord.Color.blue()
            )

            # Reset current prefs
            self.current_prefs = {'due_date_reminder': '1_day', 'assignment_notifications': 'enabled'}

            await interaction.response.edit_message(embed=embed, view=self)
        else:
            error_embed = discord.Embed(
                title="❌ Reset Failed",
                description="Failed to reset your preferences. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.red)
    async def close_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the settings menu."""
        embed = discord.Embed(
            title="✅ Settings Saved",
            description="Your notification preferences have been saved. You can change them anytime with `/notification-settings`.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

async def main():
    """Main function to run the bot."""
    global error_logger

    # Initialize error logger with bot instance
    error_logger = init_error_logger(bot)

    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()

    # Start the bot
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
