from django.apps import AppConfig


class ArcaniawikiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arcaniawiki'

    def ready(self):
        from . import security  # noqa: F401  (connects the admin login signals)
