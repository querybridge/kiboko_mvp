"""Encryption at rest for secrets Kiboko stores: Google refresh tokens, BigQuery
service-account keys, and the SendGrid / Stripe keys in Integration Settings.

The key lives only in .env (KIBOKO_ENCRYPTION_KEY), never in the database, so a
copy of the database alone exposes nothing. Make one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

To rotate: put the new key first and keep the old one after it, comma-separated
(KIBOKO_ENCRYPTION_KEY=new,old), run `python manage.py reencrypt_secrets`, then
drop the old key. Losing the key means re-entering every secret (users reconnect
Google, admins re-paste BigQuery and API keys); nothing else is lost.
"""
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = 'enc1:'  # marks a stored value as encrypted; anything else is legacy plaintext


def _fernet():
    keys = [k.strip() for k in (getattr(settings, 'KIBOKO_ENCRYPTION_KEY', '') or '').split(',') if k.strip()]
    if not keys:
        raise ImproperlyConfigured('KIBOKO_ENCRYPTION_KEY is not set. Add it to .env in the project root.')
    try:
        return MultiFernet([Fernet(k) for k in keys])
    except ValueError as e:
        raise ImproperlyConfigured(f'KIBOKO_ENCRYPTION_KEY is not a valid Fernet key ({e}).')


def encrypt(text):
    if not text:
        return ''
    return PREFIX + _fernet().encrypt(text.encode()).decode()


def decrypt(stored):
    """Plaintext for a stored value. Values saved before encryption (no prefix)
    pass through unchanged until the migration or next save encrypts them."""
    if not stored or not stored.startswith(PREFIX):
        return stored or ''
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        raise ImproperlyConfigured('A stored secret could not be decrypted: KIBOKO_ENCRYPTION_KEY does not match '
                                   'the key it was saved with.')


class EncryptedTextField(models.TextField):
    """A text field stored encrypted. Reads and writes plain strings in Python;
    it can't be searched or filtered on except for blank/non-blank."""

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt(value) if value else ''


class EncryptedJSONField(models.TextField):
    """A JSON value (dict/list) stored encrypted as text."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default', dict)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        text = decrypt(value)
        return json.loads(text) if text else {}

    def to_python(self, value):
        if isinstance(value, str):
            return json.loads(value) if value.strip() else {}
        return value

    def get_prep_value(self, value):
        if value in (None, '', {}, []):
            return ''
        return encrypt(json.dumps(value))

    def value_to_string(self, obj):
        return json.dumps(self.value_from_object(obj))
