from business_unit.models import Company, BusinessUnit, Website


def google_flags(request):
    """Expose whether Google sign-in is configured (for the login page CTA)."""
    from app.integrations import google_oauth
    return {'google_oauth_enabled': google_oauth.is_enabled()}


def getting_started_banner(request):
    """Onboarding state for the "Return to Getting Started" banner shown on each
    step's page during initial setup. Returns nothing once every step is done, so
    the banner disappears. Each step is annotated with the next incomplete step."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from app.views import getting_started_steps
        org, steps = getting_started_steps(user)
    except Exception:
        return {}
    if not org or not steps:
        return {}
    incomplete = [s for s in steps if not s['done']]
    if not incomplete:
        return {}                                   # all set up -> no banner anywhere
    for i, s in enumerate(steps):
        nxt = next((t for t in steps[i + 1:] if not t['done']), None)
        if nxt is None:
            nxt = next((t for t in incomplete if t['key'] != s['key']), None)
        s['next'] = nxt
    return {'gs_setup': {'active': True, 'steps': steps,
                         'done_count': sum(1 for s in steps if s['done']),
                         'total': len(steps)}}


def tenancy_selector(request):
    """Cascading Company -> BusinessUnit -> Website scope for the top bar.

    - Company: the customer (a user only sees companies they belong to; a
      superuser sees all).
    - BusinessUnit: a GA4 property / business unit. 'all' = company roll-up (Summary).
    - Website: a GA4 data stream. 'all' = BusinessUnit roll-up (sum of its streams).

    Selection persists in the session and cascades (changing Company resets
    BusinessUnit + Website; changing BusinessUnit resets Website). The BusinessUnit scope also
    drives the existing PPM vertical filtering via business_unit.scope.
    """
    from business_unit.access import visible_companies, allowed_bu_ids, has_real_company, contact_admin

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    demo_only = not user.is_superuser and not has_real_company(user)

    companies = list(visible_companies(user))
    if not companies:
        return {'tenancy_companies': [], 'tenancy_current_company': None,
                'tenancy_demo_only': demo_only, 'tenancy_contact_admin': contact_admin(user)}

    # Per-user business-unit visibility: {company_id: set(bu_id) or None(=all)}.
    bu_scope = {c.id: allowed_bu_ids(user, c) for c in companies}

    def _visible_bus(company):
        allowed = bu_scope.get(company.id)
        bus = company.verticals.all()
        return [b for b in bus if allowed is None or b.id in allowed]

    s = request.session

    # --- Company (cascade-resets BusinessUnit + Website when it changes) ---
    if 'company' in request.GET:
        if str(s.get('scope_company')) != str(request.GET['company']):
            s['scope_vertical'] = 'all'
            s['scope_website'] = 'all'
        s['scope_company'] = request.GET['company']
    company_ids = {str(c.id) for c in companies}
    if str(s.get('scope_company')) not in company_ids:
        s['scope_company'] = str(companies[0].id)
    current_company = next(c for c in companies if str(c.id) == str(s['scope_company']))

    verticals = _visible_bus(current_company)

    # --- BusinessUnit ('all' = company roll-up / Summary; resets Website) ---
    if 'vertical' in request.GET:
        if str(s.get('scope_vertical')) != str(request.GET['vertical']):
            s['scope_website'] = 'all'
        s['scope_vertical'] = request.GET['vertical'] or 'all'
    vertical_sel = str(s.get('scope_vertical', 'all'))
    if vertical_sel != 'all' and vertical_sel not in {str(v.id) for v in verticals}:
        vertical_sel = 'all'
    s['scope_vertical'] = vertical_sel
    current_vertical = None if vertical_sel == 'all' else next(v for v in verticals if str(v.id) == vertical_sel)

    websites = list(Website.objects.filter(vertical=current_vertical)) if current_vertical else []

    # --- Website ('all' = BusinessUnit roll-up, i.e. summed streams) ---
    if 'website' in request.GET:
        s['scope_website'] = request.GET['website']
    website_sel = str(s.get('scope_website', 'all'))
    if website_sel != 'all' and website_sel not in {str(w.id) for w in websites}:
        website_sel = 'all'
    s['scope_website'] = website_sel
    current_website = None if website_sel == 'all' else next(w for w in websites if str(w.id) == website_sel)

    # Full tree (company -> verticals -> websites) for client-side cascade, so the
    # BusinessUnit/Website dropdowns update without a page load/query until Apply.
    company_ids_list = [c.id for c in companies]
    verts_by_company = {}
    for v in BusinessUnit.objects.filter(company_id__in=company_ids_list):
        allowed = bu_scope.get(v.company_id)
        if allowed is None or v.id in allowed:      # honor per-user BU visibility
            verts_by_company.setdefault(v.company_id, []).append(v)
    sites_by_vertical = {}
    for w in Website.objects.filter(vertical__company_id__in=company_ids_list):
        sites_by_vertical.setdefault(w.vertical_id, []).append(w)
    tree = {str(c.id): {'verticals': [
        {'id': v.id, 'name': v.name,
         'websites': [{'id': w.id, 'name': w.name} for w in sites_by_vertical.get(v.id, [])]}
        for v in verts_by_company.get(c.id, [])]} for c in companies}

    org = current_company.organization
    is_agency = bool(org and org.kind == 'agency')

    return {
        'tenancy_companies': companies,
        'tenancy_verticals': verticals,
        'tenancy_websites': websites,
        'tenancy_current_company': current_company,
        'tenancy_current_org': org,
        'tenancy_vertical_sel': vertical_sel,
        'tenancy_website_sel': website_sel,
        'tenancy_current_vertical': current_vertical,
        'tenancy_current_website': current_website,
        'tenancy_tree': tree,
        'tenancy_demo_only': demo_only,
        'tenancy_contact_admin': contact_admin(user, current_company),
        'tenancy_client_word': 'Client' if is_agency else 'Company',
        'tenancy_client_word_plural': 'Clients' if is_agency else 'Companies',
    }
