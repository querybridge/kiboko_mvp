from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from users.forms import UserRegistrationForm

# Create your views here.
@login_required
#Logout View
def logout_view(request):
	logout(request)
	# Send to the login page directly (no ?next=) so the next login honors
	# LOGIN_REDIRECT_URL (Grow Sales) rather than bouncing back here.
	return HttpResponseRedirect(reverse('users:login'))


#Registration Page — DISABLED. Kiboko is invite-only: accounts are created by an
# admin (Manage Users) or provisioned when a user signs in with Google. Self-serve
# password signup bypassed org/company assignment, so it's turned off.
def register(request):
    from django.contrib import messages
    messages.info(request, 'Registration is by invitation. Ask your admin to add you, '
                           'or sign in with Google.')
    return redirect('users:login')


@login_required
def profile(request):
    """User Settings — change password and username. Also the landing page when a
    temporary-password account must set its own password on first login."""
    from django.contrib import messages
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.models import User
    from users.forms import TrimmedPasswordChangeForm as PwForm

    prof = getattr(request.user, 'profile', None)
    must_change = bool(prof and prof.must_change_password)
    pw_form = PwForm(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_password':
            pw_form = PwForm(request.user, request.POST)
            if pw_form.is_valid():
                user = pw_form.save()
                update_session_auth_hash(request, user)          # stay logged in
                if prof and prof.must_change_password:
                    prof.must_change_password = False
                    prof.save(update_fields=['must_change_password'])
                messages.success(request, 'Password updated.')
                return redirect('users:profile')
            messages.error(request, 'Could not update the password — see below.')
        elif action == 'change_username':
            new = (request.POST.get('username') or '').strip()
            if not new:
                messages.error(request, 'Enter a username.')
            elif new == request.user.username:
                messages.info(request, 'That is already your username.')
            elif User.objects.filter(username__iexact=new).exclude(pk=request.user.pk).exists():
                messages.error(request, 'That username is taken.')
            else:
                request.user.username = new[:150]
                request.user.save(update_fields=['username'])
                messages.success(request, 'Username updated.')
                return redirect('users:profile')
        elif action == 'set_lander':
            from users.models import LANDER_CHOICES
            valid = {k for k, _ in LANDER_CHOICES}
            choice = (request.POST.get('default_lander') or '').strip()
            if prof is not None and choice in valid:
                prof.default_lander = choice
                prof.save(update_fields=['default_lander'])
                messages.success(request, 'Landing page updated.')
                return redirect('users:profile')
            messages.error(request, 'Pick a valid landing page.')

    from users.models import LANDER_CHOICES
    for f in pw_form.fields.values():
        f.widget.attrs['class'] = 'form-control'
    return render(request, 'users/profile.html', {
        'title': 'User Settings', 'pw_form': pw_form, 'must_change': must_change,
        'lander_choices': LANDER_CHOICES,
        'current_lander': (prof.default_lander if prof else ''),
        'resolved_lander': (prof.resolved_lander_key() if prof else 'pipeline')})
