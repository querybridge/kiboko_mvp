from django import forms
from django.contrib.auth.forms import (UserCreationForm, UserChangeForm,
                                       AuthenticationForm, PasswordChangeForm,
                                       PasswordResetForm, SetPasswordForm)
from django.contrib.auth.models import User
from django.urls import reverse

from users.models import ROLE_CHOICES


class TrimmedAuthenticationForm(AuthenticationForm):
    """Login form that trims surrounding whitespace from the username and password,
    so a copy-pasted temporary password with a stray space/newline still works."""
    def clean_username(self):
        return (self.cleaned_data.get('username') or '').strip()

    def clean_password(self):
        return (self.cleaned_data.get('password') or '').strip()


class KibokoPasswordResetForm(PasswordResetForm):
    """Sends the reset link through SendGrid (business_unit.email) instead of
    Django's mail backend. Accounts without a usable password (Google sign-in)
    are skipped by Django, so they never get a link."""
    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        from business_unit import email as mail
        path = reverse('users:password_reset_confirm',
                       kwargs={'uidb64': context['uid'], 'token': context['token']})
        mail.send(to_email, 'Reset your Kiboko password', 'password_reset', {
            'first_name': context['user'].first_name,
            'username': context['user'].get_username(),
            'reset_url': f"{context['protocol']}://{context['domain']}{path}",
        })


class KibokoSetPasswordForm(SetPasswordForm):
    """Setting a new password from the reset link also clears a pending
    'must change temporary password' flag."""
    def save(self, commit=True):
        user = super().save(commit)
        prof = getattr(user, 'profile', None)
        if commit and prof is not None and getattr(prof, 'must_change_password', False):
            prof.must_change_password = False
            prof.save(update_fields=['must_change_password'])
        return user


class TrimmedPasswordChangeForm(PasswordChangeForm):
    """Password-change form that trims the (often pasted) current password so a
    stray space/newline doesn't reject a valid temporary password."""
    def clean_old_password(self):
        old = (self.cleaned_data.get('old_password') or '').strip()
        if not self.user.check_password(old):
            raise forms.ValidationError(
                self.error_messages['password_incorrect'], code='password_incorrect')
        return old


class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    last_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    email = forms.EmailField(max_length=254, help_text='Required. Inform a valid email address.')
    role = forms.ChoiceField(choices=ROLE_CHOICES, initial='staff', label='Role')

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2', )
