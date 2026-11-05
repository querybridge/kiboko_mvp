"""Outgoing email through SendGrid.

The API key and sender live in IntegrationSettings (Django admin). Until they are
filled in, send() logs the message and returns False instead of raising, so the
app keeps working before email is set up. Callers never need a try/except.
"""
import contextlib
import logging
import threading

from django.conf import settings
from django.core import signing
from django.template.loader import render_to_string
from django.urls import reverse

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


# Automatic emails people can turn off. Anything sent without a category is a
# service email (invite, trial code, password reset, billing) and always goes out.
OPTIONAL_CATEGORIES = {
    'project_updates': 'project update emails',
    'marketing': 'trial follow-up and product news emails',
}
_UNSUB_SALT = 'kiboko.email.unsubscribe'


def unsubscribe_token(address, category):
    return signing.dumps({'e': address.strip().lower(), 'c': category}, salt=_UNSUB_SALT)


def read_unsubscribe_token(token):
    """(email, category) from a link token, or None if it was tampered with."""
    try:
        data = signing.loads(token, salt=_UNSUB_SALT)
    except signing.BadSignature:
        return None
    if data.get('c') not in OPTIONAL_CATEGORIES or not data.get('e'):
        return None
    return data['e'], data['c']


def unsubscribe_url(address, category):
    return site_url() + reverse('email_unsubscribe', args=[unsubscribe_token(address, category)])


def is_opted_out(address, category):
    from business_unit.models import EmailOptOut
    return EmailOptOut.objects.filter(email=address.strip().lower(), category=category).exists()


def set_opted_out(address, category, opted_out=True, source='link'):
    from business_unit.models import EmailOptOut
    address = address.strip().lower()
    if opted_out:
        EmailOptOut.objects.get_or_create(email=address, category=category, defaults={'source': source})
    else:
        EmailOptOut.objects.filter(email=address, category=category).delete()


def send(to, subject, template, context, reply_to=None, category=None):
    """Email `to` (address or list) using templates/emails/<template>.txt and .html.
    With a `category` from OPTIONAL_CATEGORIES, skips addresses that opted out and
    adds an unsubscribe link plus one-click List-Unsubscribe headers.
    Returns True if SendGrid accepted it."""
    from business_unit.models import IntegrationSettings

    assert category is None or category in OPTIONAL_CATEGORIES, category
    recipients = sorted({a.strip() for a in ([to] if isinstance(to, str) else to)
                         if a and a.strip() and not _reserved(a)})
    if category:
        recipients = [a for a in recipients if not is_opted_out(a, category)]
    if not recipients or is_suppressed():
        return False
    s = IntegrationSettings.current()

    def render(addr):
        ctx = {'site_url': site_url(), **context}
        if category:
            ctx['unsubscribe_url'] = unsubscribe_url(addr, category)
            ctx['unsubscribe_label'] = OPTIONAL_CATEGORIES[category]
        text = render_to_string(f'emails/{template}.txt', ctx)
        if category:
            text += (f"\n--\nDon't want {ctx['unsubscribe_label']}? Unsubscribe: {ctx['unsubscribe_url']}\n"
                     f"Or change it in User Settings: {ctx['site_url']}{reverse('users:profile')}\n")
        return text, render_to_string(f'emails/{template}.html', ctx), ctx

    if not (s.sendgrid_api_key and s.email_from_address):
        log.info('Email not sent (SendGrid not configured): %r to %s', subject, recipients)
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, From, Header
        ok = True
        # One message per recipient so addresses aren't exposed to each other
        # (and each gets their own unsubscribe link).
        for addr in recipients:
            text, html, ctx = render(addr)
            msg = Mail(from_email=From(s.email_from_address, s.email_from_name or 'Kiboko'),
                       to_emails=addr, subject=subject, plain_text_content=text, html_content=html)
            if reply_to:
                msg.reply_to = reply_to
            if category:
                # RFC 8058 one-click unsubscribe (Gmail / Yahoo show an Unsubscribe button).
                msg.add_header(Header('List-Unsubscribe', f"<{ctx['unsubscribe_url']}>"))
                msg.add_header(Header('List-Unsubscribe-Post', 'List-Unsubscribe=One-Click'))
            resp = SendGridAPIClient(s.sendgrid_api_key).send(msg)
            ok = ok and 200 <= resp.status_code < 300
        return ok
    except Exception:
        log.exception('SendGrid send failed: %r to %s', subject, recipients)
        return False
