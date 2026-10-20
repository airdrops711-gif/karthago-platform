from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"

    def ready(self):
        # The lifecycle signals of the store are registered here: they
        # must be connected before the first store is saved.
        from . import signals  # noqa: F401
