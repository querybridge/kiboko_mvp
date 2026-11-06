"""Phones are routed to the /m/ experience, everything else to desktop, and the
mobile pages act through the desktop endpoints and come back to mobile."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from business_unit.models import BusinessUnit, Company, CompanyMembership, Organization
from strategy.models import Objective, Project

IPHONE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 '
          '(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1')
IPAD = ('Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
ANDROID_PHONE = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
                 '(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36')
ANDROID_TABLET = ('Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
MAC = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 '
       '(KHTML, like Gecko) Version/17.5 Safari/605.1.15')


class MobileBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('exec', 'exec@x.test', 'pw', first_name='Avery', last_name='Exec')
        org = Organization.objects.create(name='o', slug='o', org_admin=self.user, plan_status='active')
        self.co = Company.objects.create(organization=org, name='Co', slug='co')   # seeds 3 objectives
        self.bu = BusinessUnit.objects.create(name='Unit', company=self.co)
        CompanyMembership.objects.create(company=self.co, user=self.user, role='admin')
        self.objective = Objective.objects.filter(company=self.co, aee_alignment='engage_customers').first()
        self.client.force_login(self.user)

    def phone_get(self, url, **kw):
        return self.client.get(url, HTTP_USER_AGENT=IPHONE, **kw)

    def scored_project(self, name='Faster checkout', value=365000, live_in=20):
        p = Project.objects.create(
            name=name, why='As a shopper…', definition_of_done='Live', owner=self.user,
            vertical=self.bu, objective=self.objective, approved=True, value=value,
            target_completion=timezone.localdate() + timedelta(days=live_in))
        Project.objects.filter(pk=p.pk).update(status='Scored', value=value, normalized_score=7.5)
        return Project.objects.get(pk=p.pk)


class RoutingTests(MobileBase):
    def test_phone_goes_to_mobile_equivalent(self):
        for desktop, mobile in [('/app/', '/m/'), ('/app/home/', '/m/start/'), ('/', '/m/start/'),
                                ('/project/executive-approval/', '/m/approve/'),
                                ('/app/score-projects/', '/m/score/'),
                                ('/project/add.html', '/m/add/'),
                                ('/app/analytics/performance-story/', '/m/story/'),
                                ('/project/42/actions/', '/m/projects/42/')]:
            resp = self.phone_get(desktop)
            self.assertEqual((resp.status_code, resp['Location']), (302, mobile), desktop)

    def test_android_phone_routed_tablets_are_not(self):
        self.assertEqual(self.client.get('/app/', HTTP_USER_AGENT=ANDROID_PHONE)['Location'], '/m/')
        for ua in (IPAD, ANDROID_TABLET, MAC):
            self.assertEqual(self.client.get('/app/', HTTP_USER_AGENT=ua).status_code, 200, ua)

    def test_desktop_on_mobile_url_goes_to_desktop(self):
        resp = self.client.get('/m/approve/', HTTP_USER_AGENT=MAC)
        self.assertEqual(resp['Location'], '/project/executive-approval/')

    def test_scope_query_is_kept(self):
        resp = self.phone_get(f'/app/?company={self.co.id}&vertical=all')
        self.assertEqual(resp['Location'], f'/m/?company={self.co.id}&vertical=all')

    def test_desktop_only_pages_stay_on_desktop_for_phones(self):
        resp = self.phone_get('/app/billing/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'kb-mobile-pill')          # the way back to the mobile app

    def test_no_pill_when_signed_out_and_password_reveal_on_phones(self):
        self.client.logout()
        resp = self.client.get('/users/login/', HTTP_USER_AGENT=IPHONE)
        self.assertNotContains(resp, 'class="kb-mobile-pill"')
        self.assertContains(resp, 'kb-pw-toggle')
        self.assertNotContains(self.client.get('/users/login/', HTTP_USER_AGENT=MAC), 'kb-pw-toggle')

    def test_choice_is_remembered(self):
        resp = self.phone_get('/m/?ui=desktop')
        self.assertEqual(resp['Location'], '/app/')
        self.assertEqual(resp.cookies['kb_ui'].value, 'desktop')
        self.assertEqual(self.phone_get('/app/').status_code, 200)       # stays on desktop
        resp = self.phone_get('/app/billing/?ui=mobile')                  # explicit switch back
        self.assertEqual(resp['Location'], '/m/')
        self.assertEqual(self.phone_get('/app/')['Location'], '/m/')

    def test_posts_are_never_redirected(self):
        resp = self.client.post('/app/score-projects/', {'project_id': 0}, HTTP_USER_AGENT=IPHONE)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/app/score-projects/')    # the view's own redirect


class PageTests(MobileBase):
    def test_every_page_renders(self):
        p = self.scored_project()
        for url in ('/m/', '/m/?p=year', '/m/forecast/?p=next_quarter', '/m/approve/', '/m/score/',
                    '/m/projects/', '/m/projects/?f=review', '/m/projects/?f=done',
                    f'/m/projects/{p.id}/', '/m/story/', '/m/add/'):
            resp = self.phone_get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertContains(resp, 'm-tabs')

    def test_start_honors_default_home_page(self):
        from users.models import UserProfile
        prof, _ = UserProfile.objects.get_or_create(user=self.user)
        for lander, page in [('pipeline', '/m/'), ('kanban', '/m/projects/'),
                             ('grow_sales', '/m/story/'), ('storyboard', '/m/story/')]:
            prof.default_lander = lander
            prof.save()
            self.assertEqual(self.phone_get('/m/start/')['Location'], page, lander)

    def test_story_groups_attract_engage_expand(self):
        groups = self.phone_get('/m/story/').context['groups']
        self.assertEqual([g['name'] for g in groups], ['Attract', 'Engage', 'Expand'])
        self.assertEqual([[s['name'] for s in g['subs']] for g in groups],
                         [['Awareness', 'Enlighten'], ['Interest', 'Convince'], ['Inspire', 'Enhance']])
        attract = groups[0]
        self.assertEqual([r['key'] for s in attract['subs'] for r in s['rows']],
                         ['visitors', 'new_visitor_visit', 'returning_visitor_visit', 'visits_per_visitor'])
        self.assertEqual([[r['key'] for r in g['lag'] if r['bold']] for g in groups],
                         [['visits'], ['close_rate'], ['avg_order_value']])

    def test_greenlight_from_mobile_returns_to_mobile(self):
        p = self.scored_project()
        resp = self.phone_get('/m/approve/')
        self.assertContains(resp, p.name)
        self.assertEqual(resp.context['badge_approve'], 1)
        resp = self.client.post(f'/project/{p.id}/approve-on-deck/', {'next': '/m/approve/'},
                                HTTP_USER_AGENT=IPHONE)
        self.assertEqual(resp['Location'], '/m/approve/')
        self.assertEqual(Project.objects.get(pk=p.pk).status, 'On Deck')

    def test_gap_closers_rank_by_value_this_period(self):
        from mobile.views import _forecast
        from app.models import MonthlyGoal
        today = timezone.localdate()
        MonthlyGoal.objects.create(vertical=self.bu, month=today.replace(day=1), budget=1_000_000)
        self.scored_project('Small', value=36_500)
        self.scored_project('Big', value=730_000)
        resp = self.phone_get('/m/forecast/?p=year')
        fc = resp.context['fc']
        self.assertEqual([p.name for p in fc['candidates']], ['Big', 'Small'])
        self.assertFalse(fc['ahead'])
        self.scored_project('After year end', value=900_000, live_in=400)   # adds nothing this year
        fc = self.phone_get('/m/forecast/?p=year').context['fc']
        self.assertNotIn('After year end', [p.name for p in fc['candidates']])

    def test_add_project_lands_on_mobile_project(self):
        resp = self.client.post('/m/add/', {
            'name': 'Guided selling quiz', 'objective': self.objective.id, 'vertical': self.bu.id,
            'owner': self.user.id, 'target_completion': (timezone.localdate() + timedelta(days=45)).isoformat(),
            'why': 'As a shopper, I want help choosing, so that I buy with confidence.',
            'definition_of_done': 'Live for all visitors', 'lever': 'cart_completion',
            'target_from': '0.5000', 'target_to': '0.5500', 's0_annual': '1000000',
            'plausibility_factor': '1.0', 'ramp_days': '30', 'direct_expense': '0', 'expense_type': 'one_time',
        }, HTTP_USER_AGENT=IPHONE)
        p = Project.objects.get(name='Guided selling quiz')
        self.assertEqual(resp['Location'], f'/m/projects/{p.id}/')
        self.assertEqual(p.value, 100000)                      # $1M sales x +10% on the lever

    def test_add_project_shows_errors(self):
        resp = self.client.post('/m/add/', {'name': ''}, HTTP_USER_AGENT=IPHONE)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)

    def test_project_page_is_scoped_to_visible_projects(self):
        other = User.objects.create_user('other', 'o@x.test', 'pw')
        org2 = Organization.objects.create(name='o2', slug='o2', org_admin=other, plan_status='active')
        co2 = Company.objects.create(organization=org2, name='Co2', slug='co2')
        bu2 = BusinessUnit.objects.create(name='U2', company=co2)
        p = Project.objects.create(name='Secret', why='x', owner=other, vertical=bu2)
        self.assertEqual(self.phone_get(f'/m/projects/{p.id}/').status_code, 404)
