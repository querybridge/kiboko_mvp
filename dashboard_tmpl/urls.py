"""Kiboko URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import path, include
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from django.contrib import admin
from django.views.generic import RedirectView, TemplateView

from app import auth_views
from business_unit import email_views

urlpatterns = [
    path('admin/', admin.site.urls),
    # Home page -> the user's default home page (app.views.home)
    path('', RedirectView.as_view(url='/app/home/', permanent=False)),
    # Browsers ask for /favicon.ico directly (e.g. on non-HTML responses).
    path('favicon.ico', RedirectView.as_view(url='/static/images/kiboko-favicon.ico', permanent=True)),
    # Sign in with Google (callback path must match GOOGLE_OAUTH_REDIRECT_URI)
    path('auth/google/login/', auth_views.google_login, name='google_login'),
    path('auth/google/callback/', auth_views.google_callback, name='google_callback'),
    path('strategy/', include('strategy.urls', namespace='strategy')),
    path('project/', include('project.urls', namespace='project')),
    path('users/', include('users.urls', namespace='users')),
    path('app/', include('app.urls')),
    # Phone experience (phones are routed here by mobile.middleware)
    path('m/', include('mobile.urls', namespace='mobile')),
    # Public legal pages (open to signed-out and billing-locked users)
    path('legal/privacy/', TemplateView.as_view(template_name='legal/privacy.html'), name='legal_privacy'),
    path('legal/terms/', TemplateView.as_view(template_name='legal/terms.html'), name='legal_terms'),
    # Unsubscribe link in automatic emails (signed token; no login needed)
    path('email/unsubscribe/<str:token>/', email_views.unsubscribe, name='email_unsubscribe'),
    # Stripe: Checkout, Customer Portal, webhook (reachable while billing-locked)
    path('billing/', include('business_unit.billing_urls', namespace='billing')),
]
