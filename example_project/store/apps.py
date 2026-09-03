from django.apps import AppConfig


class StoreConfig(AppConfig):
    name = "example_project.store"
    label = "store"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Importing the module runs its @register_tool decorators, which is what
        # puts the custom tool names in the registry — and therefore in the
        # AgentConfig admin's "extra tools" list. Without this the tools exist
        # but nothing has ever imported them.
        from . import tools  # noqa: F401
