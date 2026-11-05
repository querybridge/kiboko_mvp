"""Re-save every stored secret with the current first KIBOKO_ENCRYPTION_KEY.
Run after rotating the key (KIBOKO_ENCRYPTION_KEY=new,old), then drop the old key."""
from django.core.management.base import BaseCommand

from business_unit.models import BigQueryConnection, GoogleIdentity, IntegrationSettings

SECRETS = ((GoogleIdentity, ['refresh_token']),
           (BigQueryConnection, ['service_account_json']),
           (IntegrationSettings, ['sendgrid_api_key', 'stripe_secret_key', 'stripe_webhook_secret']))


class Command(BaseCommand):
    help = 'Re-encrypt stored secrets with the current encryption key (after a key rotation).'

    def handle(self, *args, **opts):
        for model, fields in SECRETS:
            n = 0
            for obj in model.objects.all():
                obj.save(update_fields=fields)
                n += 1
            self.stdout.write(f'{model.__name__}: {n} re-encrypted')
