"""Secrets are stored encrypted and read back as plain values."""
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import TestCase, override_settings

from business_unit import crypto
from business_unit.models import BigQueryConnection, Company, GoogleIdentity, IntegrationSettings, Organization


def raw(table, column, pk):
    with connection.cursor() as c:
        c.execute(f'SELECT {column} FROM {table} WHERE id = %s', [pk])
        return c.fetchone()[0]


class EncryptedFieldTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u', 'u@x.test', 'pw')
        org = Organization.objects.create(name='o', slug='o', org_admin=self.user)
        self.co = Company.objects.create(organization=org, name='Co', slug='co')

    def test_google_token_is_encrypted_in_the_database(self):
        gi = GoogleIdentity.objects.create(user=self.user, google_sub='s', email='u@x.test', refresh_token='1//tok')
        stored = raw('business_unit_googleidentity', 'refresh_token', gi.pk)
        self.assertTrue(stored.startswith(crypto.PREFIX))
        self.assertNotIn('1//tok', stored)
        self.assertEqual(GoogleIdentity.objects.get(pk=gi.pk).refresh_token, '1//tok')

    def test_bigquery_key_is_encrypted_and_reads_back_as_a_dict(self):
        key = {'type': 'service_account', 'private_key': '-----BEGIN PRIVATE KEY-----x'}
        bq = BigQueryConnection.objects.create(company=self.co, service_account_json=key)
        self.assertNotIn('PRIVATE KEY', raw('business_unit_bigqueryconnection', 'service_account_json', bq.pk))
        self.assertEqual(BigQueryConnection.objects.get(pk=bq.pk).service_account_json, key)
        self.assertEqual(BigQueryConnection.objects.exclude(service_account_json={}).count(), 1)

    def test_api_keys_are_encrypted(self):
        s = IntegrationSettings.current()
        s.stripe_secret_key = 'sk_test_abc'
        s.save()
        self.assertNotIn('sk_test', raw('business_unit_integrationsettings', 'stripe_secret_key', s.pk))
        self.assertEqual(IntegrationSettings.current().stripe_secret_key, 'sk_test_abc')

    def test_blank_stays_blank(self):
        gi = GoogleIdentity.objects.create(user=self.user, google_sub='s', email='u@x.test')
        self.assertEqual(raw('business_unit_googleidentity', 'refresh_token', gi.pk), '')
        self.assertEqual(GoogleIdentity.objects.get(pk=gi.pk).refresh_token, '')

    def test_legacy_plaintext_still_reads(self):
        self.assertEqual(crypto.decrypt('1//old-plain'), '1//old-plain')

    def test_rotation_keeps_old_values_readable(self):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        with override_settings(KIBOKO_ENCRYPTION_KEY=old):
            token = crypto.encrypt('secret')
        with override_settings(KIBOKO_ENCRYPTION_KEY=f'{new},{old}'):
            self.assertEqual(crypto.decrypt(token), 'secret')
        with override_settings(KIBOKO_ENCRYPTION_KEY=new):
            with self.assertRaises(ImproperlyConfigured):
                crypto.decrypt(token)
