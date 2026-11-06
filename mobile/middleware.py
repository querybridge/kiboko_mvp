"""Send each visitor to the experience built for their device (see mobile.device)."""
from django.shortcuts import redirect

from mobile import device

_SKIP_PREFIXES = ('/static/', '/media/', '/admin/', '/auth/', '/billing/', '/email/', '/legal/', '/users/')


class DeviceRouterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        target = self._route(request)
        response = redirect(target) if target else self.get_response(request)
        pref = request.GET.get('ui')
        if pref in ('mobile', 'desktop'):
            response.set_cookie(device.PREF_COOKIE, pref, max_age=device.PREF_MAX_AGE,
                                samesite='Lax', secure=request.is_secure())
        return response

    def _route(self, request):
        if request.method not in ('GET', 'HEAD'):
            return None
        path = request.path_info
        if path.startswith(_SKIP_PREFIXES):
            return None
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return None
        on_mobile = path == '/m/' or path.startswith('/m/')
        mobile = device.wants_mobile(request)
        if mobile and not on_mobile:
            target = device.mobile_url_for(path)
            if target is None and request.GET.get('ui') == 'mobile':
                target = '/m/'            # an explicit switch from a desktop-only page
        elif on_mobile and not mobile:
            target = device.desktop_url_for(path)
        else:
            return None
        if not target:
            return None
        query = request.GET.copy()
        query.pop('ui', None)
        return f'{target}?{query.urlencode()}' if query else target
