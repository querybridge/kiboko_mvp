"""Shared helpers for the current tenancy scope (Company / BusinessUnit / Website).

The top-bar BusinessUnit selector drives both the GA4 data scope and the existing PPM
vertical filtering, so both read the same source: the `?company=` / `?vertical=`
query params (when the selector just changed) falling back to the session scope.

Every value is checked against what the user may see, with the same rules as the
selector (app.context_processors.tenancy_selector): an unknown or foreign company
falls back to the user's first company, and a business unit outside that company
(or outside the user's allowed units) falls back to the company roll-up. A user
with no visible company gets NO_ACCESS, which matches nothing, so list pages never
fall through to an unscoped query.
"""

NO_ACCESS = -1  # a company id no row has: filters to nothing, but is truthy for `if company_id:`


def _resolve(request):
    cached = getattr(request, '_kiboko_scope', None)
    if cached is not None:
        return cached

    from business_unit.access import allowed_bu_ids, visible_companies
    from business_unit.models import BusinessUnit

    user = getattr(request, 'user', None)
    companies = list(visible_companies(user)) if user is not None else []
    if not companies:
        request._kiboko_scope = (NO_ACCESS, None)
        return request._kiboko_scope

    session = getattr(request, 'session', {}) or {}
    raw_company = request.GET.get('company', None)
    company_changed = raw_company is not None and str(raw_company) != str(session.get('scope_company'))
    if raw_company is None:
        raw_company = session.get('scope_company')
    by_id = {str(c.id): c for c in companies}
    company = by_id.get(str(raw_company)) or companies[0]

    raw_vertical = request.GET.get('vertical', None)
    if raw_vertical is None:
        # A company switch without a unit resets to the roll-up, as the selector does.
        raw_vertical = 'all' if company_changed else session.get('scope_vertical')
    vertical_id = None
    if raw_vertical not in (None, '', 'all'):
        allowed = allowed_bu_ids(user, company)
        try:
            candidate = int(raw_vertical)
        except (TypeError, ValueError):
            candidate = None
        if (candidate is not None
                and BusinessUnit.objects.filter(pk=candidate, company=company).exists()
                and (allowed is None or candidate in allowed)):
            vertical_id = candidate

    request._kiboko_scope = (company.id, vertical_id)
    return request._kiboko_scope


def scoped_company_id(request):
    """The selected Company id: always one the user may see, else NO_ACCESS."""
    return _resolve(request)[0]


def scoped_vertical_id(request):
    """The selected BusinessUnit id inside the scoped company, or None for the
    company roll-up (Summary)."""
    return _resolve(request)[1]
