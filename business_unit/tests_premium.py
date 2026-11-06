"""Self-serve Premium Connection: the owner adds it in Billing, then the org's
own companies can be connected to BigQuery without Kiboko's help."""
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from business_unit.models import BigQueryConnection, Company, CompanyMembership, Organization, Plan


class PremiumBase(TestCase):
    def setUp(self):
        self.standard = Plan.objects.create(slug='std', name='Standard', tier='standard', price=299,
                                            stripe_price_id='price_std')
        self.addon = Plan.objects.create(slug='pc', name='Premium Connection', tier='addon', is_addon=True,
                                         price=150, stripe_price_id='price_addon')
        self.owner = User.objects.create_user('owner', 'owner@a.test', 'pw')
        self.org = Organization.objects.create(name='A', slug='a', org_admin=self.owner, plan=self.standard,
                                               plan_status='trial')
        self.co = Company.objects.create(organization=self.org, name='A Co', slug='a-co')
        CompanyMembership.objects.create(company=self.co, user=self.owner, role='admin')
        other_admin = User.objects.create_user('other', 'o@b.test', 'pw')
        other_org = Organization.objects.create(name='B', slug='b', org_admin=other_admin, premium_connection=True)
        self.other_co = Company.objects.create(organization=other_org, name='B Co', slug='b-co')
        self.client.force_login(self.owner)

    def add_premium(self, **extra):
        return self.client.post('/app/billing/', {'action': 'add_premium', **extra})


class PremiumTests(PremiumBase):
    def test_trial_org_turns_premium_on_without_payment(self):
        resp = self.add_premium(next='data_connection')
        self.assertRedirects(resp, '/app/data-connection/', fetch_redirect_response=False)
        self.org.refresh_from_db()
        self.assertTrue(self.org.premium_connection)

    def test_paying_org_gets_the_addon_on_its_subscription(self):
        Organization.objects.filter(pk=self.org.pk).update(stripe_subscription_id='sub_1', plan_status='active')
        create = mock.Mock()
        sc = SimpleNamespace(v1=SimpleNamespace(subscription_items=SimpleNamespace(create=create)))
        with mock.patch('business_unit.billing.client', return_value=sc):
            self.add_premium()
        params = create.call_args.kwargs['params']
        self.assertEqual((params['subscription'], params['price']), ('sub_1', 'price_addon'))
        self.org.refresh_from_db()
        self.assertTrue(self.org.premium_connection)

    def test_stripe_refusal_leaves_premium_off(self):
        Organization.objects.filter(pk=self.org.pk).update(stripe_subscription_id='sub_1', plan_status='active')
        sc = SimpleNamespace(v1=SimpleNamespace(subscription_items=SimpleNamespace(
            create=mock.Mock(side_effect=RuntimeError('declined')))))
        with mock.patch('business_unit.billing.client', return_value=sc):
            self.add_premium()
        self.org.refresh_from_db()
        self.assertFalse(self.org.premium_connection)

    def test_premium_plan_includes_it(self):
        self.org.plan = Plan.objects.create(slug='prem', name='Premium', tier='premium', price=599)
        self.assertTrue(self.org.has_premium)

    def test_data_connection_offers_the_upgrade_until_premium_is_on(self):
        page = self.client.get('/app/data-connection/').content.decode()
        self.assertIn('?from=data_connection#premium', page)
        self.assertNotIn('name="service_account_json"', page)
        self.add_premium()
        page = self.client.get('/app/data-connection/').content.decode()
        self.assertIn('name="service_account_json"', page)
        self.assertIn(f'<option value="{self.co.id}">A Co</option>', page)
        self.assertNotIn('B Co', page)

    @mock.patch('app.integrations.bigquery.test_connection', return_value=(True, 'ok', None))
    def test_connect_requires_premium_and_an_own_company(self, _test):
        post = {'action': 'bigquery_connect', 'property_id': '123', 'service_account_json': '{"project_id": "p"}'}
        self.assertEqual(self.client.post('/app/data-connection/', {**post, 'company': self.co.id}).status_code, 403)
        self.add_premium()
        self.assertEqual(self.client.post('/app/data-connection/', {**post, 'company': self.other_co.id}).status_code, 403)
        self.client.post('/app/data-connection/', {**post, 'company': self.co.id})
        self.assertTrue(BigQueryConnection.objects.filter(company=self.co).exists())
        self.assertFalse(BigQueryConnection.objects.filter(company=self.other_co).exists())


class RemovePremiumTests(PremiumBase):
    def setUp(self):
        super().setUp()
        from business_unit.models import GA4DailyRollup
        import datetime
        self.org.premium_connection = True
        self.org.save()
        BigQueryConnection.objects.create(company=self.co, gcp_project='p', service_account_json={'k': 'v'})
        GA4DailyRollup.objects.create(company=self.co, property_id='1', date=datetime.date(2026, 1, 1))

    def remove(self, **extra):
        return self.client.post('/app/billing/', {'action': 'remove_premium', 'understood': '1', **extra})

    def test_remove_turns_premium_off_and_deletes_the_connection(self):
        from business_unit.models import GA4DailyRollup
        self.remove()
        self.org.refresh_from_db()
        self.assertFalse(self.org.premium_connection)
        self.assertFalse(BigQueryConnection.objects.filter(company=self.co).exists())
        self.assertFalse(GA4DailyRollup.objects.filter(company=self.co).exists())

    def test_remove_needs_the_acknowledgement(self):
        self.client.post('/app/billing/', {'action': 'remove_premium'})
        self.org.refresh_from_db()
        self.assertTrue(self.org.premium_connection)

    def test_paying_org_has_the_addon_taken_off_its_subscription(self):
        Organization.objects.filter(pk=self.org.pk).update(stripe_subscription_id='sub_1', plan_status='active')
        items = SimpleNamespace(data=[SimpleNamespace(id='si_plan', price=SimpleNamespace(id='price_std')),
                                      SimpleNamespace(id='si_addon', price=SimpleNamespace(id='price_addon'))])
        delete = mock.Mock()
        sc = SimpleNamespace(v1=SimpleNamespace(subscription_items=SimpleNamespace(
            list=mock.Mock(return_value=items), delete=delete)))
        with mock.patch('business_unit.billing.client', return_value=sc):
            self.remove()
        self.assertEqual([c.args[0] for c in delete.call_args_list], ['si_addon'])
        self.org.refresh_from_db()
        self.assertFalse(self.org.premium_connection)

    def test_premium_plan_has_nothing_to_remove(self):
        Organization.objects.filter(pk=self.org.pk).update(
            plan=Plan.objects.create(slug='prem', name='Premium', tier='premium', price=599))
        self.remove()
        self.assertTrue(BigQueryConnection.objects.filter(company=self.co).exists())


class TimeZoneTests(PremiumBase):
    def set_zone(self, company, zone):
        return self.client.post('/app/data-connection/', {'action': 'set_time_zone', 'company': company.id,
                                                           'time_zone': zone})

    def test_owner_sets_a_zone_and_requests_use_it(self):
        import datetime
        from unittest import mock as _m
        from django.utils import timezone
        self.set_zone(self.co, 'America/Los_Angeles')
        self.co.refresh_from_db()
        self.assertEqual(self.co.time_zone, 'America/Los_Angeles')
        # 2026-11-06 03:00 UTC is still Nov 5 in Los Angeles.
        seen = {}
        real = timezone.localdate
        def spy(*a, **kw):
            seen['date'] = real(*a, **kw)
            return seen['date']
        fixed = datetime.datetime(2026, 11, 6, 3, 0, tzinfo=datetime.timezone.utc)
        with _m.patch('django.utils.timezone.now', return_value=fixed), \
             _m.patch('app.views.timezone.localdate', side_effect=spy):
            self.client.get(f'/app/?company={self.co.id}&vertical=all')
        self.assertEqual(seen['date'], datetime.date(2026, 11, 5))

    def test_blank_falls_back_to_the_ga4_property(self):
        from business_unit.models import BusinessUnit
        BusinessUnit.objects.create(name='U', company=self.co, timezone='America/Denver')
        self.set_zone(self.co, '')
        self.assertEqual(Company.objects.get(pk=self.co.pk).effective_time_zone, 'America/Denver')

    def test_bad_zone_and_other_orgs_company_are_refused(self):
        self.set_zone(self.co, 'Mars/Olympus')
        self.assertEqual(Company.objects.get(pk=self.co.pk).time_zone, '')
        self.assertEqual(self.set_zone(self.other_co, 'UTC').status_code, 403)
