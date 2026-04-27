from django.urls import path
from . import views


app_name = 'project'

urlpatterns = [
    path('view.html', views.view, name='all'),
    path('add.html', views.project, name='project'),
    path('value.html', views.value, name='value'),
    path('loe.html', views.loe, name='loe'),
    path('approvals.html', views.approve, name='approvals'),
    path('archive/', views.archive, name='archive'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('kanban/move/', views.kanban_move, name='kanban_move'),
    #Project Detail Page
    path('<int:project_id>/', views.project_detail, name='project_detail'),
    path('<int:project_id>/edit/', views.project_edit, name='project_edit'),
    path('<int:project_id>/edit_manager/', views.project_edit_manager, name='project_edit_manager'),
    path('<int:project_id>/comment/', views.add_comment_to_project, name='add_comment_to_project'),
    path('<int:project_id>/approve/', views.approve_project, name='approve_project'),
    path('<int:project_id>/delete/', views.delete, name='delete_project'),
    path('<int:project_id>/value/', views.project_value, name='project_value'),
    path('<int:project_id>/loe/', views.project_loe, name='project_loe'),
]
