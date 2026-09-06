"""'Sign in with Google' OAuth flow + credential handling.

Kiboko authenticates users with Google and reads GA4 on their behalf, so a user
only sees GA4 data their own Google account can access. This module wraps the
OAuth2 authorization-code flow and turns the result into a linked
``GoogleIdentity``.

Google client libraries are imported lazily so this module loads even when they
aren't installed. Requires (add to requirements):
    google-auth, google-auth-oauthlib

Activation: set GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REDIRECT_URI in
local_settings.py. Until then ``is_enabled()`` returns False and the app uses the
existing login.
"""
import os

from django.conf import settings

GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'


def _relax_oauth_env():
    """Dev-friendliness for the OAuth library:

    - OAUTHLIB_RELAX_TOKEN_SCOPE: Google may return scopes in a different order /
      add 'openid', which otherwise makes oauthlib raise "Scope has changed".
    - OAUTHLIB_INSECURE_TRANSPORT: allow an http:// redirect URI for local dev
      (never used for the https production redirect).
    """
    os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')
    if str(getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')).startswith('http://'):
        os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')


class GoogleOAuthNotConfigured(RuntimeError):
    pass


def is_enabled():
    """True when a Google OAuth client id + secret are configured."""
    return bool(getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
                and getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''))


def _require_config():
    if not is_enabled():
        raise GoogleOAuthNotConfigured(
            'Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in '
            'local_settings.py to enable Google sign-in.')


def _client_config():
    return {
        'web': {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'auth_uri': GOOGLE_AUTH_URI,
            'token_uri': GOOGLE_TOKEN_URI,
            'redirect_uris': [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def _flow(state=None):
    _require_config()
    _relax_oauth_env()
    from google_auth_oauthlib.flow import Flow  # lazy import
    flow = Flow.from_client_config(
        _client_config(), scopes=settings.GOOGLE_OAUTH_SCOPES, state=state)
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    return flow


def authorization_url():
    """(url, state, code_verifier) to redirect the user to Google's consent screen.

    access_type=offline + prompt=consent so we always receive a refresh token.
    Google uses PKCE, so the generated code_verifier must be persisted and handed
    back to exchange_code().
    """
    flow = _flow()
    url, state = flow.authorization_url(
        access_type='offline', include_granted_scopes='true', prompt='consent')
    return url, state, getattr(flow, 'code_verifier', None)


def exchange_code(code, state=None, code_verifier=None):
    """Exchange the callback ``code`` for credentials + verified id-token claims.

    Returns (credentials, claims) where claims has: sub, email, name, picture.
    ``code_verifier`` must be the PKCE verifier issued by authorization_url().
    """
    flow = _flow(state=state)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    return creds, _verify_id_token(creds)


def _verify_id_token(creds):
    from google.oauth2 import id_token  # lazy
    from google.auth.transport import requests as google_requests
    return id_token.verify_oauth2_token(
        creds.id_token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID)


def credentials_from_identity(identity):
    """Build refreshed Credentials from a stored GoogleIdentity's refresh token.

    Used for background/GA4 calls on the user's behalf.
    """
    _require_config()
    if not identity.refresh_token:
        raise GoogleOAuthNotConfigured('No stored refresh token for this user.')
    from google.oauth2.credentials import Credentials  # lazy
    from google.auth.transport.requests import Request
    creds = Credentials(
        token=None,
        refresh_token=identity.refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=settings.GOOGLE_OAUTH_SCOPES,
    )
    creds.refresh(Request())
    return creds


def upsert_identity(user, creds, claims):
    """Create/update the user's GoogleIdentity from an OAuth result.

    NOTE: refresh_token is stored in plaintext here for scaffolding -- encrypt it
    with django-cryptography before storing real tokens (see the plan).
    """
    from business_unit.models import GoogleIdentity
    from django.utils import timezone
    defaults = {
        'user': user,
        'email': claims.get('email', ''),
        'picture_url': claims.get('picture', ''),
    }
    if getattr(creds, 'refresh_token', None):
        defaults['refresh_token'] = creds.refresh_token
    if getattr(creds, 'expiry', None):
        defaults['token_expiry'] = creds.expiry if timezone.is_aware(creds.expiry) \
            else timezone.make_aware(creds.expiry)
    identity, _ = GoogleIdentity.objects.update_or_create(
        google_sub=claims['sub'], defaults=defaults)
    return identity
