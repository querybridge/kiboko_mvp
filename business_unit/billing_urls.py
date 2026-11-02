from django.urls import path

from . import billing_views

app_name = 'billing'

urlpatterns = [
    path('checkout/', billing_views.checkout, name='checkout'),
    path('portal/', billing_views.portal, name='portal'),
    path('stripe/webhook/', billing_views.webhook, name='stripe_webhook'),
]
