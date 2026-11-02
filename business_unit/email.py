"""Outgoing email through SendGrid.

The API key and sender live in IntegrationSettings (Django admin). Until they are
filled in, send() logs the message and returns False instead of raising, so the
app keeps working before email is set up. Callers never need a try/except.
"""
import contextlib
import logging
import threading

from django.conf import settings
from django.template.loader import render_to_string

log = logging.getLogger(__name__)
_state = threading.local()


@contextlib.contextmanager
def suppressed():
    """Send nothing inside this block (seed / demo commands)."""
    prev = getattr(_state, 'off', False)
    _state.off = True
    try:
        yield
    finally:
        _state.off = prev


def quiet(fn):
    """Decorator: run a management command's handle() without sending email."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with suppressed():
            return fn(*args, **kwargs)
    return wrapper


def is_suppressed():
    return getattr(_state, 'off', False)


# Placeholder domains used by demo / seed users; never worth sending to.
_RESERVED = ('example.com', 'example.org', 'example.net')
_RESERVED_TLDS = ('.test', '.invalid', '.localhost', '.example')


def _reserved(address):
    domain = address.strip().rsplit('@', 1)[-1].lower()
    return domain in _RESERVED or domain.endswith(_RESERVED_TLDS)


def is_configured():
    from business_unit.models import IntegrationSettings
    s = IntegrationSettings.current()
    return bool(s.sendgrid_api_key and s.email_from_address)


def site_url():
    """Base URL for links in emails (no trailing slash)."""
    from business_unit.models import IntegrationSettings
    return (IntegrationSettings.current().site_url or getattr(settings, 'SITE_URL', '')
            or 'http://localhost:8000').rstrip('/')


def send(to, subject, template, context, reply_to=None):
    """Email `to` (address or list) using templates/emails/<template>.txt and .html.
    Returns True if SendGrid accepted it."""
    from business_unit.models import IntegrationSettings

    recipients = sorted({a.strip() for a in ([to] if isinstance(to, str) else to)
                         if a and a.strip() and not _reserved(a)})
    if not recipients or is_suppressed():
        return False
    s = IntegrationSettings.current()
    ctx = {'site_url': site_url(), **context}
    text = render_to_string(f'emails/{template}.txt', ctx)
    html = render_to_string(f'emails/{template}.html', ctx)

    if not (s.sendgrid_api_key and s.email_from_address):
        log.info('Email not sent (SendGrid not configured): %r to %s', subject, recipients)
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, From
        ok = True
        # One message per recipient so addresses aren't exposed to each other.
        for addr in recipients:
            msg = Mail(from_email=From(s.email_from_address, s.email_from_name or 'Kiboko'),
                       to_emails=addr, subject=subject, plain_text_content=text, html_content=html)
            if reply_to:
                msg.reply_to = reply_to
            resp = SendGridAPIClient(s.sendgrid_api_key).send(msg)
            ok = ok and 200 <= resp.status_code < 300
        return ok
    except Exception:
        log.exception('SendGrid send failed: %r to %s', subject, recipients)
        return False
