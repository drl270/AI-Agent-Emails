#!/bin/bash

CONFIG_FILE=".deploy_config"
if [ -f "$CONFIG_FILE" ]; then
  source "$CONFIG_FILE"
else
  echo "Error: Configuration file $CONFIG_FILE not found."
  echo "Please create $CONFIG_FILE with KEY_PATH, EC2_USER, EC2_HOST, PROJECT_DIR, PORT, and LOG_FILE."
  exit 1
fi

if [ -z "$KEY_PATH" ] || [ -z "$EC2_USER" ] || [ -z "$EC2_HOST" ] || [ -z "$PROJECT_DIR" ] || [ -z "$PORT" ] || [ -z "$LOG_FILE" ]; then
  echo "Error: Missing required configuration variables in $CONFIG_FILE." | tee -a "$LOG_FILE"
  exit 1
fi

if [ ! -f "$KEY_PATH" ]; then
  echo "Error: Key file $KEY_PATH not found." | tee -a "$LOG_FILE"
  exit 1
fi

echo "Starting deployment to $EC2_HOST at $(date)" | tee -a "$LOG_FILE"

ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << EOF

  if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory $PROJECT_DIR does not exist." | tee -a "$LOG_FILE"
    exit 1
  fi
  cd "$PROJECT_DIR" || { echo "Error: Failed to navigate to $PROJECT_DIR" | tee -a "$LOG_FILE"; exit 1; }

  if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found in $PROJECT_DIR" | tee -a "$LOG_FILE"
    exit 1
  fi
  source venv/bin/activate || { echo "Error: Failed to activate virtual environment" | tee -a "$LOG_FILE"; exit 1; }

  if ! pip install -r requirements.txt; then
    echo "Error: Failed to install requirements" | tee -a "$LOG_FILE"
    exit 1
  fi

  pkill -f "uvicorn.*$PORT" || echo "No existing uvicorn process found on port $PORT"

  nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" > app.log 2>&1 &
  if [ \$? -eq 0 ]; then
    echo "Application started successfully on port $PORT" | tee -a "$LOG_FILE"
  else
    echo "Error: Failed to start application" | tee -a "$LOG_FILE"
    exit 1
  fi
EOF

if [ $? -eq 0 ]; then
  echo "Deployment completed successfully at $(date)" | tee -a "$LOG_FILE"
else
  echo "Deployment failed at $(date)" | tee -a "$LOG_FILE"
  exit 1
fi