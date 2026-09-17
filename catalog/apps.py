from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"

    def ready(self):
        from . import signals  # noqa: F401  (registers Wishlist/Compare merge-on-login receivers)
