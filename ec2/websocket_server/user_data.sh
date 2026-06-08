#!/bin/bash
# EC2 user data script — runs once at first launch as root
# Installs runtime, copies app, sets up systemd service

set -e

# Update system and install dependencies
yum update -y
yum install -y python3 python3-pip git

# Create application directory with correct ownership
mkdir -p /home/ec2-user/app
chown ec2-user:ec2-user /home/ec2-user/app

# Copy application files (in CI/CD this would pull from S3 or git)
# git clone https://github.com/your-org/store-api.git /home/ec2-user/app

# Set up Python virtual environment
cd /home/ec2-user
python3 -m venv venv
chown -R ec2-user:ec2-user venv

# Install application dependencies
/home/ec2-user/venv/bin/pip install flask gunicorn boto3

# Install and enable systemd service
cp /tmp/myapi.service /etc/systemd/system/myapi.service
systemctl daemon-reload
systemctl enable myapi
systemctl start myapi

echo "EC2 setup complete"
