#!/bin/bash
cd amsapp
exec gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application