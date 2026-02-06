from django.urls import path
from . import views

#Import Tables

app_name = 'strategy'

urlpatterns = [
    path('<int:strategy_id>/', views.strategy_detail, name='strategy_detail'),
    path('<int:strategy_id>/edit/', views.strategy_edit, name='strategy_edit'),
    path('<int:strategy_id>/comment/', views.add_comment_to_strategy, name='add_comment_to_strategy'),
    path('view.html', views.strategy_view, name='strategy_view'),
    path('add.html', views.strategy, name='strategy'),
    path('rocks/', views.edit_rocks, name='edit_rocks'),
    path('measurement/', views.measurement, name='measurement'),
]
