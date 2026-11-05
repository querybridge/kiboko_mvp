from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy

from . import views
from .forms import TrimmedAuthenticationForm, KibokoPasswordResetForm, KibokoSetPasswordForm

app_name = 'users'

urlpatterns = [
	#Login Page (trims whitespace so a copy-pasted temporary password still works)
	path('login/', LoginView.as_view(template_name='users/login.html',
	                                  authentication_form=TrimmedAuthenticationForm), name='login'),

	#Forgot password: request a link, then set a new password from it
	path('password-reset/', auth_views.PasswordResetView.as_view(
		template_name='users/password_reset.html', form_class=KibokoPasswordResetForm,
		success_url=reverse_lazy('users:password_reset_done')), name='password_reset'),
	path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(
		template_name='users/password_reset_done.html'), name='password_reset_done'),
	path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
		template_name='users/password_reset_confirm.html', form_class=KibokoSetPasswordForm,
		success_url=reverse_lazy('users:password_reset_complete')), name='password_reset_confirm'),
	path('password-reset/done/', auth_views.PasswordResetCompleteView.as_view(
		template_name='users/password_reset_complete.html'), name='password_reset_complete'),

	#Logout Function
	path('logout/', views.logout_view, name='logout'),

	#Registration Page
	path('register/', views.register, name='register'),

	#Public "Create a new account" / Get Started (self-serve trial signup)
	path('get-started/', views.get_started, name='get_started'),

	#User Settings (profile: change password + username)
	path('profile/', views.profile, name='profile'),
]
