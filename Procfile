web: cd amsapp && gunicorn --bind 0.0.0.0:${PORT:-8000} amsapp.wsgi:application
release: cd amsapp && python manage.py migrate
