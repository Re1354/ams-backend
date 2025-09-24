#!/bin/bash
cd amsapp
gunicorn --bind 0.0.0.0:$PORT amsapp.wsgi:application