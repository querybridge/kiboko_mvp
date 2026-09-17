from django import forms
from django.contrib.auth.forms import (UserCreationForm, UserChangeForm,
                                       AuthenticationForm, PasswordChangeForm)
from django.contrib.auth.models import User

from users.models import ROLE_CHOICES


class TrimmedAuthenticationForm(AuthenticationForm):
    """Login form that trims surrounding whitespace from the username and password,
    so a copy-pasted temporary password with a stray space/newline still works."""
    def clean_username(self):
        return (self.cleaned_data.get('username') or '').strip()

    def clean_password(self):
        return (self.cleaned_data.get('password') or '').strip()


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
