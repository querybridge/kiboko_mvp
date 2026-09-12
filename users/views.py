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
