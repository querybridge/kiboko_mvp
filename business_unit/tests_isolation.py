"""Cross-tenant isolation: a user in organization A must never see or change
organization B's data.

Tests marked @unittest.expectedFailure document a known leak (see the # LEAK
comment above each). They pass as "expected failures" until the leak is fixed;
once fixed, the run reports an "unexpected success" -- remove the decorator then.
Email is mocked; no message leaves the test run.
"""
import datetime
import io
import json
import unittest
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from app.models import DailyActual, MonthlyGoal
from business_unit.models import (BusinessUnit, Company, CompanyMembership, Department,
                                  Organization)
from project.models import Action
from strategy.models import Project, ProjectComment

B_PROJECT = 'Beta confidential roadmap'
B_DONE = 'Beta finished launch'
B_SHELVED = 'Beta shelved idea'
B_INTAKE = 'Beta intake proposal'
B_ACTION = 'Beta execution task'
B_EMAIL = 'owner@beta-co.test'
B_BUDGET = Decimal('987654')


class IsolationBase(TestCase):
    """Two separate customers. A's org admin is the strongest legitimate role
    short of platform superuser, so anything they reach in B is a real leak."""

    def setUp(self):
        patcher = mock.patch('business_unit.email.send', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.a_admin = User.objects.create_user('alpha_admin', 'admin@alpha-co.test', 'pw')
        self.a_member = User.objects.create_user('alpha_member', 'member@alpha-co.test', 'pw')
        self.b_admin = User.objects.create_user('beta_admin', B_EMAIL, 'pw')

        self.org_a = Organization.objects.create(name='Alpha Org', slug='alpha-org', org_admin=self.a_admin,
                                                 billing_exempt=True, plan_status='active')
        self.org_b = Organization.objects.create(name='Beta Org', slug='beta-org', org_admin=self.b_admin,
                                                 billing_exempt=True, plan_status='active')
        self.co_a = Company.objects.create(organization=self.org_a, name='Alpha Co', slug='alpha-co')
        self.co_b = Company.objects.create(organization=self.org_b, name='Beta Co', slug='beta-co')
        self.bu_a = BusinessUnit.objects.create(name='Alpha Unit', company=self.co_a)
        self.bu_b = BusinessUnit.objects.create(name='Beta Unit', company=self.co_b, general_manager=self.b_admin)
        CompanyMembership.objects.create(company=self.co_a, user=self.a_admin, role='admin')
        CompanyMembership.objects.create(company=self.co_a, user=self.a_member, role='member')
        CompanyMembership.objects.create(company=self.co_b, user=self.b_admin, role='admin')

        self.dept = Department.objects.create(name='General')
        today = datetime.date.today()

        def project(name, bu, owner, **status):
            p = Project.objects.create(name=name, why='x', owner=owner, vertical=bu, department=self.dept,
                                       value=777777, target_completion=today)
            if status:
                Project.objects.filter(pk=p.pk).update(**status)
                p.refresh_from_db()
            return p

        self.p_a = project('Alpha roadmap', self.bu_a, self.a_admin, status='WIP', approved=True)
        self.p_b = project(B_PROJECT, self.bu_b, self.b_admin, status='WIP', approved=True)
        self.p_b_done = project(B_DONE, self.bu_b, self.b_admin, status='Complete', approved=True)
        self.p_b_shelved = project(B_SHELVED, self.bu_b, self.b_admin, archived=True)
        self.p_b_intake = project(B_INTAKE, self.bu_b, self.b_admin, status='In Intake', approved=True)
        self.a_b = Action.objects.create(project=self.p_b, owner=self.b_admin, name=B_ACTION, status='WIP',
                                         business_unit=self.dept, vertical=self.bu_b, launch=today)
        MonthlyGoal.objects.create(month=today.replace(day=1), vertical=self.bu_b, budget=B_BUDGET)

    def login_a(self, user=None):
        self.client.force_login(user or self.a_admin)

    def assertBlocked(self, resp):
        """Denied: 403/404, or bounced away (not rendering B's object)."""
        self.assertIn(resp.status_code, (302, 403, 404), f'got {resp.status_code}')

    def assertNoB(self, resp, *names):
        body = resp.content.decode('utf-8', 'replace')
        for n in names or (B_PROJECT,):
            self.assertNotIn(n, body)


# ---------------------------------------------------------------------------
# Guards that hold today
# ---------------------------------------------------------------------------
class GuardsThatHold(IsolationBase):

    def test_selector_refuses_a_company_the_user_is_not_in(self):
        self.login_a()
        resp = self.client.get('/app/help/', {'company': self.co_b.id})
        self.assertEqual(resp.context['tenancy_current_company'], self.co_a)
        self.assertEqual(self.client.session['scope_company'], str(self.co_a.id))
        self.assertNotIn(self.co_b, resp.context['tenancy_companies'])

    def test_selector_refuses_a_foreign_business_unit(self):
        self.login_a()
        resp = self.client.get('/app/help/', {'vertical': self.bu_b.id})
        self.assertIsNone(resp.context['tenancy_current_vertical'])
        self.assertEqual(self.client.session['scope_vertical'], 'all')

    def test_analytics_data_scope_refuses_foreign_ids(self):
        from app.integrations import ga4_dashboard
        DailyActual.objects.create(date=datetime.date.today(), vertical=self.bu_b, revenue=4321, visits=9, orders=1)
        rf = RequestFactory()
        for params in ({'company': self.co_b.id}, {'company': self.co_b.id, 'vertical': self.bu_b.id},
                       {'company': self.co_a.id, 'vertical': self.bu_b.id}):
            req = rf.get('/app/analytics/grow-sales/', params)
            req.user, req.session = self.a_admin, {}
            self.assertEqual(ga4_dashboard._scoped_verticals(req), [], params)
            self.assertFalse(ga4_dashboard._scope_has_actuals(req), params)
            self.assertIsNone(ga4_dashboard._resolve_scope(req), params)

    def test_company_details_cannot_edit_another_orgs_company(self):
        self.login_a()
        self.client.post('/app/company-details/', {'company': self.co_b.id, 'legal_name': 'Hijacked LLC'})
        self.co_b.refresh_from_db()
        self.assertEqual(self.co_b.legal_name, '')

    def test_billing_actions_only_touch_own_org(self):
        self.login_a()
        self.client.post('/app/billing/', {'action': 'cancel_account'})
        self.client.post('/app/billing/', {'action': 'save_billing_address', 'billing_legal_name': 'X'})
        self.org_b.refresh_from_db()
        self.assertEqual(self.org_b.plan_status, 'active')
        self.assertEqual(self.org_b.billing_legal_name, '')
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.plan_status, 'canceled')

    def test_billing_page_is_forbidden_to_plain_members(self):
        self.login_a(self.a_member)
        self.assertEqual(self.client.get('/app/billing/').status_code, 403)

    def test_score_weights_and_estimator_refuse_foreign_company(self):
        from project.models import EstimatorSettings, ScoringWeights
        self.login_a()
        self.client.post('/app/score-weights/', {'company': self.co_b.id, 'customer_value': 100})
        self.client.post('/app/estimator/', {'company': self.co_b.id, 'margin_factor': '0.9'})
        self.assertFalse(ScoringWeights.objects.filter(company=self.co_b).exists())
        self.assertFalse(EstimatorSettings.objects.filter(company=self.co_b).exists())

    def test_budget_post_refuses_foreign_business_unit(self):
        self.login_a()
        resp = self.client.post(f'/app/goals/?vertical={self.bu_b.id}', {'budget_1': '1'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(MonthlyGoal.objects.get(vertical=self.bu_b).budget, B_BUDGET)

    def test_insights_add_project_refuses_foreign_business_unit(self):
        from app import insights as I
        from app.models import MetricRecommendation
        rec = MetricRecommendation.objects.create(metric=I.METRIC_CHOICES[0][0], direction='win',
                                                  text='Planted recommendation')
        self.login_a()
        self.client.post('/app/insights/add-project/', {'recommendation_id': rec.id, 'vertical': self.bu_b.id})
        self.assertFalse(Project.objects.filter(name='Planted recommendation').exists())

    def test_cannot_vote_on_a_foreign_project(self):
        from project.models import ScoreVote
        self.login_a()
        self.client.post('/app/score-projects/', {'project_id': self.p_b.id, 'customer_value': 10})
        self.assertFalse(ScoreVote.objects.filter(project=self.p_b).exists())

    def test_manage_users_is_forbidden_to_plain_members(self):
        self.login_a(self.a_member)
        self.assertEqual(self.client.get('/app/manage-users/').status_code, 403)

    def test_project_delete_url_never_deletes(self):
        self.login_a()
        self.client.get(f'/project/{self.p_b.id}/delete/')
        self.assertTrue(Project.objects.filter(pk=self.p_b.pk).exists())


# ---------------------------------------------------------------------------
# Known leaks: B's projects are fetched by id with no tenant check
# (get_object_or_404(Project, pk=...) in project/views.py and strategy/views.py)
# ---------------------------------------------------------------------------
class ProjectByIdLeaks(IsolationBase):

    # LEAK: /project/<id>/ renders any org's project (name, value, owner, actions).
    @unittest.expectedFailure
    def test_project_overview(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/project/{self.p_b.id}/'))

    # LEAK: /project/<id>/actions/ lists any org's actions.
    @unittest.expectedFailure
    def test_project_actions_tab(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/project/{self.p_b.id}/actions/'))

    # LEAK: /project/<id>/performance/ shows any org's realized performance.
    @unittest.expectedFailure
    def test_project_performance_tab(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/project/{self.p_b_done.id}/performance/'))

    # LEAK: /project/<id>/edit/ opens any org's project in the edit form.
    @unittest.expectedFailure
    def test_project_edit_form(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/project/{self.p_b.id}/edit/'))

    # LEAK: /project/<id>/add-action/ accepts posts on any org's project.
    @unittest.expectedFailure
    def test_add_action(self):
        self.login_a()
        self.client.post(f'/project/{self.p_b.id}/add-action/', {'name': 'Injected', 'owner': self.a_admin.id})
        self.assertFalse(Action.objects.filter(project=self.p_b, name='Injected').exists())

    # LEAK: /project/<id>/comment/ writes a comment onto any org's project.
    @unittest.expectedFailure
    def test_comment(self):
        self.login_a()
        self.client.post(f'/project/{self.p_b.id}/comment/', {'text': 'Injected comment'})
        self.assertFalse(ProjectComment.objects.filter(project=self.p_b, text='Injected comment').exists())

    # LEAK: /project/<id>/approve/ toggles approval on any org's project (any logged-in user, even GET).
    @unittest.expectedFailure
    def test_approve_toggle(self):
        self.login_a(self.a_member)
        self.client.get(f'/project/{self.p_b.id}/approve/')
        self.p_b.refresh_from_db()
        self.assertTrue(self.p_b.approved)

    # LEAK: /project/<id>/archive/ archives any org's completed project (any logged-in user).
    @unittest.expectedFailure
    def test_archive(self):
        self.login_a(self.a_member)
        self.client.post(f'/project/{self.p_b_done.id}/archive/')
        self.p_b_done.refresh_from_db()
        self.assertFalse(self.p_b_done.archived)

    # LEAK: /project/kanban/move/ moves any org's project (role checked, tenant not).
    @unittest.expectedFailure
    def test_kanban_move(self):
        self.login_a()
        self.client.post('/project/kanban/move/', json.dumps({'project_id': self.p_b.id, 'target_lane': 'blocked'}),
                         content_type='application/json')
        self.p_b.refresh_from_db()
        self.assertEqual(self.p_b.status, 'WIP')

    # LEAK: /project/<id>/set-loe/ sizes any org's intake project (A's org admin counts as executive).
    @unittest.expectedFailure
    def test_set_loe(self):
        self.login_a()
        self.client.post(f'/project/{self.p_b_intake.id}/set-loe/', {'effort_size': 'XL', 'capability': 'fully'})
        self.p_b_intake.refresh_from_db()
        self.assertEqual(self.p_b_intake.effort_size, '')

    # LEAK: /project/<id>/analyst-review/ renders any org's project and baselines.
    @unittest.expectedFailure
    def test_analyst_review_page(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/project/{self.p_b_intake.id}/analyst-review/'))

    # LEAK: /strategy/<id>/ renders any org's project (legacy page).
    @unittest.expectedFailure
    def test_strategy_detail(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/strategy/{self.p_b.id}/'))

    # LEAK: /strategy/<id>/edit/ opens any org's project (legacy page).
    @unittest.expectedFailure
    def test_strategy_edit(self):
        self.login_a()
        self.assertBlocked(self.client.get(f'/strategy/{self.p_b.id}/edit/'))

    # LEAK: /strategy/<id>/comment/ writes onto any org's project (legacy page).
    @unittest.expectedFailure
    def test_strategy_comment(self):
        self.login_a()
        before = ProjectComment.objects.filter(project=self.p_b).count()
        self.client.post(f'/strategy/{self.p_b.id}/comment/', {'text': 'Injected via strategy'})
        self.assertEqual(ProjectComment.objects.filter(project=self.p_b).count(), before)


# ---------------------------------------------------------------------------
# Known leaks: list pages trust raw ?company= / ?vertical= (business_unit.scope
# reads the query string before the context processor validates it) and are
# unscoped when the session has no company yet (first page after login).
# ---------------------------------------------------------------------------
class ListScopeLeaks(IsolationBase):

    def _get(self, url, params=None, prime=True):
        self.login_a()
        if prime:   # settle the session on A's company first, as after a normal page view
            self.client.get('/app/help/')
            assert self.client.session['scope_company'] == str(self.co_a.id)
        return self.client.get(url, params or {})

    # LEAK: Backlog on the first request of a session is unscoped -> every org's projects.
    @unittest.expectedFailure
    def test_backlog_unscoped_first_request(self):
        self.assertNoB(self._get('/project/view.html', prime=False))

    # LEAK: Backlog with ?company=<B> lists B's projects.
    @unittest.expectedFailure
    def test_backlog_foreign_company_param(self):
        self.assertNoB(self._get('/project/view.html', {'company': self.co_b.id}))

    # LEAK: Backlog with ?vertical=<B unit> lists B's projects.
    @unittest.expectedFailure
    def test_backlog_foreign_vertical_param(self):
        self.assertNoB(self._get('/project/view.html', {'vertical': self.bu_b.id}))

    # LEAK: Kanban with ?company=<B> shows B's cards.
    @unittest.expectedFailure
    def test_kanban_foreign_company_param(self):
        self.assertNoB(self._get('/project/kanban/', {'company': self.co_b.id}))

    # LEAK: Completed Projects with ?company=<B> lists B's completed work.
    @unittest.expectedFailure
    def test_completed_foreign_company_param(self):
        self.assertNoB(self._get('/project/completed/', {'company': self.co_b.id}), B_DONE)

    # LEAK: Archive with ?company=<B> lists B's archived projects.
    @unittest.expectedFailure
    def test_archive_foreign_company_param(self):
        self.assertNoB(self._get('/project/archive/', {'company': self.co_b.id}), B_SHELVED)

    # LEAK: Approve Projects with ?company=<B> lists B's intake queue.
    @unittest.expectedFailure
    def test_approve_queue_foreign_company_param(self):
        self.assertNoB(self._get('/project/approve/', {'company': self.co_b.id}), B_INTAKE)

    # LEAK: Work In Progress gantt with ?company=<B> includes B's actions.
    @unittest.expectedFailure
    def test_wip_foreign_company_param(self):
        self.assertNoB(self._get('/app/work-in-progress/', {'company': self.co_b.id}), B_ACTION)

    # LEAK: Budget page with ?vertical=<B unit> shows B's monthly budget.
    @unittest.expectedFailure
    def test_budget_page_foreign_vertical_param(self):
        resp = self._get('/app/goals/', {'vertical': self.bu_b.id})
        self.assertNotIn('987654', resp.content.decode().replace(',', ''))


class PipelineScopeCheck(IsolationBase):
    """The Project Value Pipeline (/app/) sums WIP/On Deck value per objective.
    With a foreign ?company= the B project's value must not be counted."""

    # LEAK: /app/ (Project Value Pipeline) with ?company=<B> lists B's WIP actions.
    @unittest.expectedFailure
    def test_pipeline_foreign_company_param(self):
        self.login_a()
        resp = self.client.get('/app/', {'company': self.co_b.id})
        self.assertNoB(resp, B_ACTION)


# ---------------------------------------------------------------------------
# Known leaks: data writes and admin screens not tied to the user's org
# ---------------------------------------------------------------------------
class AdminScreenLeaks(IsolationBase):

    # LEAK: Upload Actuals lists every org's business units in its picker.
    @unittest.expectedFailure
    def test_upload_actuals_picker(self):
        self.login_a()
        self.assertNoB(self.client.get('/app/actuals/'), 'Beta Unit')

    # LEAK: Upload Actuals writes revenue into any org's business unit.
    @unittest.expectedFailure
    def test_upload_actuals_write(self):
        self.login_a()
        csv_file = io.BytesIO(b'Date,Actual Revenue\n2026-01-05,123\n')
        csv_file.name = 'actuals.csv'
        self.client.post('/app/actuals/', {'vertical': self.bu_b.id, 'csv_file': csv_file})
        self.assertFalse(DailyActual.objects.filter(vertical=self.bu_b).exists())

    # LEAK: Manage Users shows every company's members to any org admin or Executive.
    @unittest.expectedFailure
    def test_manage_users_lists_other_orgs(self):
        self.login_a()
        self.assertNoB(self.client.get('/app/manage-users/'), B_EMAIL, 'Beta Co')

    # LEAK: Manage Users lets any org admin add themselves (or anyone) to another org's company.
    @unittest.expectedFailure
    def test_manage_users_add_member_to_other_org(self):
        self.login_a()
        self.client.post('/app/manage-users/', {'action': 'add_member', 'company': self.co_b.id,
                                                'email': self.a_admin.email, 'roles': ['executive']})
        self.assertFalse(CompanyMembership.objects.filter(company=self.co_b, user=self.a_admin).exists())

    # LEAK: Manage Users lets any org admin remove another org's members.
    @unittest.expectedFailure
    def test_manage_users_remove_member_of_other_org(self):
        extra = User.objects.create_user('beta_staff', 'staff@beta-co.test', 'pw')
        m = CompanyMembership.objects.create(company=self.co_b, user=extra, role='member')
        self.login_a()
        self.client.post('/app/manage-users/', {'action': 'remove_member', 'company': self.co_b.id,
                                                'membership_id': m.id})
        self.assertTrue(CompanyMembership.objects.filter(pk=m.pk).exists())
