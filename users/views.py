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


SIGNUP_KEY = 'trial_signup'          # session: {'email', 'verified', 'code_id', 'tries', 'sent_at'}
CODE_TRIES = 5                        # wrong codes allowed before a new one is needed
RESEND_SECONDS = 60


def get_started(request):
    """Public "Create a new account" page: an email-first trial signup in three
    steps, each its own screen.

      1. Email   -- the person enters a work email; we email a one-time trial code.
      2. Verify  -- they enter the code. Proves the email before we ask for more.
      3. Set up  -- choose a plan and enter name, company and password. Creates the
                    User + Organization (45-day trial, no card) + Company, logs them
                    in, and drops them on the Getting Started checklist.

    Progress lives in the session, so a refresh or the back button keeps the step.
    Every POST redirects (post/redirect/get). Payment is added later on Billing.
    """
    import datetime
    from django.conf import settings
    from django.contrib import messages
    from django.contrib.auth import login
    from django.contrib.auth.models import User
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from django.db import transaction
    from django.utils import timezone
    from business_unit.models import Plan, Organization, Company, CompanyMembership, TrialCode
    from users.models import LEGAL_VERSION
    from business_unit import email as mail

    if request.user.is_authenticated:
        return redirect('app:getting_started')

    plans = list(Plan.objects.filter(active=True, is_addon=False).order_by('sort_order', 'price'))
    addon = Plan.objects.filter(active=True, is_addon=True).order_by('sort_order').first()
    valid_slugs = {p.slug for p in plans}
    default_slug = next((p.slug for p in plans if p.highlighted), plans[0].slug if plans else '')
    days = Organization.TRIAL_DAYS
    signup = request.session.get(SIGNUP_KEY) or {}
    here = reverse('users:get_started')

    def save(state):
        request.session[SIGNUP_KEY] = state
        request.session.modified = True

    def send_code(email, first_name=''):
        """Issue a code for `email` and email it. Returns True if it went out."""
        tc = TrialCode.issue(email)
        sent = mail.send(email, 'Your Kiboko trial code', 'trial_code',
                         {'code': tc.code, 'days': days, 'valid_days': TrialCode.VALID_DAYS,
                          'first_name': first_name})
        if not sent and settings.DEBUG:
            messages.warning(request, f'Email isn’t set up, so here is the code (development only): {tc.code}')
            sent = True
        if sent:
            save({'email': email, 'verified': False, 'code_id': None, 'tries': 0,
                  'sent_at': timezone.now().timestamp()})
        return sent

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'send_code':                                   # step 1
            email = (request.POST.get('email') or '').strip()
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, 'Enter a valid work email.')
                return redirect(here)
            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, 'An account with that email already exists. Sign in instead.')
                return redirect(here)
            if not send_code(email):
                messages.error(request, 'We couldn’t send the code just now. Please try again shortly.')
            return redirect(here)

        if action == 'change_email':
            request.session.pop(SIGNUP_KEY, None)
            return redirect(here)

        if action == 'resend' and signup.get('email') and not signup.get('verified'):
            wait = RESEND_SECONDS - (timezone.now().timestamp() - (signup.get('sent_at') or 0))
            if wait > 0:
                messages.info(request, f'Please wait {int(wait) + 1} seconds before asking for another code.')
            elif send_code(signup['email']):
                messages.success(request, f'We sent a new code to {signup["email"]}.')
            else:
                messages.error(request, 'We couldn’t send the code just now. Please try again shortly.')
            return redirect(here)

        if action == 'verify' and signup.get('email') and not signup.get('verified'):  # step 2
            tc = TrialCode.redeemable(signup['email'], request.POST.get('code'))
            if tc is None:
                signup['tries'] = signup.get('tries', 0) + 1
                if signup['tries'] >= CODE_TRIES:
                    TrialCode.objects.filter(email__iexact=signup['email'], used_at__isnull=True).update(
                        expires=timezone.now())
                    request.session.pop(SIGNUP_KEY, None)
                    messages.error(request, 'Too many incorrect codes. Enter your email to get a new one.')
                    return redirect(here)
                save(signup)
                messages.error(request, 'That code isn’t right or has expired. Check the latest email, or resend it.')
                return redirect(here)
            signup.update(verified=True, code_id=tc.id)
            save(signup)
            return redirect(here)

        if action == 'create' and signup.get('verified'):            # step 3
            form = {
                'first_name': (request.POST.get('first_name') or '').strip(),
                'last_name': (request.POST.get('last_name') or '').strip(),
                'company': (request.POST.get('company') or '').strip(),
                'plan': (request.POST.get('plan') or '').strip(),
                'premium_connection': bool(request.POST.get('premium_connection')),
            }
            password = request.POST.get('password') or ''
            confirm = request.POST.get('password_confirm') or ''
            email = signup['email']
            trial = TrialCode.objects.filter(pk=signup.get('code_id'), email__iexact=email,
                                             used_at__isnull=True).first()
            errors = []
            if trial is None or User.objects.filter(email__iexact=email).exists():
                request.session.pop(SIGNUP_KEY, None)
                messages.error(request, 'That trial code has already been used. Enter your email to start again.')
                return redirect(here)
            if not form['first_name'] or not form['last_name']:
                errors.append('Enter your first and last name.')
            if not form['company']:
                errors.append('Enter your company name.')
            if len(password) < 8:
                errors.append('Choose a password of at least 8 characters.')
            elif password != confirm:
                errors.append('The passwords do not match.')
            if form['plan'] not in valid_slugs:
                errors.append('Choose a plan.')
            if not request.POST.get('agree_terms'):
                errors.append('Agree to the Terms of Service and Privacy Policy to start your trial.')
            if errors:
                for e in errors:
                    messages.error(request, e)
                signup['form'] = form             # refill the step 3 fields (never the password)
                save(signup)
                return redirect(here)

            chosen = Plan.objects.get(slug=form['plan'])
            # Premium/Enterprise include the connection; the add-on only applies to Standard.
            premium_conn = form['premium_connection'] if chosen.tier == 'standard' else (chosen.tier != 'standard')
            today = datetime.date.today()
            with transaction.atomic():
                user = User.objects.create_user(
                    username=_signup_username(email), email=email,
                    password=password, first_name=form['first_name'], last_name=form['last_name'])
                org = Organization.objects.create(
                    name=form['company'], slug=_unique_slug(Organization, form['company']),
                    kind='direct', org_admin=user, plan=chosen,
                    premium_connection=premium_conn,
                    plan_status='trial', trial_started=today,
                    trial_ends=today + datetime.timedelta(days=days))
                company = Company.objects.create(
                    organization=org, name=form['company'],
                    slug=_unique_slug(Company, form['company']))
                CompanyMembership.objects.create(user=user, company=company, role='admin')
                user.profile.terms_accepted_at = timezone.now()
                user.profile.terms_version = LEGAL_VERSION
                user.profile.save(update_fields=['terms_accepted_at', 'terms_version'])
                trial.used_at = timezone.now()
                trial.organization = org
                trial.save(update_fields=['used_at', 'organization'])
            request.session.pop(SIGNUP_KEY, None)
            # No authenticate() call (we set the password directly), so name the backend.
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome to Kiboko! Your {days}-day {chosen.name} trial '
                                      'has started. Finish setup below. No card needed.')
            return redirect('app:getting_started')

        return redirect(here)

    step = 'details' if signup.get('verified') else ('verify' if signup.get('email') else 'email')
    form = {'first_name': '', 'last_name': '', 'company': '', 'plan': default_slug,
            'premium_connection': False, **(signup.get('form') or {})}
    return render(request, 'users/get_started.html', {
        'title': 'Get Started', 'step': step, 'email': signup.get('email', ''),
        'plans': plans, 'addon': addon, 'form': form, 'trial_days': days,
        'code_valid_days': TrialCode.VALID_DAYS,
        'steps': [('email', 'Your email'), ('verify', 'Verify'), ('details', 'Plan and details')],
    })


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
