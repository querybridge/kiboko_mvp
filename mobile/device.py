"""Phone detection and the desktop <-> mobile page map.

Kiboko has two separate experiences rather than one responsive one: phones get
the /m/ app (built for a busy executive on the go), everything else gets the
desktop app. A visitor can override the choice with ?ui=mobile or ?ui=desktop,
which is remembered in the kb_ui cookie."""
import re

from django.urls import Resolver404, resolve, reverse

PREF_COOKIE = 'kb_ui'
PREF_MAX_AGE = 365 * 24 * 3600

# Phones only: tablets (iPad, Android tablets without "Mobile") get the desktop
# app, which works well at their size. iPadOS also reports itself as a Mac.
_PHONE_RE = re.compile(r'iPhone|iPod|Windows Phone|IEMobile|BlackBerry|BB10|Opera Mini|Android.*Mobile', re.I)


def is_phone(request):
    ua = request.META.get('HTTP_USER_AGENT', '')
    return bool(ua and _PHONE_RE.search(ua))


def preference(request):
    """'mobile', 'desktop', or '' (none chosen): ?ui= first, then the cookie."""
    pref = request.GET.get('ui') or request.COOKIES.get(PREF_COOKIE, '')
    return pref if pref in ('mobile', 'desktop') else ''


def wants_mobile(request):
    pref = preference(request)
    return pref == 'mobile' if pref else is_phone(request)


# Desktop path -> mobile url name. Pages without a mobile version (settings,
# billing, data connection, ...) stay on desktop.
_TO_MOBILE = {
    '/': 'mobile:start',
    '/app/': 'mobile:home',
    '/app/home/': 'mobile:start',      # post-login: the user's default home page
    '/app/analytics/': 'mobile:story',
    '/app/analytics/grow-sales/': 'mobile:story',
    '/app/analytics/performance-story/': 'mobile:story',
    '/app/analytics/attract-traffic/': 'mobile:story',
    '/app/analytics/engage-customers/': 'mobile:story',
    '/app/analytics/expand-purchases/': 'mobile:story',
    '/project/executive-approval/': 'mobile:approve',
    '/project/approve/': 'mobile:approve',
    '/app/score-projects/': 'mobile:score',
    '/project/view.html': 'mobile:projects',
    '/project/kanban/': 'mobile:projects',
    '/app/work-in-progress/': 'mobile:projects',
    '/project/completed/': 'mobile:projects',
    '/project/add.html': 'mobile:add',
}
_PROJECT_RE = re.compile(r'^/project/(\d+)/(?:(?:overview|actions|performance|activity)/)?$')

# Mobile url name -> desktop path (for a non-phone that lands on /m/).
_TO_DESKTOP = {
    'start': '/app/home/',
    'home': '/app/',
    'forecast': '/app/',
    'approve': '/project/executive-approval/',
    'score': '/app/score-projects/',
    'score_project': '/app/score-projects/',
    'projects': '/project/view.html',
    'add': '/project/add.html',
    'story': '/app/analytics/performance-story/',
}


def mobile_url_for(path):
    """The mobile page for a desktop path, or None."""
    name = _TO_MOBILE.get(path)
    if name:
        return reverse(name)
    m = _PROJECT_RE.match(path)
    if m:
        return reverse('mobile:project', kwargs={'project_id': int(m.group(1))})
    return None


def desktop_url_for(path):
    """The desktop page for a mobile path, or None."""
    try:
        match = resolve(path)
    except Resolver404:
        return None
    if match.namespace != 'mobile':
        return None
    if match.url_name == 'project':
        return f"/project/{match.kwargs['project_id']}/"
    return _TO_DESKTOP.get(match.url_name, '/app/')
