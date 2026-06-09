#!/bin/bash
cd amsapp
gunicorn --bind 0.0.0.0:${PORT:-8000} amsapp.wsgi:application
