#!/bin/bash
exec gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application
