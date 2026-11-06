"""The Project Pipeline Value page always shows Attract, Engage and Expand tiles."""
from django.contrib.auth.models import User
from django.test import TestCase

from business_unit.models import BusinessUnit, Company, CompanyMembership, Organization
from strategy.models import Objective, seed_default_objectives


class PipelineTilesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('lead', 'lead@x.test', 'pw')
        org = Organization.objects.create(name='o', slug='o', org_admin=self.user, plan_status='active')
        self.co = Company.objects.create(organization=org, name='Co', slug='co')   # seeds 3 objectives
        BusinessUnit.objects.create(name='Unit', company=self.co)
        CompanyMembership.objects.create(company=self.co, user=self.user, role='admin')
        self.client.force_login(self.user)

    def tiles(self):
        resp = self.client.get(f'/app/?company={self.co.id}&vertical=all')
        self.assertEqual(resp.status_code, 200)
        return [(t['aee_element'], t['rock'].name) for t in resp.context['annual_rocks_data']]

    def test_three_tiles_even_with_one_objective(self):
        Objective.objects.filter(company=self.co).exclude(aee_alignment='attract_traffic').delete()
        self.assertEqual([a for a, _ in self.tiles()], ['Attract', 'Engage', 'Expand'])

    def test_three_tiles_with_no_objectives_this_year(self):
        Objective.objects.filter(company=self.co).delete()
        self.assertEqual(self.tiles(), [('Attract', 'Increase Shopper Volume'), ('Engage', 'Increase Close Rate'),
                                        ('Expand', 'Increase Average Order Value')])

    def test_seeding_fills_only_missing_elements(self):
        Objective.objects.filter(company=self.co, aee_alignment='engage_customers').delete()
        seed_default_objectives(self.co)
        self.assertEqual(Objective.objects.filter(company=self.co).count(), 3)
        seed_default_objectives(self.co)                       # idempotent
        self.assertEqual(Objective.objects.filter(company=self.co).count(), 3)
