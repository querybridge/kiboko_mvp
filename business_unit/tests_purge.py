"""90-day deletion of disabled accounts, and the Google / BigQuery Disconnect buttons."""
import datetime
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from app.models import DailyActual, MonthlyGoal
from business_unit.models import (BigQueryConnection, BusinessUnit, Company, CompanyMembership, Department,
                                  EmailOptOut, GA4DailyRollup, GoogleIdentity, Organization, TrialCode)
from project.models import Action, ActionComment
from strategy.models import Objective, Project, ProjectComment

TODAY = datetime.date.today()


class TwoOrgs(TestCase):
    def setUp(self):
        patcher = mock.patch('business_unit.email.send', return_value=True)
        self.send = patcher.start()
        self.addCleanup(patcher.stop)
        self.dept = Department.objects.create(name='General')

        def org(name, **kw):
            admin = User.objects.create_user(f'{name}_admin', f'admin@{name}.test', 'pw')
            o = Organization.objects.create(name=name, slug=name, org_admin=admin, plan_status='active', **kw)
            co = Company.objects.create(organization=o, name=f'{name} Co', slug=f'{name}-co')
            bu = BusinessUnit.objects.create(name=f'{name} Unit', company=co)
            CompanyMembership.objects.create(company=co, user=admin, role='admin')
            p = Project.objects.create(name=f'{name} project', why='x', owner=admin, vertical=bu, department=self.dept)
            a = Action.objects.create(project=p, owner=admin, name=f'{name} action', business_unit=self.dept, vertical=bu)
            ProjectComment.objects.create(project=p, author=admin, text='note')
            DailyActual.objects.create(date=TODAY, vertical=bu, revenue=1, visits=1, orders=1)
            MonthlyGoal.objects.create(month=TODAY.replace(day=1), vertical=bu, budget=1)
            return SimpleNamespace(org=o, admin=admin, co=co, bu=bu, project=p, action=a)

        self.a = org('alpha')
        self.b = org('beta')
        self.dept.owner = self.a.admin
        self.dept.save()
        BigQueryConnection.objects.create(company=self.a.co, gcp_project='x', service_account_json={'k': 'secret'})
        GA4DailyRollup.objects.create(company=self.a.co, property_id='1', date=TODAY)
        GoogleIdentity.objects.create(user=self.a.admin, google_sub='sub-a', email='admin@alpha.test',
                                      refresh_token='tok')
        TrialCode.objects.create(email='admin@alpha.test', code='ABCD2345', organization=self.a.org,
                                 expires=TODAY + datetime.timedelta(days=7))
        EmailOptOut.objects.create(email='admin@alpha.test', category='project_updates')


class PurgeTests(TwoOrgs):
    def purge(self, org, **kw):
        from business_unit.purge import purge_organization
        return purge_organization(org, **kw)

    def test_deletes_everything_for_the_org_and_nothing_else(self):
        self.purge(self.a.org)
        self.assertFalse(Organization.objects.filter(pk=self.a.org.pk).exists())
        self.assertFalse(Company.objects.filter(pk=self.a.co.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.a.project.pk).exists())
        self.assertFalse(Action.objects.filter(pk=self.a.action.pk).exists())
        self.assertFalse(DailyActual.objects.filter(vertical_id=self.a.bu.pk).exists())
        self.assertFalse(Objective.objects.filter(company_id=self.a.co.pk).exists())
        self.assertFalse(GA4DailyRollup.objects.exists())
        self.assertFalse(BigQueryConnection.objects.exists())
        self.assertFalse(TrialCode.objects.exists())
        self.assertFalse(User.objects.filter(pk=self.a.admin.pk).exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        # Shared and other-org data stay; the department just loses its owner.
        self.dept.refresh_from_db()
        self.assertIsNone(self.dept.owner)
        for obj in (self.b.org, self.b.co, self.b.project, self.b.action, self.b.admin):
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists(), obj)
        self.assertTrue(EmailOptOut.objects.filter(email='admin@alpha.test').exists())

    def test_person_with_records_elsewhere_is_scrubbed_not_deleted(self):
        ActionComment.objects.create(action=self.b.action, author=self.a.admin, text='cross-org note')
        self.purge(self.a.org)
        user = User.objects.get(pk=self.a.admin.pk)
        self.assertEqual((user.email, user.is_active, user.has_usable_password()), ('', False, False))
        self.assertTrue(user.username.startswith('deleted-user-'))
        self.assertTrue(ActionComment.objects.filter(action=self.b.action).exists())

    def test_member_of_another_org_is_kept(self):
        CompanyMembership.objects.create(company=self.b.co, user=self.a.admin, role='member')
        self.purge(self.a.org)
        self.assertEqual(User.objects.get(pk=self.a.admin.pk).email, 'admin@alpha.test')

    def test_dry_run_counts_but_keeps_everything(self):
        counts = self.purge(self.a.org, dry_run=True)
        self.assertGreaterEqual(counts.get('strategy.Project', 0), 1)
        self.assertTrue(Project.objects.filter(pk=self.a.project.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=self.a.org.pk).exists())

    def test_demo_and_comped_orgs_are_refused(self):
        for flag in ('is_platform_demo', 'billing_exempt'):
            setattr(self.a.org, flag, True)
            with self.assertRaises(ValueError):
                self.purge(self.a.org)
            setattr(self.a.org, flag, False)


class DeletionClockTests(TwoOrgs):
    def run_job(self, *args):
        out = StringIO()
        call_command('purge_disabled_accounts', *args, stdout=out)
        return out.getvalue()

    def lock(self, org):
        Organization.objects.filter(pk=org.pk).update(plan_status='past_due')

    def test_disabled_org_gets_a_date_and_an_email(self):
        self.lock(self.a.org)
        self.run_job()
        self.a.org.refresh_from_db()
        self.assertEqual(self.a.org.purge_after, TODAY + datetime.timedelta(days=90))
        self.assertEqual(self.send.call_args.args[2], 'account_disabled')
        self.b.org.refresh_from_db()
        self.assertIsNone(self.b.org.purge_after)

    def test_paying_again_clears_the_date(self):
        Organization.objects.filter(pk=self.a.org.pk).update(purge_after=TODAY + datetime.timedelta(days=50))
        self.run_job()
        self.a.org.refresh_from_db()
        self.assertIsNone(self.a.org.purge_after)

    def test_final_warning_is_sent_once(self):
        self.lock(self.a.org)
        Organization.objects.filter(pk=self.a.org.pk).update(purge_after=TODAY + datetime.timedelta(days=5))
        self.run_job()
        self.run_job()
        warnings = [c for c in self.send.call_args_list if c.args[2] == 'account_purge_warning']
        self.assertEqual(len(warnings), 1)

    def test_past_the_date_is_deleted(self):
        self.lock(self.a.org)
        Organization.objects.filter(pk=self.a.org.pk).update(purge_after=TODAY)
        self.run_job()
        self.assertFalse(Organization.objects.filter(pk=self.a.org.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=self.b.org.pk).exists())

    def test_dry_run_changes_nothing(self):
        self.lock(self.a.org)
        Organization.objects.filter(pk=self.a.org.pk).update(purge_after=TODAY)
        out = self.run_job('--dry-run')
        self.assertIn('would delete', out)
        self.assertTrue(Organization.objects.filter(pk=self.a.org.pk).exists())

    def test_comped_org_is_never_touched(self):
        Organization.objects.filter(pk=self.a.org.pk).update(plan_status='past_due', billing_exempt=True,
                                                             purge_after=TODAY)
        self.run_job()
        self.assertTrue(Organization.objects.filter(pk=self.a.org.pk).exists())


class CancelTests(TwoOrgs):
    def post(self, action):
        self.client.force_login(self.a.admin)
        return self.client.post('/app/billing/', {'action': action})

    def test_cancelled_org_is_locked_once_nothing_is_paid_up(self):
        org = self.a.org
        org.plan_status = 'canceled'
        org.stripe_subscription_id = 'sub_123'
        self.assertFalse(org.is_locked)                 # paid period still running
        org.stripe_subscription_id = ''
        self.assertTrue(org.is_locked)

    @mock.patch('business_unit.billing.set_cancel_at_period_end', return_value=True)
    def test_cancel_without_subscription_starts_the_clock_now(self, stripe):
        self.post('cancel_account')
        self.a.org.refresh_from_db()
        self.assertEqual((self.a.org.plan_status, self.a.org.purge_after),
                         ('canceled', TODAY + datetime.timedelta(days=90)))

    @mock.patch('business_unit.billing.set_cancel_at_period_end', return_value=True)
    def test_cancel_with_subscription_stops_renewal_and_waits(self, stripe):
        Organization.objects.filter(pk=self.a.org.pk).update(stripe_subscription_id='sub_123')
        self.post('cancel_account')
        stripe.assert_called_once()
        self.assertTrue(stripe.call_args.args[1])
        self.a.org.refresh_from_db()
        self.assertEqual((self.a.org.plan_status, self.a.org.purge_after), ('canceled', None))

    @mock.patch('business_unit.billing.set_cancel_at_period_end', return_value=False)
    def test_stripe_failure_leaves_the_account_as_it_was(self, stripe):
        Organization.objects.filter(pk=self.a.org.pk).update(stripe_subscription_id='sub_123')
        self.post('cancel_account')
        self.a.org.refresh_from_db()
        self.assertEqual(self.a.org.plan_status, 'active')

    @mock.patch('business_unit.billing.set_cancel_at_period_end', return_value=True)
    def test_reactivate_resumes_and_clears_the_date(self, stripe):
        Organization.objects.filter(pk=self.a.org.pk).update(
            plan_status='canceled', stripe_subscription_id='sub_123', purge_after=TODAY)
        self.post('reactivate')
        self.assertFalse(stripe.call_args.args[1])
        self.a.org.refresh_from_db()
        self.assertEqual((self.a.org.plan_status, self.a.org.purge_after), ('active', None))


class DisconnectTests(TwoOrgs):
    @mock.patch('requests.post', return_value=SimpleNamespace(status_code=200))
    def test_disconnect_google_revokes_and_deletes_the_token(self, post):
        GoogleIdentity.objects.create(user=self.b.admin, google_sub='sub-b', email='admin@beta.test')
        self.client.force_login(self.a.admin)
        self.client.post('/users/profile/', {'action': 'disconnect_google'})
        self.assertEqual(post.call_args.kwargs['data'], {'token': 'tok'})
        self.assertFalse(GoogleIdentity.objects.filter(user=self.a.admin).exists())
        self.assertTrue(GoogleIdentity.objects.filter(user=self.b.admin).exists())

    def test_disconnect_bigquery_deletes_key_and_summary_table(self):
        self.client.force_login(self.a.admin)
        self.client.post('/app/data-connection/', {'action': 'bigquery_disconnect', 'company': self.a.co.id})
        self.assertFalse(BigQueryConnection.objects.filter(company=self.a.co).exists())
        self.assertFalse(GA4DailyRollup.objects.filter(company=self.a.co).exists())

    def test_cannot_disconnect_another_orgs_bigquery(self):
        self.client.force_login(self.b.admin)
        resp = self.client.post('/app/data-connection/', {'action': 'bigquery_disconnect', 'company': self.a.co.id})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(BigQueryConnection.objects.filter(company=self.a.co).exists())

    def test_plain_member_cannot_disconnect_bigquery(self):
        member = User.objects.create_user('alpha_member', 'member@alpha.test', 'pw')
        CompanyMembership.objects.create(company=self.a.co, user=member, role='member')
        self.client.force_login(member)
        resp = self.client.post('/app/data-connection/', {'action': 'bigquery_disconnect', 'company': self.a.co.id})
        self.assertEqual(resp.status_code, 403)
