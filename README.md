# Botsana - Discord Asana Bot

A Discord bot that integrates with Asana for task management, allowing you to manage your Asana tasks directly from Discord.

## Features

- Create, update, complete, and delete Asana tasks
- List tasks from projects
- Support for slash commands in Discord
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

- `/create-task name:"Task name" due:"2025-12-31" project:"Project ID"` - Create a new task
- `/update-task id:12345 name:"New name" due:"2025-12-31"` - Update an existing task
- `/complete-task id:12345` - Mark a task as completed
- `/list-tasks project:"Project ID"` - List tasks in a project
- `/delete-task id:12345` - Delete a task

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
