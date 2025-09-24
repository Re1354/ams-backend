#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Change to the Django project directory
cd amsapp

# Collect static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate