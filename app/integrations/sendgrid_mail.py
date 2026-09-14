"""SendGrid email scaffolding. Config lives in the SendGridSettings model
(editable in Django admin); the API key is added there later. Until it's set,
send() returns (False, reason) without raising, so callers can degrade
gracefully (e.g. log feedback instead of losing it)."""
import json
import logging

logger = logging.getLogger(__name__)

_API_URL = 'https://api.sendgrid.com/v3/mail/send'


def get_settings():
    from app.models import SendGridSettings
    return SendGridSettings.current()


def is_configured():
    s = get_settings()
    return bool(s and s.is_configured)


def send(to_email, subject, body_text, reply_to=None):
    """Send a plaintext email via the SendGrid v3 API. Returns (ok, detail).
    No-op (False, ...) when unconfigured -- never raises."""
    s = get_settings()
    if not s or not s.is_configured:
        return False, 'SendGrid is not configured yet.'

    payload = {
        'personalizations': [{'to': [{'email': to_email}], 'subject': subject}],
        'from': {'email': s.from_email, 'name': s.from_name or 'Kiboko'},
        'content': [{'type': 'text/plain', 'value': body_text}],
    }
    if reply_to:
        payload['reply_to'] = {'email': reply_to}

    try:
        import requests
        resp = requests.post(
            _API_URL,
            headers={'Authorization': f'Bearer {s.api_key}', 'Content-Type': 'application/json'},
            data=json.dumps(payload), timeout=10)
        if resp.status_code in (200, 201, 202):
            return True, 'sent'
        logger.warning('SendGrid send failed (%s): %s', resp.status_code, resp.text[:300])
        return False, f'SendGrid error {resp.status_code}'
    except Exception as e:
        logger.warning('SendGrid send exception: %s: %s', type(e).__name__, e)
        return False, f'{type(e).__name__}: {e}'
