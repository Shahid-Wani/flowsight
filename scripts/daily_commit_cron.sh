#!/bin/bash
# Daily commit cron job for FlowSight
# Add to crontab: 0 2 * * * /path/to/flowsight/scripts/daily_commit_cron.sh

set -e

REPO_DIR="/home/shahi/flowsight"
LOG_FILE="/home/shahi/flowsight/logs/daily_commit.log"

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Log start
echo "[$(date)] Starting daily commit" >> "$LOG_FILE"

# Change to repo directory
cd "$REPO_DIR"

# Run the daily commit script
python3 scripts/daily_commit.py >> "$LOG_FILE" 2>&1

# Log completion
echo "[$(date)] Daily commit completed" >> "$LOG_FILE"