from django.urls import path
from . import views


app_name = 'project'

urlpatterns = [
    path('view.html', views.view, name='all'),
    path('add.html', views.project, name='project'),
    path('archive/', views.archive, name='archive'),
    # Intake pipeline
    path('approve/', views.approve_projects, name='approve_projects'),
    path('<int:project_id>/approve-action/', views.approve_action, name='approve_action'),
    path('<int:project_id>/set-revenue/', views.set_revenue, name='set_revenue'),
    path('<int:project_id>/set-loe/', views.set_loe, name='set_loe'),
    # Kanban
    path('kanban/', views.kanban_view, name='kanban'),
    path('kanban/move/', views.kanban_move, name='kanban_move'),
    # Project detail + execution tasks
    path('<int:project_id>/', views.project_detail, name='project_detail'),
    path('<int:project_id>/edit/', views.project_edit, name='project_edit'),
    path('<int:project_id>/add-action/', views.add_action, name='add_action'),
    path('<int:project_id>/comment/', views.add_comment_to_project, name='add_comment_to_project'),
    path('<int:project_id>/approve/', views.approve_project, name='approve_project'),
    path('<int:project_id>/delete/', views.delete, name='delete_project'),
]
