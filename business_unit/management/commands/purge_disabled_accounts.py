"""Daily: keep each organization's 90-day deletion clock in step, warn its owner,
and permanently delete what is past due. Schedule it once a day on the server:

    python manage.py purge_disabled_accounts

  - A disabled org (cancelled, or locked for non-payment; Organization.is_locked)
    without a date gets purge_after = today + 90 and the owner is emailed.
  - An org that is no longer disabled (paid, reactivated, comped) has its date cleared.
  - Seven days out, the owner gets one final warning.
  - On or after purge_after, everything is deleted (business_unit.purge).

--dry-run reports what would happen and changes nothing.
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from business_unit import email as mail
from business_unit.models import Organization
from business_unit.purge import purge_organization

WARN_DAYS = 7


def _recipients(org):
    return [a for a in {getattr(org.org_admin, 'email', ''), org.billing_email} if a]


class Command(BaseCommand):
    help = 'Start, clear and enforce the 90-day deletion clock for disabled accounts.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report only; change and delete nothing.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        today = datetime.date.today()
        checked, acted = 0, []

        def say(line):
            acted.append(line)
            self.stdout.write(line)

        for org in Organization.objects.filter(is_platform_demo=False, billing_exempt=False).select_related('org_admin'):
            checked += 1
            disabled = org.is_locked
            if not disabled:
                if org.purge_after:
                    say(f'{org.name}: active again, deletion date cleared')
                    if not dry:
                        org.purge_after = None
                        org.purge_warned_at = None
                        org.save(update_fields=['purge_after', 'purge_warned_at'])
                continue

            if org.purge_after is None:
                purge_on = today + datetime.timedelta(days=org.PURGE_DAYS)
                say(f'{org.name}: disabled, data will be deleted on {purge_on}')
                if not dry:
                    org.purge_after = purge_on
                    org.save(update_fields=['purge_after'])
                    mail.send(_recipients(org), 'Your Kiboko account is disabled', 'account_disabled',
                              {'org': org, 'purge_on': purge_on, 'days': org.PURGE_DAYS})
                continue

            if org.purge_after <= today:
                counts = purge_organization(org, dry_run=dry)
                summary = ', '.join(f'{k} {v}' for k, v in sorted(counts.items()) if v)
                say(f'{org.name}: {"would delete" if dry else "deleted"} ({summary})')
                continue

            if (org.purge_after - today).days <= WARN_DAYS and org.purge_warned_at is None:
                say(f'{org.name}: final warning, deletion on {org.purge_after}')
                if not dry:
                    mail.send(_recipients(org), 'Your Kiboko data will be deleted in 7 days', 'account_purge_warning',
                              {'org': org, 'purge_on': org.purge_after})
                    org.purge_warned_at = timezone.now()
                    org.save(update_fields=['purge_warned_at'])

        outcome = f'{len(acted)} action(s)' if acted else 'nothing to do'
        self.stdout.write(f'{"Dry run: " if dry else ""}{checked} organization(s) checked, {outcome}.')
