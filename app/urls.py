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
    path('work-in-progress/', views.work_in_progress, name='work_in_progress'),
    path('data-connection/', views.data_connection, name='data_connection'),
    # Analytics dashboards (Analytics == Grow Sales landing page)
    path('analytics/', views.analytics_grow_sales, name='analytics'),
    path('analytics/grow-sales/', views.analytics_grow_sales, name='analytics_grow_sales'),
    path('analytics/attract-traffic/', views.analytics_attract_traffic, name='analytics_attract_traffic'),
    path('analytics/engage-customers/', views.analytics_engage_customers, name='analytics_engage_customers'),
    path('analytics/expand-purchases/', views.analytics_expand_purchases, name='analytics_expand_purchases'),
    path('', views.index, name='index'),
]
