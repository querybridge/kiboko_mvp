"""Billing, trial codes, the billing lock, and project notification emails.
External services are mocked: no SendGrid or Stripe calls leave the test run."""
import datetime
import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from business_unit.models import (BusinessUnit, Company, CompanyMembership, IntegrationSettings,
                                  Organization, Plan, TrialCode)
from strategy.models import Project


def _configure(**kw):
    s = IntegrationSettings.current()
    for k, v in kw.items():
        setattr(s, k, v)
    s.save()


class TrialSignupTests(TestCase):
    """Email first: 1) email -> code sent, 2) code verified, 3) plan + details."""
    def setUp(self):
        self.plan = Plan.objects.create(slug='standard', name='Standard', tier='standard', price=99)

    def _details(self, **kw):
        data = {'action': 'create', 'first_name': 'Ada', 'last_name': 'Lee', 'company': 'Acme',
                'plan': 'standard', 'password': 'longpassword', 'password_confirm': 'longpassword'}
        data.update(kw)
        return data

    def _step(self):
        return self.client.get('/users/get-started/').context['step']

    @mock.patch('business_unit.email.send', return_value=True)
    def _send(self, send, email='ada@acme.co'):
        self.client.post('/users/get-started/', {'action': 'send_code', 'email': email})
        return send

    def test_step_one_emails_a_code_and_moves_to_verify(self):
        send = self._send()
        tc = TrialCode.objects.get(email='ada@acme.co')
        self.assertEqual(send.call_args[0][2], 'trial_code')
        self.assertEqual(send.call_args[0][3]['code'], tc.code)
        self.assertEqual(self._step(), 'verify')
        self.assertFalse(User.objects.filter(email='ada@acme.co').exists())

    def test_existing_account_email_is_refused(self):
        User.objects.create_user('ada', 'ada@acme.co', 'pw')
        self._send()
        self.assertFalse(TrialCode.objects.exists())
        self.assertEqual(self._step(), 'email')

    def test_details_are_refused_until_the_code_is_verified(self):
        self._send()
        self.client.post('/users/get-started/', self._details())
        self.assertFalse(User.objects.filter(email='ada@acme.co').exists())

    def test_wrong_code_then_too_many_tries_restarts(self):
        self._send()
        for _ in range(4):
            self.client.post('/users/get-started/', {'action': 'verify', 'code': 'WRONG123'})
        self.assertEqual(self._step(), 'verify')
        self.client.post('/users/get-started/', {'action': 'verify', 'code': 'WRONG123'})
        self.assertEqual(self._step(), 'email')
        self.assertFalse(TrialCode.objects.filter(email='ada@acme.co', expires__gt=timezone.now()).exists())

    def test_code_for_another_email_does_not_verify(self):
        other = TrialCode.issue('someone@else.co')
        self._send()
        self.client.post('/users/get-started/', {'action': 'verify', 'code': other.code})
        self.assertEqual(self._step(), 'verify')

    def test_full_flow_starts_45_day_trial_once(self):
        self._send()
        tc = TrialCode.objects.get(email='ada@acme.co')
        self.client.post('/users/get-started/', {'action': 'verify', 'code': tc.code.lower()})
        self.assertEqual(self._step(), 'details')
        r = self.client.post('/users/get-started/', self._details())
        self.assertRedirects(r, '/app/getting-started/', fetch_redirect_response=False)
        org = Organization.objects.get(name='Acme')
        self.assertEqual((org.plan_status, org.org_admin.email), ('trial', 'ada@acme.co'))
        self.assertEqual(org.trial_ends, datetime.date.today() + datetime.timedelta(days=45))
        tc.refresh_from_db()
        self.assertIsNotNone(tc.used_at)
        self.assertIsNone(TrialCode.redeemable('ada@acme.co', tc.code))

    def test_detail_errors_keep_fields_and_stay_on_step_three(self):
        self._send()
        tc = TrialCode.objects.get(email='ada@acme.co')
        self.client.post('/users/get-started/', {'action': 'verify', 'code': tc.code})
        self.client.post('/users/get-started/', self._details(password_confirm='different1'))
        r = self.client.get('/users/get-started/')
        self.assertEqual(r.context['step'], 'details')
        self.assertEqual(r.context['form']['company'], 'Acme')

    def test_change_email_goes_back_to_step_one(self):
        self._send()
        self.client.post('/users/get-started/', {'action': 'change_email'})
        self.assertEqual(self._step(), 'email')


class BillingLockTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('boss', 'boss@acme.co', 'pw')
        self.member = User.objects.create_user('pat', 'pat@acme.co', 'pw')
        self.org = Organization.objects.create(name='Acme', slug='acme', org_admin=self.admin,
                                               plan_status='trial', trial_started=datetime.date(2026, 1, 1),
                                               trial_ends=datetime.date.today() - datetime.timedelta(days=1))
        self.company = Company.objects.create(organization=self.org, name='Acme', slug='acme')
        CompanyMembership.objects.create(user=self.member, company=self.company, role='member')

    def test_expired_trial_locks_admin_to_billing(self):
        self.client.force_login(self.admin)
        r = self.client.get('/app/insights/')
        self.assertRedirects(r, '/app/billing/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/app/billing/').status_code, 200)

    def test_expired_trial_shows_member_locked_page(self):
        self.client.force_login(self.member)
        r = self.client.get('/app/insights/')
        self.assertEqual(r.status_code, 402)
        self.assertContains(r, 'organization admin', status_code=402)

    def test_live_trial_payment_and_comped_are_open(self):
        self.org.trial_ends = datetime.date.today() + datetime.timedelta(days=3)
        self.org.save()
        self.assertFalse(self.org.is_locked)
        self.org.trial_ends = datetime.date.today()
        self.org.stripe_subscription_id = 'sub_1'
        self.org.save()
        self.assertFalse(self.org.is_locked)
        self.org.stripe_subscription_id = ''
        self.org.billing_exempt = True
        self.org.save()
        self.assertFalse(self.org.is_locked)

    def test_superuser_never_locked(self):
        su = User.objects.create_superuser('method', 'm@kiboko.co', 'pw')
        self.org.org_admin = su
        self.org.save()
        self.client.force_login(su)
        self.assertNotEqual(self.client.get('/app/help/').status_code, 402)
        self.assertNotEqual(self.client.get('/app/help/').get('Location'), '/app/billing/')


class StripeTests(TestCase):
    def setUp(self):
        _configure(stripe_secret_key='sk_test_x', stripe_webhook_secret='whsec_x')
        self.admin = User.objects.create_user('boss', 'boss@acme.co', 'pw')
        plan = Plan.objects.create(slug='premium', name='Premium', tier='premium', price=299,
                                   stripe_price_id='price_123')
        self.org = Organization.objects.create(name='Acme', slug='acme', org_admin=self.admin, plan=plan,
                                               plan_status='trial', trial_started=datetime.date.today(),
                                               trial_ends=datetime.date.today() + datetime.timedelta(days=45))
        self.client.force_login(self.admin)

    @mock.patch('stripe.StripeClient')
    def test_checkout_carries_trial_and_redirects(self, SC):
        sc = SC.return_value
        sc.v1.customers.create.return_value = SimpleNamespace(id='cus_1')
        sc.v1.checkout.sessions.create.return_value = SimpleNamespace(url='https://checkout.stripe.test/s')
        r = self.client.post('/billing/checkout/')
        self.assertEqual(r['Location'], 'https://checkout.stripe.test/s')
        params = sc.v1.checkout.sessions.create.call_args.kwargs['params']
        self.assertEqual(params['mode'], 'subscription')
        self.assertEqual(params['line_items'], [{'price': 'price_123', 'quantity': 1}])
        self.assertIn('trial_end', params['subscription_data'])
        self.assertNotIn('payment_method_types', params)
        self.org.refresh_from_db()
        self.assertEqual(self.org.stripe_customer_id, 'cus_1')

    @mock.patch('stripe.StripeClient')
    def test_webhook_activates_then_past_due(self, SC):
        self.org.stripe_customer_id = 'cus_1'
        self.org.save()
        sc = SC.return_value

        def event(kind, **obj):
            return SimpleNamespace(type=kind, data=SimpleNamespace(object=SimpleNamespace(customer='cus_1', **obj)))

        sc.construct_event.return_value = event('checkout.session.completed', mode='subscription',
                                                status='complete', subscription='sub_9')
        r = self.client.post('/billing/stripe/webhook/', data=b'{}', content_type='application/json',
                             HTTP_STRIPE_SIGNATURE='t=1,v1=x')
        self.assertEqual(r.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual((self.org.plan_status, self.org.stripe_subscription_id), ('active', 'sub_9'))

        sc.construct_event.return_value = event('invoice.payment_failed')
        self.client.post('/billing/stripe/webhook/', data=b'{}', content_type='application/json',
                         HTTP_STRIPE_SIGNATURE='t=1,v1=x')
        self.org.refresh_from_db()
        self.assertEqual(self.org.plan_status, 'past_due')
        self.assertTrue(self.org.is_locked)

    @mock.patch('stripe.StripeClient')
    def test_webhook_rejects_bad_signature(self, SC):
        SC.return_value.construct_event.side_effect = ValueError('bad sig')
        r = self.client.post('/billing/stripe/webhook/', data=b'{}', content_type='application/json',
                             HTTP_STRIPE_SIGNATURE='nope')
        self.assertEqual(r.status_code, 400)


class ProjectEmailTests(TestCase):
    def setUp(self):
        _configure(sendgrid_api_key='SG.x', email_from_address='hello@kiboko.co')
        self.gm = User.objects.create_user('gm', 'gm@acme.co', 'pw')
        self.owner = User.objects.create_user('own', 'own@acme.co', 'pw')
        org = Organization.objects.create(name='Acme', slug='acme', plan_status='active')
        self.company = Company.objects.create(organization=org, name='Acme', slug='acme')
        self.bu = BusinessUnit.objects.create(name='Lighting', company=self.company, general_manager=self.gm)
        CompanyMembership.objects.create(user=self.owner, company=self.company, role='member')

    def _templates(self, send):
        return [(c.args[0], c.args[2]) for c in send.call_args_list]

    @mock.patch('business_unit.email.send', return_value=True)
    def test_new_project_emails_bu_owner(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            Project.objects.create(name='Nav redesign', why='x', owner=self.owner, vertical=self.bu)
        self.assertIn(('gm@acme.co', 'project_added'), self._templates(send))

    @mock.patch('business_unit.email.send', return_value=True)
    def test_phase_move_emails_owner_and_scorers(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            p = Project.objects.create(name='Nav redesign', why='x', owner=self.owner, vertical=self.bu,
                                       status='In Intake')
        send.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            p.status = 'Ready to Score'
            p.save()
        sent = self._templates(send)
        self.assertIn(('own@acme.co', 'project_phase'), sent)
        self.assertIn(('own@acme.co', 'project_needs_scoring'), sent)   # BU member
        self.assertIn(('gm@acme.co', 'project_needs_scoring'), sent)    # BU lead
        self.assertNotIn('project_added', [t for _, t in sent])

    @mock.patch('business_unit.email.send', return_value=True)
    def test_unchanged_save_sends_nothing(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            p = Project.objects.create(name='Nav', why='x', owner=self.owner, vertical=self.bu, status='Scored')
        send.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            p.name = 'Nav 2'
            p.save()
        send.assert_not_called()

    @mock.patch('business_unit.email.send', return_value=True)
    def test_suppressed_and_disabled_send_nothing(self, send):
        from business_unit import email as mail
        with mail.suppressed(), self.captureOnCommitCallbacks(execute=True):
            Project.objects.create(name='Seeded', why='x', owner=self.owner, vertical=self.bu)
        _configure(notifications_enabled=False)
        with self.captureOnCommitCallbacks(execute=True):
            Project.objects.create(name='Quiet', why='x', owner=self.owner, vertical=self.bu)
        send.assert_not_called()


class EmailSendTests(TestCase):
    def test_unconfigured_send_is_a_quiet_no_op(self):
        from business_unit import email as mail
        self.assertFalse(mail.send('a@acme.co', 'Hi', 'trial_code', {'code': 'X', 'days': 45, 'valid_days': 7}))

    @mock.patch('sendgrid.SendGridAPIClient')
    def test_sends_one_message_per_recipient_and_skips_placeholders(self, SG):
        from business_unit import email as mail
        _configure(sendgrid_api_key='SG.x', email_from_address='hello@kiboko.co')
        SG.return_value.send.return_value = SimpleNamespace(status_code=202)
        ok = mail.send(['a@acme.co', 'b@acme.co', 'demo@example.com'], 'Hi', 'trial_code',
                       {'code': 'ABCD', 'days': 45, 'valid_days': 7})
        self.assertTrue(ok)
        self.assertEqual(SG.return_value.send.call_count, 2)


class FeedbackTests(TestCase):
    @mock.patch('business_unit.email.send', return_value=True)
    def test_feedback_goes_to_info_with_reply_to(self, send):
        u = User.objects.create_user('pat', 'pat@acme.co', 'pw', first_name='Pat')
        self.client.force_login(u)
        self.client.post('/app/feedback/', {'message': 'Love the Backlog', 'next': '/app/help/'})
        args, kwargs = send.call_args
        self.assertEqual(args[0], 'info@kibokomethod.com')
        self.assertEqual(args[2], 'feedback')
        self.assertEqual(args[3]['message'], 'Love the Backlog')
        self.assertEqual(kwargs['reply_to'], 'pat@acme.co')

    def test_feedback_template_renders(self):
        from django.template.loader import render_to_string
        ctx = {'who': 'Pat', 'email': 'pat@acme.co', 'username': 'pat', 'user_id': 1, 'org': 'Acme',
               'page': '/app/help/', 'message': 'Line one\nLine <two>'}
        self.assertIn('Line <two>', render_to_string('emails/feedback.txt', ctx))
        self.assertIn('Line &lt;two&gt;', render_to_string('emails/feedback.html', ctx))
