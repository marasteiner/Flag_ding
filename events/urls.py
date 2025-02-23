from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home page with overall standings
    path('', views.index, name='index'),

    # Custom login/logout using our views
    path('login/', views.CustomLoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.CustomLogoutView.as_view(next_page='/login/'), name='logout'),

    # Team URLs
    path('players/', views.players_view, name='players'),
    path('players/delete/<int:player_id>/', views.delete_player, name='delete_player'),
    path('tournaments/', views.tournaments_view, name='tournaments'),
    path('tournaments/apply/<int:tournament_id>/', views.apply_tournament, name='apply_tournament'),
    path('tournaments/detail/<int:tournament_id>/', views.tournament_detail, name='tournament_detail'),

    path('', views.index, name='index'),
    path('login/', views.CustomLoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),

     path('scorecard/', views.scorecard_home, name='scorecard_home'),
    path('scorecard/coin_toss/<int:game_id>/', views.scorecard_coin_toss, name='scorecard_coin_toss'),
    path('scorecard/live/<int:game_id>/', views.scorecard_live, name='scorecard_live'),
    path('scorecard/<int:game_id>/record_event/', views.record_score_event, name='record_score_event'),
    path('scorecard/<int:game_id>/switch_offense/', views.switch_offense, name='switch_offense'),
    path('api/scoreboard/<int:tournament_id>/', views.scoreboard_data, name='scoreboard_data'),
]
