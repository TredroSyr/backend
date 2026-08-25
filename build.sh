#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Run database migrations
python manage.py migrate --noinput

# Initialize application (seeds common data and other setup tasks)
python manage.py initialize_application

# Collect static files
python manage.py collectstatic --noinput
