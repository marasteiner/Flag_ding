from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('team/add/', views.admin_team_add, name='admin_team_add'),
    path('team/edit/<int:team_id>/', views.admin_team_edit, name='admin_team_edit'),
    path('team/<int:team_id>/players/', views.admin_team_players, name='admin_team_players'),
    path('team/<int:team_id>/player/add/', views.admin_player_add, name='admin_player_add'),
    path('player/edit/<int:player_id>/', views.admin_player_edit, name='admin_player_edit'),
    path('player/delete/<int:player_id>/', views.admin_player_delete, name='admin_player_delete'),
    path('tournaments/', views.admin_tournaments, name='admin_tournaments'),
    path('tournaments/create/', views.admin_tournament_create, name='admin_tournament_create'),
    path('tournaments/edit/<int:tournament_id>/', views.admin_tournament_edit, name='admin_tournament_edit'),
    path('tournaments/<int:tournament_id>/games/', views.admin_games, name='admin_games'),
    path('games/edit/<int:game_id>/', views.admin_game_edit, name='admin_game_edit'),
    path('applications/', views.admin_applications, name='admin_applications'),
    path('applications/approve/<int:application_id>/', views.approve_application, name='approve_application'),
    path('tournaments/<int:tournament_id>/detail/', views.admin_tournament_detail, name='admin_tournament_detail'),
    path('tournaments/<int:tournament_id>/create_schedule/', views.create_schedule, name='create_schedule'),
    path('tournaments/<int:tournament_id>/remove_team/<int:team_id>/', views.admin_tournament_remove_team, name='admin_tournament_remove_team'),
    path('games/update_score/<int:game_id>/', views.update_game_score, name='update_game_score'),
    path('officials/', views.admin_official_assignments, name='admin_official_assignments'),  # NEW

]
