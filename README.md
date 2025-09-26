# Botsana - Discord Asana Bot

A Discord bot that integrates with Asana for task management, allowing you to manage your Asana tasks directly from Discord.

## Features

- Create, update, complete, and delete Asana tasks
- List tasks from projects
- Support for slash commands in Discord
- **Comprehensive Audit System** - Real-time monitoring of ALL Asana activity
- **🤖 AI-Powered Natural Language** - Create tasks using conversational language
- **⚙️ Bulk Operations** - Select and operate on multiple tasks at once
- **📋 Task Templates** - Save and reuse common task configurations
- **🔍 Advanced Search** - Filter and save task searches with powerful criteria
- **📊 Project Dashboards** - Visual project status with progress indicators
- **🕐 Time Tracking** - Virtual assistant clock in/out with time proof validation
- **🔔 Smart Notifications** - Personalized due date reminders and assignment alerts
- Secure environment variable handling
- Ready for Heroku deployment

## Prerequisites

- Python 3.8+
- Discord Bot Token from [Discord Developer Portal](https://discord.com/developers/applications)
- Asana Personal Access Token from [Asana Settings](https://app.asana.com/0/my-apps)
- Asana Workspace ID and Project ID (optional)
- **xAI API Key** from [xAI Console](https://console.x.ai/) (for AI-powered natural language processing)

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
     XAI_API_KEY=your_xai_api_key
     ```

4. **Run the bot locally:**
   ```bash
   python bot.py
   ```

## Discord Commands

### Task Management
- `/create-task name:"Task name" assignee:@user due:"2025-12-31"` - Create a new task (auto-assigns to you if no assignee)
- `/update-task task:"Task name or ID" assignee:@user name:"New name"` - Update existing tasks (smart task finding)
- `/complete-task task:"Task name or ID"` - Mark tasks as completed (finds by name or ID)
- `/list-tasks project:"Project ID"` - List tasks in a project
- `/delete-task task:"Task name or ID"` - Delete tasks (finds by name or ID)
- `/view-task task_id` - View task details
- `/status` - Check comprehensive bot health and status
- `/help` - Show all commands

### 🤖 AI-Powered Features
- `@Botsana Create a task to fix the login bug due tomorrow` - Create tasks using natural language in designated chat channel
- `/set-chat-channel #channel` - Designate a channel for AI chat (Admin only)
- `/bulk-select search:"bug" limit:10` - Select multiple tasks for batch operations
- `/notification-settings` - Manage your notification preferences

### 📋 Task Templates
- `/create-template name:"Bug Report" task_name:"🐛 Bug: {description}"` - Create reusable task configurations
- `/list-templates` - Browse available task templates
- `/use-template template:"Bug Report" custom_name:"🐛 Login issue"` - Create tasks from saved templates
- `/delete-template template:"Bug Report"` - Remove templates (Admin only)

### 🔍 Advanced Search
- `/search-tasks query:"bug" assignee:@user status:incomplete due_date:week` - Advanced task search with filters
- `/save-search name:"My Tasks" assignee:@me status:incomplete` - Save search configurations
- `/load-search search:"My Tasks"` - Run previously saved searches
- `/list-searches` - Browse all available saved searches
- `/delete-search search:"My Tasks"` - Delete saved searches

### 📊 Project Dashboards
- `/create-dashboard name:"Sprint" projects:"120123456789,120987654321"` - Create visual project status overviews
- `/view-dashboard dashboard:"Sprint"` - Display project dashboard with metrics
- `/list-dashboards` - Browse all available dashboards
- `/delete-dashboard dashboard:"Sprint"` - Delete project dashboards

### 🕐 Time Tracking
- `/clock-in` - Start tracking work time
- `/clock-out time_proof_link:"https://docs.google.com/..." notes:"Work completed"` - End session with proof
- `/time-status` - Check your current clock in/out status
- `/time-history limit:5` - View recent time entries and history
- `/timeclock-status` - View all currently active sessions (Admin only)

### 🕐 Timeclock Channel (Admin Only)
- `/set-timeclock-channel #timeclock` - Designate channel for time tracking commands
- `/remove-timeclock-channel` - Remove channel restriction (commands work everywhere)

### Audit System Setup
- `/audit-setup` - **ADMIN ONLY** - Set up the Botsana audit category and channels
- `/set-audit-log` - **ADMIN ONLY** - Configure the error logging channel
- `/set-default-project` - **ADMIN ONLY** - Set default project for task creation
- `/view-error-logs` - **ADMIN ONLY** - View recent error logs
- `/test-audit` - **ADMIN ONLY** - Test audit system functionality
- `/repair-audit` - **ADMIN ONLY** - Repair/reset the audit system

### User Management
- `/map-user @user` - **ADMIN ONLY** - Interactive mapping: Select from all Asana workspace users
- `/unmap-user @user` - **ADMIN ONLY** - Remove a Discord user's Asana mapping
- `/list-mappings` - **ADMIN ONLY** - List all Discord-Asana user mappings

## User Mapping System

Botsana includes an intelligent user mapping system that connects Discord users to Asana users, enabling seamless task assignment and collaboration.

### How It Works

1. **Setup**: Administrators use `/map-user @user` to start an interactive mapping process
2. **Selection**: Bot fetches all users from your Asana workspace and presents them in a dropdown menu
3. **Mapping**: Select the correct Asana user from the list - no manual ID entry needed!
4. **Auto-Assignment**: When you create a task without specifying an assignee, it automatically assigns to your Asana account (if mapped)
5. **Mention Assignment**: You can @mention Discord users in task creation to assign tasks directly to their Asana accounts

### Example Usage

**Mapping a user:**
```
/map-user @Lobo
```
Bot shows: "Select Asana User for Lobo" with a dropdown of all Asana workspace users.

**Creating tasks:**
```
/create-task name="Fix the login bug" assignee:@developer
```

This will create a task and assign it to the Asana user mapped to `@developer` in Discord.

If you create a task without specifying an assignee:
```
/create-task name="Review the new feature"
```

It will automatically assign the task to your Asana account (assuming you've been mapped by an admin).

### Interactive Mapping Process

1. Run `/map-user @username`
2. Bot fetches all users from your Asana workspace
3. Select the correct person from the dropdown menu
4. Mapping is created instantly!

**No more manual Asana ID hunting!** 🎉

## Smart Task Operations

Botsana is intelligent about finding and managing tasks across your workspace. You can reference tasks by **name** or **ID** - the bot will figure out what you mean!

### Task Identification
- **By ID**: Use the exact numeric task ID (`/complete-task task:"1211480509573974"`)
- **By Name**: Use partial or full task names (`/complete-task task:"fix login bug"`)
- **Smart Search**: Bot searches your tasks and shows matches if multiple are found
- **Cross-Project**: Finds tasks across all projects you have access to

### Examples

**Complete a task:**
```
/complete-task task:"fix login bug"
/complete-task task:"1211480509573974"
```

**Update a task:**
```
/update-task task:"review code" assignee:@developer due_date:"2025-12-31"
/update-task task:"task name" assignee:@nyte  # Assign to yourself
/update-task task:"1211480509573974" name:"Updated task name"
```

**Delete a task:**
```
/delete-task task:"old task to remove"
/delete-task task:"1211480509573974"
```

### When Multiple Tasks Match

If your search matches multiple tasks, Botsana will show you options:
```
🎯 Multiple Tasks Found
Found 3 tasks matching 'bug'

Option 1: **Fix login bug** (ID: 1211480509573974)
Option 2: **Bug in homepage** (ID: 1211480509573975)
Option 3: **Bug report system** (ID: 1211480509573976)
```

Just use the exact task ID to specify which one you want!

**Never memorize task IDs again!** 🤖✨

## 🤖 AI-Powered Chat Channel

Botsana now understands natural language in designated chat channels! Mention the bot to create tasks using conversational language instead of rigid parameters.

### Setup

An administrator must first designate a channel for AI chat using:

```
/set-chat-channel #your-channel-name
```

Once configured, the bot will respond to @mentions in that channel.

### How It Works

Mention @Botsana in the designated channel and describe your task in natural language. The AI-powered parsing uses **Grok-4-Fast-Reasoning** to intelligently extract:
- Task names and descriptions
- Due dates (tomorrow, next week, specific dates)
- Assignee mentions (@username)
- Project references

**Smart Fallback**: If the xAI API is unavailable, the bot automatically falls back to regex-based parsing to ensure reliability.

### Examples

**Simple task creation:**
```
@Botsana Fix the login bug
```

**With due date:**
```
@Botsana Create a task to review the new feature due tomorrow
```

**With assignee:**
```
@Botsana Schedule a meeting with the team for Friday and assign to @developer
```

**Complex task:**
```
@Botsana I need to update documentation for the API next week with notes about the new endpoints
```

### What It Understands

- **Task Actions**: create, add, schedule, remind, I need to
- **Due Dates**: tomorrow, today, next week, next month, specific dates (MM/DD, YYYY-MM-DD)
- **Time References**: in 3 days, in 2 weeks
- **Assignees**: @username mentions
- **Projects**: "in marketing project", "for project X"

### Smart Confirmation

After parsing your request, Botsana replies with exactly what it understood and provides confirmation buttons. You can review the interpreted details before proceeding with task creation.

### Channel Management

- **Set Channel**: `/set-chat-channel #channel` (Admin only)
- **Remove Channel**: `/remove-chat-channel` (Admin only)
- **Check Status**: `/status` shows if chat channel is configured

The bot only responds to @mentions in the designated channel, keeping regular conversation unaffected.

## 📋 Task Templates

Create reusable task configurations to standardize common workflows and save time.

### Creating Templates

Use `/create-template` to save task configurations for reuse:

```
/create-template name:"Bug Report" task_name:"🐛 Bug: {description}" assignee:@developer due_date_offset:3 notes:"Reported by: {reporter}\nPriority: {priority}\nSteps to reproduce:\n{steps}"
```

**Template Features:**
- **Custom task names** with variables like `{description}`, `{priority}`
- **Default assignees** and projects
- **Automatic due dates** (e.g., 3 days from creation)
- **Template descriptions** and usage notes
- **Usage tracking** and statistics

### Using Templates

Create tasks instantly from templates:

```
/use-template template:"Bug Report" custom_name:"🐛 Login button not working" notes:"User cannot click login after entering credentials"
```

**Override Options:**
- **custom_name**: Override the default task name
- **assignee**: Assign to different user
- **project**: Use different project
- **due_date**: Set specific due date
- **notes**: Add custom notes (appended to template notes)

### Managing Templates

- **`/list-templates`**: Browse all available templates
- **`/use-template`**: Create tasks from templates
- **`/delete-template`** (Admin): Remove templates

### Template Statistics

Templates track usage statistics:
- How many times each template has been used
- Who created each template
- When templates were last used

**Perfect for standardizing:**
- Bug reports
- Feature requests
- Support tickets
- Recurring tasks
- Department workflows

## 🔍 Advanced Search System

Powerful task search capabilities with comprehensive filtering, sorting, and saveable configurations.

### One-Time Advanced Search

Use `/search-tasks` for immediate searches with multiple filter criteria:

```
/search-tasks query:"bug fix" assignee:@developer status:incomplete due_date:week sort_by:created_at limit:15
```

**Available Filters:**
- **query**: Text search in task names and descriptions
- **assignee**: Filter by Discord user (must be mapped to Asana)
- **project**: Filter by Asana project ID
- **status**: `completed` or `incomplete`
- **due_date**: `overdue`, `today`, `tomorrow`, `week`, `month`
- **sort_by**: `created_at`, `modified_at`, `due_on`, `name`
- **sort_order**: `asc` or `desc`
- **limit**: Maximum results (1-25, default 10)

### Saved Searches

Save commonly used search configurations for quick reuse:

**`/save-search`** - Create a reusable search configuration
```
/save-search name:"My Overdue Tasks" description:"Tasks assigned to me that are overdue" assignee:@me status:incomplete due_date:overdue sort_by:due_on sort_order:asc max_results:20
```

**`/load-search`** - Run a previously saved search
```
/load-search search:"My Overdue Tasks"
```

**`/list-searches`** - Browse all available saved searches
```
/list-searches
```

**`/delete-search`** - Remove saved searches (creator or admin only)
```
/delete-search search:"My Overdue Tasks"
```

### Search Results

All search results display:
- **Task Name & ID**: Clickable task identifiers
- **Assignee**: Current task assignee
- **Due Date**: With overdue/today indicators
- **Status**: Completed or incomplete
- **Search Criteria**: Shows what filters were applied

### Advanced Features

- **Smart Date Filtering**: Relative dates (today, week, month) automatically calculated
- **User Mapping**: Discord users automatically resolved to Asana users
- **Usage Tracking**: Saved searches track how often they're used
- **Permission Control**: Users can only delete searches they created (admins can delete any)
- **Result Limiting**: Prevent overwhelming responses with configurable limits

### Use Cases

**For Managers:**
- "All overdue tasks in my department"
- "Tasks assigned to specific team members"
- "High-priority items due this week"

**For Individual Contributors:**
- "My incomplete tasks due today"
- "Tasks I've been assigned this month"
- "Bug reports I've filed"

**For Teams:**
- "All tasks in our current sprint"
- "Support tickets awaiting response"
- "Feature requests from this quarter"

**Saved searches enable:**
- **Quick Access**: One-click access to frequently needed views
- **Consistency**: Standardized search criteria across team members
- **Productivity**: Eliminate repetitive search configuration
- **Monitoring**: Track usage patterns of different search types

## 📊 Project Dashboards

Visual project status monitoring with customizable metrics and real-time progress indicators.

### Creating Dashboards

Set up comprehensive project overviews with multiple metrics:

**`/create-dashboard`** - Build visual project dashboards
```
/create-dashboard name:"Q4 Development Sprint" projects:"120123456789,120987654321" description:"Development team sprint progress" metrics:"task_count,completion_rate,overdue_count,due_soon_count,assignee_breakdown"
```

**Available Metrics:**
- **task_count**: Total number of tasks in each project
- **completion_rate**: Percentage of completed tasks with visual progress bars
- **overdue_count**: Number of tasks past their due date
- **due_soon_count**: Tasks due within the next 7 days
- **assignee_breakdown**: Task distribution across team members

### Viewing Dashboards

Display rich visual project status with real-time data:

**`/view-dashboard`** - Show comprehensive project status
```
/view-dashboard dashboard:"Q4 Development Sprint"
```

**Dashboard Display:**
- **Individual Project Cards**: Each project gets its own visual card
- **Progress Bars**: Visual completion indicators (████████░░)
- **Color-Coded Status**: Different colors for different projects
- **Metric Breakdown**: Detailed statistics for each configured metric
- **Overall Summary**: Cross-project totals and urgent item counts

### Managing Dashboards

**`/list-dashboards`** - Browse all available dashboards
```
/list-dashboards
```

**`/delete-dashboard`** - Remove dashboards (creator or admin only)
```
/delete-dashboard dashboard:"Q4 Development Sprint"
```

### Dashboard Features

**Visual Progress Indicators:**
- Progress bars showing completion percentage
- Color-coded status (green for good, yellow for caution, red for urgent)
- Emoji indicators for quick status assessment

**Comprehensive Metrics:**
- Task counts and completion rates
- Due date analysis (overdue, due soon)
- Workload distribution across team members
- Cross-project summary statistics

**Real-Time Data:**
- Live data from Asana API
- Automatic calculations and aggregations
- Usage tracking for popularity metrics
- Timestamped updates

### Use Cases

**For Project Managers:**
- Monitor multiple projects simultaneously
- Track team productivity across projects
- Identify bottlenecks and overdue work
- Generate visual status reports

**For Team Leads:**
- View sprint progress at a glance
- Monitor task distribution across team members
- Identify projects needing attention
- Share visual status with stakeholders

**For Executives:**
- High-level project portfolio overview
- Quick assessment of project health
- Identify trends across multiple initiatives
- Make data-driven resource decisions

**Dashboard benefits:**
- **Visual Clarity**: Progress bars and color coding for instant understanding
- **Comprehensive View**: Multiple projects in one consolidated view
- **Real-Time Insights**: Live data directly from Asana
- **Customizable Metrics**: Choose exactly what to monitor
- **Team Collaboration**: Shared dashboards for aligned understanding

## 🕐 Time Tracking System

Track work hours with virtual assistants using a dedicated #timeclock channel and automated Asana logging.

### Getting Started

Create a `#timeclock` channel in your Discord server and designate it for time tracking:

**`/set-timeclock-channel #timeclock`** (Admin only)
- Restricts all time tracking commands to the designated channel
- Ensures time tracking happens in an organized location
- Can be changed or removed later with `/remove-timeclock-channel`

Once set, all time tracking commands will only work in the designated channel.

### Clock In/Out Commands

**`/clock-in`** - Start tracking work time
```
/clock-in
```
- Creates a timestamped entry
- Prevents duplicate clock-ins
- Automatically creates Asana task in "TimeClock" project

**`/clock-out`** - End session with time proof
```
/clock-out time_proof_link:"https://docs.google.com/spreadsheets/..." notes:"Completed client work"
```
- Requires valid time proof URL (Google Sheets, Docs, etc.)
- Calculates total session duration
- Updates Asana task with completion details
- Stores notes and proof link

### Monitoring Commands

**`/time-status`** - Check your current status
- Shows if clocked in/out
- Displays current session duration
- Shows today's total time worked

**`/time-history`** - View recent sessions
```
/time-history limit:5
```
- Lists recent time entries
- Shows duration, dates, and proof links
- Provides session summaries and averages

**`/timeclock-status`** - Admin view of all active sessions (Admin only)
- Shows all currently clocked-in users
- Displays session durations
- Helps monitor team activity

### Asana Integration

Automatically creates tasks in a dedicated "TimeClock" project:
- **Clock In**: Creates task when session starts
- **Clock Out**: Updates task with duration and proof
- **Assignment**: Assigns to mapped Asana user if available
- **Details**: Includes timestamps, duration, proof links, and notes

### Time Proof Requirements

Time proof links are required for clocking out and must be:
- Valid URLs (http:// or https://)
- Accessible work documentation
- Examples: Google Sheets, Docs, Drive folders, screenshots, etc.

### Features

- **Duplicate Prevention**: Cannot clock in twice
- **Duration Tracking**: Precise second-by-second timing
- **Proof Validation**: Ensures valid URLs for time proof
- **Daily Totals**: Calculate and display daily work totals
- **Audit Trail**: Complete logging of all time entries
- **Asana Sync**: Automatic task creation and updates

**Perfect for managing:**
- Virtual assistant work sessions
- Freelancer time tracking
- Team productivity monitoring
- Client billing preparation
- Work verification and proof

## ⚙️ Bulk Task Operations

Manage multiple tasks at once with powerful bulk operations.

### Getting Started

Use `/bulk-select` to choose tasks for batch operations:

```
/bulk-select search:"bug" limit:15
```

Or view recent tasks without a search term:
```
/bulk-select limit:10
```

### Available Operations

Once you've selected tasks, choose from:

- **✅ Complete All** - Mark all selected tasks as completed
- **👤 Reassign All** - Assign all tasks to a different user
- **📅 Update Due Dates** - Change due dates for all selected tasks

### Interactive Selection

- Use the dropdown to select multiple tasks (up to 25 at once)
- See task details including assignee and due date
- Clear selection and start over if needed
- Proceed only when you have the right tasks selected

### Bulk Results

After operations complete, Botsana shows detailed results:
- How many tasks were successfully updated
- Which tasks failed (if any) and why
- Confirmation of all changes made

## 🔔 Smart Notification System

Get personalized notifications about task updates delivered directly to your DMs.

### Notification Types

- **📅 Due Date Reminders** - Get notified when tasks are approaching their due dates
- **👥 Assignment Notifications** - Receive alerts when tasks are assigned to you

### Customizable Preferences

Use `/notification-settings` to control when and how you receive notifications:

**Due Date Reminders:**
- 1 day before due date
- 1 hour before due date
- 1 week before due date
- Disabled

**Assignment Notifications:**
- Enabled (default)
- Disabled

### How It Works

1. **Personalized**: Only you receive notifications about your tasks
2. **Respectful**: Honors your preferences - no spam if you disable notifications
3. **Informative**: Includes task details, time remaining, and quick action links
4. **Private**: Sent via DM to keep your inbox clean

### Example Notifications

**Due Date Reminder:**
```
⏰ Task Due Tomorrow
This task is due within the next 24 hours.

📋 Fix Login Bug
📅 Due Date: 2025-01-15
⏰ Time Remaining: 1 day
🔗 View Task: Use /view-task task_id:12345
```

**Assignment Notification:**
```
📋 Task Assigned to You
You have been assigned to: Fix Login Bug

📝 Task: Fix Login Bug
📅 Due Date: 2025-01-15
🔗 View Task: Use /view-task task_id:12345
```

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

### Database Persistence

Botsana uses **PostgreSQL database** for persistent storage that survives Heroku restarts and deployments:

#### Data Storage:
- **Guild configurations** - Audit channels, default projects
- **Error logs** - Complete error history with context
- **System statistics** - Bot usage and performance metrics

#### Database Features:
- **Automatic table creation** on first run
- **Connection pooling** for performance
- **Data integrity** with foreign keys and constraints
- **Migration-safe** schema design

#### Free Tier Limits:
- Heroku Postgres Essential-0: 1GB storage, 20 connections
- Suitable for most Discord bots with moderate usage

**All configuration and logs persist through restarts, deployments, and crashes.**

### Database Management

For security reasons, database operations like resets are **not available as Discord commands**. These operations require direct developer access:

#### Secure Database Operations:
- **Database resets** - Only executable via developer CLI access
- **Schema migrations** - Handled securely outside of Discord
- **Backup operations** - Managed through Heroku Postgres tools

#### Why This Design:
- **Security**: Prevents accidental or malicious data loss via Discord
- **Control**: Critical operations require explicit developer approval
- **Safety**: No risk of users accidentally deleting all bot data

### Status Command Features

The `/status` command provides comprehensive system health information:

#### Status Checks:
- **Bot Status** - Online/responding confirmation
- **Discord Connection** - Gateway latency and connection health
- **Asana API** - Authentication and API connectivity
- **Database** - PostgreSQL connection and health
- **Audit System** - Configuration and channel status
- **Error Statistics** - Recent error counts and trends
- **Bot Statistics** - Server and user counts
- **System Info** - Python version and library versions

#### Use Cases:
- Quick health check after deployments
- Troubleshooting connectivity issues
- Monitoring system performance
- Verifying configuration changes

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
   heroku config:set XAI_API_KEY=your_xai_api_key
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

### Getting Your xAI API Key

1. **Go to [xAI Console](https://console.x.ai/)**
2. **Sign in** with your xAI account
3. **Navigate to API Keys** section
4. **Create a new API key** for your project
5. **Copy the API key** - it will look like: `xai-...`

The bot uses the `grok-4-fast-reasoning` model for advanced natural language processing of task creation requests.

### Updating Environment Variables

If you need to update credentials after deployment:

```bash
heroku config:set ASANA_ACCESS_TOKEN=your_new_token
heroku config:set ASANA_WORKSPACE_ID=your_workspace_id
heroku config:set ASANA_DEFAULT_PROJECT_ID=your_project_id
heroku config:set XAI_API_KEY=your_new_xai_api_key
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
