import re
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pat', email='pat@example.org', password='old-pass-123!')

    def request_reset(self, email):
        with mock.patch('business_unit.email.send', return_value=True) as send:
            resp = self.client.post(reverse('users:password_reset'), {'email': email})
        return resp, send

    def test_login_page_links_to_reset_and_legal(self):
        html = self.client.get(reverse('users:login')).content.decode()
        self.assertIn(reverse('users:password_reset'), html)
        self.assertIn(reverse('legal_terms'), html)
        self.assertIn(reverse('legal_privacy'), html)

    def test_known_email_gets_a_working_link(self):
        resp, send = self.request_reset('PAT@example.org')
        self.assertRedirects(resp, reverse('users:password_reset_done'))
        send.assert_called_once()
        to, subject, template, ctx = send.call_args.args
        self.assertEqual((to, template), ('pat@example.org', 'password_reset'))
        path = re.sub(r'^https?://[^/]+', '', ctx['reset_url'])

        # Django swaps the token for a session marker, then shows the form.
        resp = self.client.get(path, follow=True)
        self.assertTrue(resp.context['validlink'])
        resp = self.client.post(resp.redirect_chain[-1][0],
                                {'new_password1': 'Fresh-pass-456!', 'new_password2': 'Fresh-pass-456!'})
        self.assertRedirects(resp, reverse('users:password_reset_complete'))
        self.assertTrue(self.client.login(username='pat', password='Fresh-pass-456!'))

    def test_unknown_email_looks_the_same_and_sends_nothing(self):
        resp, send = self.request_reset('nobody@example.org')
        self.assertRedirects(resp, reverse('users:password_reset_done'))
        send.assert_not_called()

    def test_google_only_account_gets_no_link(self):
        User.objects.create_user('gina', email='gina@example.org')  # no password = Google sign-in
        _, send = self.request_reset('gina@example.org')
        send.assert_not_called()

    def test_reset_clears_temporary_password_flag(self):
        self.user.profile.must_change_password = True
        self.user.profile.save()
        _, send = self.request_reset('pat@example.org')
        path = re.sub(r'^https?://[^/]+', '', send.call_args.args[3]['reset_url'])
        resp = self.client.get(path, follow=True)
        self.client.post(resp.redirect_chain[-1][0],
                         {'new_password1': 'Fresh-pass-456!', 'new_password2': 'Fresh-pass-456!'})
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.must_change_password)

    def test_bad_link_shows_expired_page(self):
        resp = self.client.get(reverse('users:password_reset_confirm',
                                       kwargs={'uidb64': 'MQ', 'token': 'bad-token'}))
        self.assertFalse(resp.context['validlink'])
        self.assertContains(resp, 'This link has expired')


class LegalPagesTests(TestCase):
    def test_public_when_signed_out(self):
        for name, heading in (('legal_privacy', 'Privacy Policy'), ('legal_terms', 'Terms of Service')):
            resp = self.client.get(reverse(name))
            self.assertContains(resp, f'<h1>{heading}</h1>')

    def test_open_to_users_who_must_change_password(self):
        user = User.objects.create_user('temp', password='temp-pass-123!')
        user.profile.must_change_password = True
        user.profile.save()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('legal_terms')).status_code, 200)
