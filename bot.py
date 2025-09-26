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
from datetime import datetime, timedelta
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
        """Check for tasks due within 24 hours."""
        try:
            tasks = await asana_manager.list_tasks()
            tomorrow = datetime.now() + timedelta(days=1)
            due_soon_tasks = []

            for task in tasks:
                if task.get('due_on') and not task.get('completed'):
                    due_date = datetime.fromisoformat(task['due_on'])
                    if due_date <= tomorrow and due_date > datetime.now():
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
