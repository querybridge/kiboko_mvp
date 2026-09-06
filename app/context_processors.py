from business_unit.models import Company, Website


def tenancy_selector(request):
    """Cascading Company -> Vertical -> Website scope for the top bar.

    - Company: the customer (a user only sees companies they belong to; a
      superuser sees all).
    - Vertical: a GA4 property / business unit. 'all' = company roll-up (Summary).
    - Website: a GA4 data stream. 'all' = Vertical roll-up (sum of its streams).

    Selection persists in the session and cascades (changing Company resets
    Vertical + Website; changing Vertical resets Website). The Vertical scope also
    drives the existing PPM vertical filtering via business_unit.scope.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    if user.is_superuser:
        companies = list(Company.objects.all())
    else:
        companies = list(Company.objects.filter(memberships__user=user).distinct())
    if not companies:
        return {'tenancy_companies': [], 'tenancy_current_company': None}

    s = request.session

    # --- Company (cascade-resets Vertical + Website when it changes) ---
    if 'company' in request.GET:
        if str(s.get('scope_company')) != str(request.GET['company']):
            s['scope_vertical'] = 'all'
            s['scope_website'] = 'all'
        s['scope_company'] = request.GET['company']
    company_ids = {str(c.id) for c in companies}
    if str(s.get('scope_company')) not in company_ids:
        s['scope_company'] = str(companies[0].id)
    current_company = next(c for c in companies if str(c.id) == str(s['scope_company']))

    verticals = list(current_company.verticals.all())

    # --- Vertical ('all' = company roll-up / Summary; resets Website) ---
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

    # --- Website ('all' = Vertical roll-up, i.e. summed streams) ---
    if 'website' in request.GET:
        s['scope_website'] = request.GET['website']
    website_sel = str(s.get('scope_website', 'all'))
    if website_sel != 'all' and website_sel not in {str(w.id) for w in websites}:
        website_sel = 'all'
    s['scope_website'] = website_sel
    current_website = None if website_sel == 'all' else next(w for w in websites if str(w.id) == website_sel)

    return {
        'tenancy_companies': companies,
        'tenancy_verticals': verticals,
        'tenancy_websites': websites,
        'tenancy_current_company': current_company,
        'tenancy_vertical_sel': vertical_sel,
        'tenancy_website_sel': website_sel,
        'tenancy_current_vertical': current_vertical,
        'tenancy_current_website': current_website,
    }
