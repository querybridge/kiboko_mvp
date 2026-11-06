from django.urls import path

from mobile import views

app_name = 'mobile'

urlpatterns = [
    path('', views.home, name='home'),
    path('start/', views.start, name='start'),
    path('forecast/', views.forecast, name='forecast'),
    path('approve/', views.approve, name='approve'),
    path('score/', views.score, name='score'),
    path('score/<int:project_id>/', views.score_project, name='score_project'),
    path('projects/', views.projects, name='projects'),
    path('projects/<int:project_id>/', views.project, name='project'),
    path('story/', views.story, name='story'),
    path('add/', views.add, name='add'),
]
