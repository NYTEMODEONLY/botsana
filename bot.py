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
                         notes: Optional[str] = None) -> Dict[str, Any]:
        """Create a new task in Asana."""
        try:
            # Use default project if none specified
            if project_id is None:
                project_id = self.default_project_id
                if not project_id:
                    raise ValueError("No project ID specified and no default project set")

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
            notes=notes
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

async def main():
    """Main function to run the bot."""
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
