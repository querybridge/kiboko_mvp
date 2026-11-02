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


def _signup_username(email):
    """Login = the part before '@' in the email, sanitized and made unique.
    Mirrors app.views._gen_username so admin-created and self-serve accounts
    derive usernames the same way."""
    from django.contrib.auth.models import User
    local = (email.split('@')[0] or '').lower()
    base = ''.join(ch for ch in local if ch.isalnum() or ch in '._-') or 'user'
    base = base[:150]
    username, i = base, 1
    while User.objects.filter(username__iexact=username).exists():
        i += 1
        username = f'{base[:150 - len(str(i))]}{i}'
    return username


def _unique_slug(model, value):
    """A unique slug for `model` derived from `value`."""
    from django.utils.text import slugify
    base = slugify(value)[:180] or 'org'
    slug, i = base, 1
    while model.objects.filter(slug=slug).exists():
        i += 1
        slug = f'{base[:180]}-{i}'
    return slug


def get_started(request):
    """Public "Create a new account" page: describes the onboarding steps,
    shows the pricing/plan table, and takes a self-serve trial signup.

    A trial needs a code: the person enters their email, we send a one-time trial
    code (SendGrid), and they enter it with the rest of the form. Submitting
    creates the User + Organization (45-day trial, no card) + Company, records the
    chosen plan, logs the person in, and drops them on the Getting Started
    checklist. Payment is added later on the Billing page (Stripe).
    """
    import datetime
    from django.contrib import messages
    from django.contrib.auth import login
    from django.utils import timezone
    from django.contrib.auth.models import User
    from django.db import transaction
    from business_unit.models import Plan, Organization, Company, CompanyMembership, TrialCode
    from business_unit import email as mail

    if request.user.is_authenticated:
        return redirect('app:getting_started')

    plans = list(Plan.objects.filter(active=True, is_addon=False).order_by('sort_order', 'price'))
    addon = Plan.objects.filter(active=True, is_addon=True).order_by('sort_order').first()
    valid_slugs = {p.slug for p in plans}
    default_slug = next((p.slug for p in plans if p.highlighted), plans[0].slug if plans else '')

    # Onboarding steps described on the page (mirrors the logged-in checklist).
    steps = [
        {'label': 'Create your account', 'desc': 'Tell us who you are and name your company.'},
        {'label': 'Choose a plan', 'desc': f'Pick Standard, Premium, or Enterprise. We email you a trial code for a {Organization.TRIAL_DAYS}-day free trial — no card needed.'},
        {'label': 'Connect your data', 'desc': 'Link GA4 (Standard) or a BigQuery service account (Premium Connection).'},
        {'label': 'Invite your team', 'desc': 'Add teammates and set each one’s role and business units.'},
        {'label': 'Set your budget & go', 'desc': 'Enter monthly revenue targets and start prioritizing the work that moves revenue.'},
    ]

    form = {'first_name': '', 'last_name': '', 'email': '', 'company': '',
            'plan': default_slug, 'premium_connection': False, 'trial_code': ''}
    code_sent = False

    if request.method == 'POST':
        form = {
            'first_name': (request.POST.get('first_name') or '').strip(),
            'last_name': (request.POST.get('last_name') or '').strip(),
            'email': (request.POST.get('email') or '').strip(),
            'company': (request.POST.get('company') or '').strip(),
            'plan': (request.POST.get('plan') or '').strip(),
            'premium_connection': bool(request.POST.get('premium_connection')),
            'trial_code': (request.POST.get('trial_code') or '').strip().upper(),
        }
        password = request.POST.get('password') or ''

        if request.POST.get('action') == 'send_code':
            email = form['email']
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, 'Enter a valid work email to receive your trial code.')
                email = ''
            if email and User.objects.filter(email__iexact=email).exists():
                messages.error(request, 'An account with that email already exists — try signing in instead.')
            elif email:
                tc = TrialCode.issue(email)
                sent = mail.send(email, 'Your Kiboko trial code', 'trial_code',
                                 {'code': tc.code, 'days': Organization.TRIAL_DAYS,
                                  'valid_days': TrialCode.VALID_DAYS, 'first_name': form['first_name']})
                if sent:
                    code_sent = True
                    messages.success(request, f'We emailed a trial code to {email}. Enter it below to start your trial.')
                else:
                    from django.conf import settings
                    if settings.DEBUG:
                        code_sent = True
                        messages.warning(request, f'Email isn’t set up, so here is the code (development only): {tc.code}')
                    else:
                        messages.error(request, 'We couldn’t send the trial code just now. Please try again shortly.')
            return render(request, 'users/get_started.html', {
                'title': 'Get Started', 'plans': plans, 'addon': addon, 'steps': steps,
                'form': form, 'default_slug': default_slug, 'code_sent': code_sent,
                'trial_days': Organization.TRIAL_DAYS})
        confirm = request.POST.get('password_confirm') or ''

        errors = []
        if not form['first_name'] or not form['last_name']:
            errors.append('Enter your first and last name.')
        if not form['email']:
            errors.append('Enter a work email.')
        elif User.objects.filter(email__iexact=form['email']).exists() or \
                User.objects.filter(username__iexact=form['email']).exists():
            errors.append('An account with that email already exists — try signing in instead.')
        if not form['company']:
            errors.append('Enter your company name.')
        if len(password) < 8:
            errors.append('Choose a password of at least 8 characters.')
        elif password != confirm:
            errors.append('The passwords do not match.')
        if form['plan'] not in valid_slugs:
            errors.append('Choose a plan.')
        trial = TrialCode.redeemable(form['email'], form['trial_code']) if form['email'] else None
        if not form['trial_code']:
            errors.append('Enter the trial code we emailed you (use “Email me a trial code”).')
        elif trial is None:
            errors.append('That trial code isn’t valid for this email, or it has expired. Request a new one.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            chosen = Plan.objects.get(slug=form['plan'])
            # Premium/Enterprise include the connection; the add-on only applies to Standard.
            premium_conn = form['premium_connection'] if chosen.tier == 'standard' else (chosen.tier != 'standard')
            with transaction.atomic():
                user = User.objects.create_user(
                    username=_signup_username(form['email']), email=form['email'],
                    password=password, first_name=form['first_name'], last_name=form['last_name'])
                org = Organization.objects.create(
                    name=form['company'], slug=_unique_slug(Organization, form['company']),
                    kind='direct', org_admin=user, plan=chosen,
                    premium_connection=premium_conn,
                    plan_status='trial', trial_started=datetime.date.today(),
                    trial_ends=datetime.date.today() + datetime.timedelta(days=Organization.TRIAL_DAYS))
                trial.used_at = timezone.now()
                trial.organization = org
                trial.save(update_fields=['used_at', 'organization'])
                company = Company.objects.create(
                    organization=org, name=form['company'],
                    slug=_unique_slug(Company, form['company']))
                CompanyMembership.objects.create(user=user, company=company, role='admin')
            # No authenticate() call (we set the password directly), so name the backend.
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome to Kiboko! Your {Organization.TRIAL_DAYS}-day {chosen.name} trial '
                                      'has started. Finish setup below — no card needed.')
            return redirect('app:getting_started')

    return render(request, 'users/get_started.html', {
        'title': 'Get Started', 'plans': plans, 'addon': addon, 'steps': steps,
        'form': form, 'default_slug': default_slug, 'code_sent': code_sent,
        'trial_days': Organization.TRIAL_DAYS})


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
