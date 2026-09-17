from django.urls import path
from django.contrib.auth.views import LoginView

from . import views
from .forms import TrimmedAuthenticationForm

app_name = 'users'

urlpatterns = [
	#Login Page (trims whitespace so a copy-pasted temporary password still works)
	path('login/', LoginView.as_view(template_name='users/login.html',
	                                  authentication_form=TrimmedAuthenticationForm), name='login'),

	#Logout Function
	path('logout/', views.logout_view, name='logout'),

	#Registration Page
	path('register/', views.register, name='register'),

	#User Settings (profile: change password + username)
	path('profile/', views.profile, name='profile'),
]
