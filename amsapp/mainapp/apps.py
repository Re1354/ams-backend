from django.apps import AppConfig


class MainappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mainapp'
    
    def ready(self):
        # Import spectacular extensions to register them
        from . import spectacular_extensions
