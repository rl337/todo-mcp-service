# Slack Integration Setup Guide

This guide explains how to set up Slack integration for the TODO MCP Service to receive task notifications and interact with tasks from Slack.

## Features

- **Task Notifications**: Receive notifications in Slack channels when tasks are created, completed, or blocked
- **Slash Commands**: Use `/todo` commands to list, reserve, and complete tasks
- **Interactive Components**: Click buttons in Slack messages to reserve tasks

## Prerequisites

1. A Slack workspace where you have permission to create apps
2. The TODO MCP Service running and accessible via HTTPS (required for Slack webhooks)
3. Python package `slack-sdk` installed (included in requirements.txt)

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" ? "From scratch"
3. Enter app name: "TODO Service" (or your preferred name)
4. Select your workspace
5. Click "Create App"

## Step 2: Configure Bot Token Scopes

1. In your app settings, go to "OAuth & Permissions" in the sidebar
2. Scroll to "Bot Token Scopes" and add these scopes:
   - `chat:write` - Send messages to channels
   - `commands` - Add slash commands
   - `channels:history` - Read channel messages (optional, for future features)
   - `users:read` - Get user information
3. Scroll up and click "Install to Workspace"
4. Authorize the app and copy the **Bot User OAuth Token** (starts with `xoxb-`)

## Step 3: Configure Signing Secret

1. In your app settings, go to "Basic Information"
2. Under "App Credentials", find "Signing Secret"
3. Click "Show" and copy the **Signing Secret**

## Step 4: Set Up Slash Commands

1. Go to "Slash Commands" in the sidebar
2. Click "Create New Command"
3. Configure:
   - **Command**: `/todo`
   - **Request URL**: `https://your-domain.com/slack/commands`
   - **Short Description**: `Manage TODO tasks`
   - **Usage Hint**: `[list|reserve|complete|help]`
4. Click "Save"

## Step 5: Set Up Event Subscriptions

1. Go to "Event Subscriptions" in the sidebar
2. Enable "Enable Events"
3. Set **Request URL**: `https://your-domain.com/slack/events`
   - Slack will send a verification challenge; the service automatically handles this
4. Under "Subscribe to bot events", add:
   - `message.channels` (optional, for future features)
5. Click "Save Changes"

## Step 6: Enable Interactive Components

1. Go to "Interactivity & Shortcuts" in the sidebar
2. Enable "Interactivity"
3. Set **Request URL**: `https://your-domain.com/slack/interactive`
4. Click "Save Changes"

## Step 7: Configure Environment Variables

Set these environment variables in your TODO MCP Service:

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token-here"
export SLACK_SIGNING_SECRET="your-signing-secret-here"
export SLACK_DEFAULT_CHANNEL="#general"  # Optional: default channel for notifications
export TODO_SERVICE_URL="https://your-domain.com"  # Optional: for task links in messages
```

Or in `docker-compose.yml`:

```yaml
environment:
  - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
  - SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
  - SLACK_DEFAULT_CHANNEL=${SLACK_DEFAULT_CHANNEL:-#general}
  - TODO_SERVICE_URL=${TODO_SERVICE_URL:-https://your-domain.com}
```

## Step 8: Invite Bot to Channels

For the bot to send notifications, invite it to your channels:

1. In Slack, go to the channel where you want notifications
2. Type `/invite @TODO Service` (or your app's display name)
3. The bot will now be able to post messages in that channel

## Usage

### Slash Commands

- `/todo list` - List available tasks (up to 10)
- `/todo reserve <task_id>` - Reserve a task for yourself
- `/todo complete <task_id> [notes]` - Complete a task
- `/todo help` - Show available commands

### Task Notifications

When tasks are created or completed via the API, Slack notifications are automatically sent to the default channel (or configured channel). Notifications include:
- Task title and ID
- Task type and status
- Project information (if applicable)
- Action buttons (for available tasks)

### Interactive Buttons

When viewing task lists or notifications, you can click the "Reserve" button to reserve a task directly from Slack.

## Security

- All Slack requests are verified using HMAC-SHA256 signatures
- Timestamp validation prevents replay attacks (requests older than 5 minutes are rejected)
- Bot tokens and signing secrets should be kept secure (use environment variables, never commit to code)

## Troubleshooting

### Notifications Not Appearing

1. Verify `SLACK_BOT_TOKEN` is set correctly
2. Check that the bot is invited to the target channel
3. Verify `SLACK_DEFAULT_CHANNEL` is set to a valid channel name or ID
4. Check service logs for Slack API errors

### Slash Commands Not Working

1. Verify the Request URL is correct and accessible
2. Check that `SLACK_SIGNING_SECRET` is set correctly
3. Ensure the slash command is installed in your workspace
4. Check service logs for signature verification errors

### Interactive Components Not Responding

1. Verify the Interactive Request URL is set correctly
2. Check that interactivity is enabled in app settings
3. Verify `SLACK_SIGNING_SECRET` is configured
4. Check service logs for errors

## API Endpoints

The Slack integration exposes these endpoints:

- `POST /slack/events` - Event subscription (URL verification and event callbacks)
- `POST /slack/commands` - Slash command handler
- `POST /slack/interactive` - Interactive component handler

All endpoints verify Slack request signatures automatically.

## Testing

Run the test suite to verify Slack integration:

```bash
python3 -m pytest tests/test_slack.py -v
```

## Example Configuration

```bash
# .env file or environment variables
SLACK_BOT_TOKEN=xoxb-<your-actual-slack-bot-token-here>
SLACK_SIGNING_SECRET=<your-slack-signing-secret-here>
SLACK_DEFAULT_CHANNEL=#general
TODO_SERVICE_URL=https://todo.example.com
```

## Next Steps

- Configure Slack notifications for specific projects
- Set up custom notification channels per project
- Add more slash commands (e.g., `/todo create`, `/todo status`)
- Implement task blocking detection and notifications
