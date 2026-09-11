"""Phase 1 org setup — idempotent, safe to run locally and on the server.

Creates the Organization tenant layer and slots the existing companies under it:
  * Querybridge (agency) -> VOLT Lighting, Autocado         admin: sherman
  * Belami (direct)      -> Belami                          admin: belami
  * Demo (platform)      -> Demo Account (visible to trials)
  * VW Group             -> DELETED (company + everything exclusive to it)

Re-running only fills gaps; it won't duplicate orgs or re-delete.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.text import slugify

from business_unit.models import Organization, Company


ORG_SPECS = [
    # (org name, kind, is_platform_demo, admin username/email, [company names])
    ('Querybridge', 'agency', False, 'sherman@querybridge.com', ['VOLT Lighting', 'Autocado']),
    ('Belami', 'direct', False, 'belami', ['Belami']),
    ('Demo', 'direct', True, None, ['Demo Account']),
]
DELETE_COMPANIES = ['VW Group']


class Command(BaseCommand):
    help = 'Create Organizations, assign companies, delete VW Group (idempotent).'

    def _find_user(self, ident):
        if not ident:
            return None
        return (User.objects.filter(username__iexact=ident).first()
                or User.objects.filter(email__iexact=ident).first())

    def handle(self, *args, **opts):
        for name, kind, is_demo, admin_ident, companies in ORG_SPECS:
            admin = self._find_user(admin_ident)
            org, created = Organization.objects.get_or_create(
                slug=slugify(name),
                defaults={'name': name, 'kind': kind, 'is_platform_demo': is_demo,
                          'org_admin': admin, 'plan_status': 'active', 'trial_started': None})
            # keep fields in sync on re-run
            changed = False
            for field, val in (('name', name), ('kind', kind),
                               ('is_platform_demo', is_demo), ('plan_status', 'active')):
                if getattr(org, field) != val:
                    setattr(org, field, val); changed = True
            if admin and org.org_admin_id != admin.id:
                org.org_admin = admin; changed = True
            if changed:
                org.save()
            self.stdout.write(f"{'created' if created else 'updated'} org: {org.name} "
                              f"({org.kind}{', demo' if is_demo else ''}) "
                              f"admin={org.org_admin.username if org.org_admin else '—'}")

            for cname in companies:
                comp = Company.objects.filter(name=cname).first()
                if not comp:
                    self.stdout.write(self.style.WARNING(f"  ! company not found: {cname}"))
                    continue
                if comp.organization_id != org.id:
                    comp.organization = org
                    comp.save(update_fields=['organization'])
                self.stdout.write(f"  -> {comp.name}")

        for cname in DELETE_COMPANIES:
            comp = Company.objects.filter(name=cname).first()
            if not comp:
                self.stdout.write(f"already gone: {cname}")
                continue
            vcount = comp.verticals.count()
            from business_unit.models import Website, CompanyMembership
            wcount = Website.objects.filter(vertical__company=comp).count()
            mcount = CompanyMembership.objects.filter(company=comp).count()
            comp.delete()  # cascades verticals/websites/memberships/bigquery
            self.stdout.write(self.style.SUCCESS(
                f"deleted company {cname} (+{vcount} business units, {wcount} websites, {mcount} memberships)"))

        self.stdout.write(self.style.SUCCESS('seed_organizations complete.'))
