from django.urls import path
from app import views

#ADDED TO IMPROVE ROUTING WITH USAGE OF DJANGO URL SYNTAX
app_name = 'app'

urlpatterns = [
    # The home page
    path('adl.html', views.adl, name='adl'),
    path('goals/', views.edit_goals, name='edit_goals'),
    path('actuals/', views.upload_actuals, name='upload_actuals'),
    path('settings/', views.settings, name='settings'),
    path('', views.index, name='index'),
]
