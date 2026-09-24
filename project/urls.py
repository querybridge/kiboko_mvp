from django.urls import path
from . import views


app_name = 'project'

urlpatterns = [
    path('view.html', views.view, name='all'),
    path('add.html', views.project, name='project'),
    path('estimator-baseline/', views.estimator_baseline, name='estimator_baseline'),
    # Project Review
    path('completed/', views.completed_projects, name='completed_projects'),
    path('archive/', views.archive, name='archive'),
    path('<int:project_id>/archive/', views.archive_project, name='archive_project'),
    # Intake pipeline
    path('approve/', views.approve_projects, name='approve_projects'),
    path('executive-approval/', views.executive_approval, name='executive_approval'),
    path('<int:project_id>/approve-on-deck/', views.approve_on_deck, name='approve_on_deck'),
    path('<int:project_id>/approve-action/', views.approve_action, name='approve_action'),
    path('<int:project_id>/set-loe/', views.set_loe, name='set_loe'),
    path('<int:project_id>/analyst-review/', views.analyst_review, name='analyst_review'),
    path('<int:project_id>/set-analyst-review/', views.set_analyst_review, name='set_analyst_review'),
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
