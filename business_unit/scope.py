"""Shared helpers for the current tenancy scope (Company / BusinessUnit / Website).

The top-bar BusinessUnit selector drives both the GA4 data scope and the existing PPM
vertical filtering, so both read the same source: the `?vertical=` query param
(when the selector just changed) falling back to the session scope.
"""


def scoped_company_id(request):
    """The selected Company id, or None. Prefers the live `?company=` query param
    (the selector emits it on change), then the persisted session scope."""
    val = request.GET.get('company', None)
    if val is None:
        val = request.session.get('scope_company')
    if not val or val == 'all':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def scoped_vertical_id(request):
    """The selected BusinessUnit id, or None for the 'All Verticals' roll-up.

    Prefers the live query param (the selector emits `?vertical=` on change), then
    the persisted session scope. 'all' / '' -> None.
    """
    val = request.GET.get('vertical', None)
    if val is None:
        val = request.session.get('scope_vertical')
    if not val or val == 'all':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
