# Botsana - Discord Asana Bot

A Discord bot that integrates with Asana for task management, allowing you to manage your Asana tasks directly from Discord.

## Features

- Create, update, complete, and delete Asana tasks
- List tasks from projects
- Support for slash commands in Discord
- **Comprehensive Audit System** - Real-time monitoring of ALL Asana activity
- Secure environment variable handling
- Ready for Heroku deployment

## Prerequisites

- Python 3.8+
- Discord Bot Token from [Discord Developer Portal](https://discord.com/developers/applications)
- Asana Personal Access Token from [Asana Settings](https://app.asana.com/0/my-apps)
- Asana Workspace ID and Project ID (optional)

## Setup

1. **Clone or download this repository**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Fill in your credentials:
     ```env
     DISCORD_TOKEN=your_discord_bot_token
     ASANA_ACCESS_TOKEN=your_asana_personal_access_token
     ASANA_WORKSPACE_ID=your_workspace_id
     ASANA_DEFAULT_PROJECT_ID=your_default_project_id
     ```

4. **Run the bot locally:**
   ```bash
   python bot.py
   ```

## Discord Commands

### Task Management
- `/create-task name:"Task name" due:"2025-12-31" project:"Project ID"` - Create a new task
- `/update-task id:12345 name:"New name" due:"2025-12-31"` - Update an existing task
- `/complete-task id:12345` - Mark a task as completed
- `/list-tasks project:"Project ID"` - List tasks in a project
- `/delete-task id:12345` - Delete a task
- `/view-task id:12345` - View task details
- `/help` - Show all commands

### Audit System Setup
- `/audit-setup` - **ADMIN ONLY** - Set up the Botsana audit category and channels
- `/set-audit-log` - **ADMIN ONLY** - Configure the error logging channel
- `/set-default-project` - **ADMIN ONLY** - Set default project for task creation

## Audit System

The Botsana audit system provides **real-time monitoring of ALL Asana activity** through webhooks and automated reporting.

### Audit Channels Created by `/audit-setup`:

- **#taskmaster** 📋 - All task creations and deletions
- **#updates** 🔄 - Task updates, comments, status changes, and assignments
- **#completed** ✅ - Tasks that have been completed
- **#due-soon** ⏰ - Tasks due within 24 hours (checked hourly)
- **#overdue** 🚨 - Currently overdue tasks
- **#missed-deadline** 💀 - Tasks that missed their deadline (reported daily at 9 AM)
- **#new-projects** 📁 - New project creations
- **#attachments** 📎 - Files added to tasks

### How It Works:
1. **Real-time Webhooks**: Asana sends instant notifications for all activity
2. **Automated Reporting**: Scheduled jobs check for due dates and missed deadlines
3. **Rich Embeds**: Each event is formatted as a beautiful Discord embed
4. **Self-Sufficient**: Channels work automatically - no manual intervention needed

### Setup Instructions:
1. Run `/audit-setup` as an Administrator in your server
2. The bot will create the "🤖 Botsana" category and all channels
3. Webhooks are automatically registered with Asana
4. The system begins monitoring immediately

**Note**: The audit system monitors ALL Asana activity in your workspace, not just actions performed through the bot.

### Error Logging System

Botsana includes a comprehensive error logging and reporting system that automatically logs critical errors and system events to a designated Discord channel.

#### Setting Up Error Logging:
1. Create a private `#audit-log` channel in your server
2. Run `/set-audit-log #audit-log` as an Administrator
3. Critical errors will now be automatically logged with detailed information

#### What Gets Logged:
- Command execution errors
- Asana API failures
- Configuration changes
- System events and warnings
- Authentication issues

#### Error Log Format:
Each error includes:
- Error type and message
- User and guild context
- Command that triggered the error
- Timestamp and detailed stack traces
- Severity levels (ERROR, CRITICAL, WARNING)

## Heroku Deployment

1. **Create a Heroku app:**
   ```bash
   heroku create your-app-name
   ```

2. **Set environment variables in Heroku:**
   ```bash
   heroku config:set DISCORD_TOKEN=your_discord_bot_token
   heroku config:set ASANA_ACCESS_TOKEN=your_asana_personal_access_token
   heroku config:set ASANA_WORKSPACE_ID=your_workspace_id
   heroku config:set ASANA_DEFAULT_PROJECT_ID=your_default_project_id
   ```

3. **Deploy to Heroku:**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push heroku main
   ```

## Configuration

### Getting Your Asana Credentials

1. **Asana Personal Access Token:**
   - Go to [Asana Settings → Apps → Personal Access Tokens](https://app.asana.com/0/my-apps)
   - Create a new token with appropriate permissions
   - It will look like: `1/1234567890:abcdef...`

2. **Asana Workspace ID:**
   - Look at the URL when you're in your Asana workspace
   - The ID is the long number in the URL (e.g., `1234567890123456`)

### Updating Environment Variables

If you need to update credentials after deployment:

```bash
heroku config:set ASANA_ACCESS_TOKEN=your_new_token
heroku config:set ASANA_WORKSPACE_ID=your_workspace_id
heroku config:set ASANA_DEFAULT_PROJECT_ID=your_project_id
```

**Bot Commands:**
- `/create-task name:"Task name" project:"Project ID"`
- `/update-task id:12345 name:"New name"`
- `/complete-task id:12345`
- `/list-tasks project:"Project ID"`
- `/delete-task id:12345`
- `/view-task id:12345`
- `/help`

## Security Notes

- Never commit your `.env` file or expose tokens in your code
- Use environment variables for all sensitive data
- Regenerate tokens if they are accidentally exposed
- The bot uses Asana's official Python client for secure API communication

## Development

The bot is built with:
- `discord.py` for Discord integration
- `asana` Python SDK for Asana API
- `python-dotenv` for environment variable management

## License

MIT License - feel free to modify and distribute.
