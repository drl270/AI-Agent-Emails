#!/bin/bash
cd /home/ec2-user/AI-Agent-Emails
source venv/bin/activate
pip install -r requirements.txt
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &