"""Force a password change on first login for admin-created (temporary-password)
accounts. Until the user changes their password, every page redirects to User
Settings. Google accounts never set the flag, so they're unaffected."""
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            prof = getattr(user, 'profile', None)
            if prof is not None and getattr(prof, 'must_change_password', False):
                path = request.path
                allowed = (
                    path == reverse('users:profile')
                    or path == reverse('users:logout')
                    or path.startswith('/auth/')          # Google OAuth
                    or path.startswith('/static/')
                    or path.startswith('/media/')
                    or path.startswith('/admin/')
                )
                if not allowed:
                    # The profile page shows an amber "temporary password" alert;
                    # no toast here (it would be redundant).
                    return redirect('users:profile')
        return self.get_response(request)
