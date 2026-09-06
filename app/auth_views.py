"""Sign in with Google — OAuth login + callback.

Gated by app.integrations.google_oauth.is_enabled(): when no Google credentials
are configured these routes just bounce back to the normal login page, so the
existing username/password login (the superuser/break-glass fallback) keeps
working.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect

from app.integrations import google_oauth
from business_unit.models import GoogleIdentity

logger = logging.getLogger(__name__)

_LOGIN = 'users:login'


def google_login(request):
    """Kick off the OAuth flow -> redirect to Google's consent screen."""
    if not google_oauth.is_enabled():
        return redirect(_LOGIN)
    url, state, code_verifier = google_oauth.authorization_url()
    request.session['google_oauth_state'] = state
    request.session['google_oauth_code_verifier'] = code_verifier
    return redirect(url)


def google_callback(request):
    """Handle Google's redirect: exchange the code, link/find the user, log in."""
    if not google_oauth.is_enabled():
        return redirect(_LOGIN)

    if request.GET.get('error'):
        messages.error(request, f"Google sign-in was cancelled ({request.GET['error']}).")
        return redirect(_LOGIN)

    state = request.session.pop('google_oauth_state', None)
    code_verifier = request.session.pop('google_oauth_code_verifier', None)
    if not state or request.GET.get('state') != state:
        return HttpResponseBadRequest('Invalid OAuth state.')

    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Google sign-in failed: no authorization code.')
        return redirect(_LOGIN)

    try:
        creds, claims = google_oauth.exchange_code(code, state=state, code_verifier=code_verifier)
    except Exception as e:
        logger.exception('Google OAuth token exchange failed')
        # Verbose during pilot so the cause is visible in the UI; tighten later.
        messages.error(request, f'Google sign-in failed: {type(e).__name__}: {e}')
        return redirect(_LOGIN)

    sub = claims.get('sub')
    email = (claims.get('email') or '').strip()

    # Prefer an already-linked identity; else link an existing user by email;
    # else create a new user (a Google account added to Kiboko).
    identity = GoogleIdentity.objects.filter(google_sub=sub).select_related('user').first()
    if identity:
        user = identity.user
    else:
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is None:
            username = (email or f'google_{sub}')[:150]
            user = User.objects.create_user(username=username, email=email)

    google_oauth.upsert_identity(user, creds, claims)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect(settings.LOGIN_REDIRECT_URL)
