"""Diagnose the estimator's GA4 baseline fetch for one Business Unit, from the
CLI (no browser). Prints the connection status, the raw GA4 result or the exact
exception, and the derived baselines.

    python manage.py ga4_baseline_check <business_unit_id> --user sherman@querybridge.com

Use this on a machine WITH internet (e.g. localhost) to tell a token/scope error
(invalid_grant / insufficient permissions) apart from a network/allowlist block.
"""
import traceback

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from business_unit.models import BusinessUnit
from project.models import EstimatorSettings
from project.services import impact


class _FakeRequest:
    def __init__(self, user):
        self.user = user
        self.GET = {}
        self.session = {}


class Command(BaseCommand):
    help = 'Diagnose the estimator GA4 baseline fetch for a Business Unit.'

    def add_arguments(self, parser):
        parser.add_argument('business_unit_id', type=int)
        parser.add_argument('--user', required=True, help='email or username to act as')

    def handle(self, *args, **opts):
        from app.integrations import ga4_dashboard, google_oauth

        u = (User.objects.filter(email=opts['user']).first()
             or User.objects.filter(username=opts['user']).first())
        if not u:
            raise CommandError(f'No user matching {opts["user"]!r}')
        bu = BusinessUnit.objects.filter(pk=opts['business_unit_id']).select_related('company').first()
        if not bu:
            raise CommandError(f'No Business Unit id={opts["business_unit_id"]}')

        w = self.stdout.write
        w(f'User          : {u} (id {u.id})')
        w(f'Business Unit : {bu.name} (id {bu.id}), company {bu.company.name}')
        w(f'ga4_property  : {bu.ga4_property_id!r}')
        gi = getattr(u, 'google_identity', None)
        w(f'google identity: {gi and gi.email} · refresh_token={bool(getattr(gi, "refresh_token", ""))}')
        w(f'oauth enabled : {google_oauth.is_enabled()}')

        req = _FakeRequest(u)
        status = ga4_dashboard.baseline_status(req, bu)
        w(f'\nbaseline_status(): {status}')
        if status not in ('premium', 'standard'):
            w(self.style.WARNING('  -> not connectable; nothing to fetch. Fix the above first.'))
            return

        settings = EstimatorSettings.current(bu.company)
        window = (settings.baseline_window_days if settings else 90) or 90
        w(f'baseline window : {window} days (fetching {max(window, 364)} for plausibility)')

        # Call the RAW fetch so any exception surfaces with a full traceback.
        try:
            daily = ga4_dashboard.baseline_daily_for_bu(req, bu, max(window, 364))
        except Exception:
            w(self.style.ERROR('\nRAW fetch raised:'))
            w(traceback.format_exc())
            return

        if not daily:
            w(self.style.ERROR('\nFetch returned no data (see the "estimator baseline: ... unavailable" '
                               'log line above for the underlying exception).'))
            return

        w(self.style.SUCCESS(f'\nFetched {len(daily)} days of GA4 fundamentals.'))
        # Show a sample day and the derived baselines.
        sample = sorted(daily.items())[-1]
        w(f'Latest day {sample[0]}: {sample[1]}')
        b = impact.baselines_from_daily(daily, window)
        if not b:
            w(self.style.ERROR('baselines_from_daily produced nothing.'))
            return
        w(f'\ns0_annual   : ${b["s0_annual"]:,.0f}')
        w(f'window_days : {b["window_days"]}')
        w('per-lever current levels:')
        for k in impact.LEVER_KEYS:
            wk = b['weekly'].get(k, [])
            w(f'  {k:20s} {b["levels"][k]:>14,.4f}   ({len(wk)} weekly points)')
        w(self.style.SUCCESS('\nOK — the estimator would auto-fill these. If the browser still '
                             "doesn't, it's a front-end/session issue, not GA4."))
