"""Shared helpers for the current tenancy scope (Company / Vertical / Website).

The top-bar Vertical selector drives both the GA4 data scope and the existing PPM
vertical filtering, so both read the same source: the `?vertical=` query param
(when the selector just changed) falling back to the session scope.
"""


def scoped_vertical_id(request):
    """The selected Vertical id, or None for the 'All Verticals' roll-up.

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
