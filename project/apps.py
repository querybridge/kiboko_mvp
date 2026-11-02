from django.apps import AppConfig


class ProjectConfig(AppConfig):
    name = 'project'

    def ready(self):
        import project.notifications  # noqa: F401 — registers project email signals
