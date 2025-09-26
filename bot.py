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
                tasks = list(result)
            elif assignee:
                # List tasks assigned to a user
                result = self.client.tasks.get_tasks_for_user(assignee, workspace=self.workspace_id, opt_fields='name,due_on,assignee.name,completed,notes,projects.name')
                tasks = list(result)
            else:
                # List all tasks in workspace (limited)
                if self.default_project_id:
                    result = self.client.tasks.get_tasks_for_project(self.default_project_id, opt_fields='name,due_on,assignee.name,completed,notes')
                    tasks = list(result)
                else:
                    raise ValueError("No project or assignee specified, and no default project set")

            logger.info(f"Retrieved {len(tasks)} tasks")
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
        # Create category
        category = await guild.create_category("🤖 Botsana")

        # Create channels
        for channel_name, description in AUDIT_CHANNELS.items():
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                topic=description
            )
            self.audit_channels[channel_name] = channel

        return category

    async def register_webhooks(self, base_url: str):
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
            logger.info(f"Registered webhook: {result['gid']}")
        except Exception as e:
            logger.error(f"Failed to register webhook: {e}")

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
    assignee="Assignee email or ID (optional)",
    due_date="Due date in YYYY-MM-DD format (optional)",
    notes="Task notes/description (optional)"
)
async def create_task_command(
    interaction: discord.Interaction,
    name: str,
    project: Optional[str] = None,
    assignee: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Create a new task in Asana."""
    await interaction.response.defer()

    try:
        task = await asana_manager.create_task(
            name=name,
            project_id=project,
            assignee=assignee,
            due_date=due_date,
            notes=notes,
            guild_id=interaction.guild.id
        )

        embed = discord.Embed(
            title="✅ Task Created",
            description=f"**{task['name']}**",
            color=discord.Color.green()
        )

        embed.add_field(name="Task ID", value=task['gid'], inline=True)
        if task.get('due_on'):
            embed.add_field(name="Due Date", value=task['due_on'], inline=True)
        if task.get('assignee'):
            embed.add_field(name="Assignee", value=task['assignee']['name'], inline=True)

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
    task_id="Task ID to update (required)",
    name="New task name (optional)",
    assignee="New assignee email or ID (optional)",
    due_date="New due date in YYYY-MM-DD format (optional)",
    notes="New task notes/description (optional)"
)
async def update_task_command(
    interaction: discord.Interaction,
    task_id: str,
    name: Optional[str] = None,
    assignee: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Update an existing task in Asana."""
    await interaction.response.defer()

    try:
        task = await asana_manager.update_task(
            task_id=task_id,
            name=name,
            assignee=assignee,
            due_date=due_date,
            notes=notes
        )

        embed = discord.Embed(
            title="✅ Task Updated",
            description=f"**{task['name']}**",
            color=discord.Color.blue()
        )

        embed.add_field(name="Task ID", value=task['gid'], inline=True)
        if task.get('due_on'):
            embed.add_field(name="Due Date", value=task['due_on'], inline=True)
        if task.get('assignee'):
            embed.add_field(name="Assignee", value=task['assignee']['name'], inline=True)

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
    task_id="Task ID to complete (required)"
)
async def complete_task_command(
    interaction: discord.Interaction,
    task_id: str
):
    """Mark a task as completed in Asana."""
    await interaction.response.defer()

    try:
        task = await asana_manager.complete_task(task_id)

        embed = discord.Embed(
            title="✅ Task Completed",
            description=f"**{task['name']}** has been marked as completed!",
            color=discord.Color.green()
        )

        embed.add_field(name="Task ID", value=task['gid'], inline=True)

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

        # Show up to the limit
        displayed_tasks = tasks[:limit] if limit else tasks

        for i, task in enumerate(displayed_tasks, 1):
            status = "✅" if task.get('completed') else "⏳"
            assignee = task.get('assignee', {}).get('name', 'Unassigned')
            due_date = task.get('due_on', 'No due date')

            task_info = f"{status} **{task['name']}**\n👤 {assignee} | 📅 {due_date} | ID: `{task['gid']}`"
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
    task_id="Task ID to delete (required)"
)
async def delete_task_command(
    interaction: discord.Interaction,
    task_id: str
):
    """Delete a task from Asana."""
    await interaction.response.defer()

    try:
        # First get the task details for confirmation
        task = await asana_manager.get_task(task_id)

        # Delete the task
        await asana_manager.delete_task(task_id)

        embed = discord.Embed(
            title="🗑️ Task Deleted",
            description=f"**{task['name']}** has been deleted from Asana.",
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

        embed = discord.Embed(
            title=f"📋 {task['name']}",
            color=discord.Color.blue()
        )

        embed.add_field(name="Task ID", value=task['gid'], inline=True)
        embed.add_field(name="Status", value="✅ Completed" if task.get('completed') else "⏳ In Progress", inline=True)

        if task.get('assignee'):
            embed.add_field(name="Assignee", value=task['assignee']['name'], inline=True)

        if task.get('due_on'):
            embed.add_field(name="Due Date", value=task['due_on'], inline=True)

        if task.get('projects'):
            project_names = [p['name'] for p in task['projects']]
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
        # Check if audit system is already set up
        botsana_category = discord.utils.get(interaction.guild.categories, name="🤖 Botsana")
        if botsana_category:
            embed = discord.Embed(
                title="⚠️ Audit System Already Exists",
                description="The Botsana audit system is already set up in this server.",
                color=discord.Color.yellow()
            )
            embed.add_field(
                name="Category",
                value=botsana_category.mention,
                inline=True
            )
            await interaction.followup.send(embed=embed)
            return

        # Create audit channels
        category = await audit_manager.setup_audit_channels(interaction.guild)

        # Register webhooks
        base_url = os.getenv('HEROKU_URL', f"https://{os.getenv('HEROKU_APP_NAME', 'botsana-discord-bot')}.herokuapp.com")
        await audit_manager.register_webhooks(base_url)

        # Start periodic tasks
        scheduler.add_job(audit_manager.check_missed_deadlines, 'cron', hour=9, minute=0)  # Daily at 9 AM
        scheduler.add_job(audit_manager.check_due_soon, 'interval', hours=1)  # Every hour

        if not scheduler.running:
            scheduler.start()

        embed = discord.Embed(
            title="✅ Audit System Setup Complete",
            description="Botsana audit channels have been created and configured!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📁 Category Created",
            value=category.mention,
            inline=True
        )

        embed.add_field(
            name="📺 Channels Created",
            value=str(len(AUDIT_CHANNELS)),
            inline=True
        )

        channels_list = "\n".join([f"• `{name}` - {desc}" for name, desc in AUDIT_CHANNELS.items()])
        embed.add_field(
            name="📋 Available Channels",
            value=channels_list,
            inline=False
        )

        embed.add_field(
            name="🔗 Webhook Status",
            value="✅ Registered for real-time updates",
            inline=True
        )

        embed.set_footer(text="The audit system will now automatically monitor all Asana activity!")

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
