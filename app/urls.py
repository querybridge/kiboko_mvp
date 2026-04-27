from django.urls import path
from app import views

#ADDED TO IMPROVE ROUTING WITH USAGE OF DJANGO URL SYNTAX
app_name = 'app'

urlpatterns = [
    # The home page
    path('goals/', views.edit_goals, name='edit_goals'),
    path('actuals/', views.upload_actuals, name='upload_actuals'),
    path('company/', views.settings_company, name='settings_company'),
    path('rocks/', views.settings_rocks, name='settings_rocks'),
    path('measurements/', views.settings_measurements, name='settings_measurements'),
    path('users/', views.settings_users, name='settings_users'),
    path('help/', views.help_page, name='help'),
    path('', views.index, name='index'),
]
