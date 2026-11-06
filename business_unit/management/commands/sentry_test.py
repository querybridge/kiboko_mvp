"""Send a test error to Sentry to confirm alerts arrive: python manage.py sentry_test"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test error to Sentry.'

    def handle(self, *args, **opts):
        import sentry_sdk
        if not sentry_sdk.is_initialized():
            raise CommandError('Sentry is off: add SENTRY_DSN to .env, then Reload.')
        try:
            raise RuntimeError('Kiboko Sentry test error (sent by manage.py sentry_test)')
        except RuntimeError as e:
            event_id = sentry_sdk.capture_exception(e)
        sentry_sdk.flush(timeout=10)
        self.stdout.write(f'Test error sent (event {event_id}). Check Sentry and your email.')
