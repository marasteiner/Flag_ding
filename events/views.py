import random
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from .models import (
    Player,
    Tournament,
    TournamentApplication,
    Game,
    ScoreEvent,  # For the live scorecard feature
)
from .forms import (
    GameForm,
    PlayerForm,
    AdminTeamCreationForm,
    AdminTeamEditForm,
    AddTeamToTournamentForm,
)

# -----------------------------------------
# Helper decorator for admin-only views
# -----------------------------------------
def admin_required(view_func):
    decorated_view_func = login_required(user_passes_test(lambda u: u.is_staff)(view_func))
    return decorated_view_func

# -----------------------------------------
# Utility functions for standings
# -----------------------------------------
FINAL_POINTS_MAPPING = {
    3: [6, 4, 2],
    4: [8, 6, 4, 2],
    5: [9, 7, 5, 3, 2],
}

def compute_tournament_standings(tournament):
    """
    Compute raw points for each team in a tournament based on final game scores,
    then assign final points from a mapping if the tournament has 3, 4, or 5 teams.
    """
    apps = TournamentApplication.objects.filter(tournament=tournament, approved=True)
    teams = {app.team: 0 for app in apps}
    # Only count games where both scores are set
    games = tournament.games.filter(team1_score__isnull=False, team2_score__isnull=False)
    for game in games:
        if game.team1 in teams:
            if game.team1_score > game.team2_score:
                teams[game.team1] += 2
            elif game.team1_score == game.team2_score:
                teams[game.team1] += 1
        if game.team2 in teams:
            if game.team2_score > game.team1_score:
                teams[game.team2] += 2
            elif game.team2_score == game.team1_score:
                teams[game.team2] += 1

    # Sort teams by raw points desc, then username
    sorted_teams = sorted(teams.items(), key=lambda x: (-x[1], x[0].username))
    n = len(sorted_teams)
    mapping = FINAL_POINTS_MAPPING.get(n)
    standings = []
    if mapping:
        for rank, (team, raw_points) in enumerate(sorted_teams, start=1):
            final_points = mapping[rank-1]
            standings.append({
                'team': team,
                'raw_points': raw_points,
                'final_points': final_points,
                'rank': rank,
            })
    else:
        # If number of teams isn't 3,4,5, just store raw points
        for rank, (team, raw_points) in enumerate(sorted_teams, start=1):
            standings.append({
                'team': team,
                'raw_points': raw_points,
                'final_points': None,
                'rank': rank,
            })
    return standings

def compute_overall_standings():
    """
    Compute overall final points across all tournaments for each team.
    """
    overall = {}
    tournaments = Tournament.objects.all()
    for tournament in tournaments:
        stands = compute_tournament_standings(tournament)
        for entry in stands:
            team = entry['team']
            pts = entry['final_points'] or 0
            overall[team] = overall.get(team, 0) + pts
    # Sort by descending total_final_points, then username
    sorted_overall = sorted(overall.items(), key=lambda x: (-x[1], x[0].username))
    return [
        {'team': team, 'total_final_points': pts}
        for team, pts in sorted_overall
    ]

# -----------------------------------------
# Custom Login/Logout Views
# -----------------------------------------
class CustomLoginView(LoginView):
    def get_success_url(self):
        # After login, redirect all users (admin or team) to home page "/"
        return '/'

class CustomLogoutView(LogoutView):
    http_method_names = ['get', 'post']
    def get_next_page(self):
        # Always redirect to home page "/" after logout
        return '/'

# -----------------------------------------
# Team (non-admin) Views
# -----------------------------------------
@login_required
def players_view(request):
    """
    Allows a non-admin user to manage their players.
    """
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot access team player management.")
    if request.method == 'POST':
        trikot = request.POST.get('trikot')
        vorname = request.POST.get('vorname')
        nachname = request.POST.get('nachname')
        passnummer = request.POST.get('passnummer')
        if trikot and vorname and nachname and passnummer:
            Player.objects.create(
                team=request.user,
                trikot=trikot,
                vorname=vorname,
                nachname=nachname,
                passnummer=passnummer
            )
            return redirect('players')
    players = Player.objects.filter(team=request.user)
    return render(request, 'players.html', {'players': players})

@login_required
def delete_player(request, player_id):
    """
    Allows a non-admin user to delete one of their players.
    """
    player = get_object_or_404(Player, id=player_id)
    if player.team != request.user:
        return HttpResponseForbidden("You cannot delete this player.")
    player.delete()
    return redirect('players')

@login_required
def tournaments_view(request):
    """
    Lists all tournaments for a non-admin user, showing their application status.
    """
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot access team tournament page.")
    tournaments = Tournament.objects.all()
    applications = TournamentApplication.objects.filter(team=request.user)
    app_status = {app.tournament.id: app for app in applications}
    return render(request, 'tournaments.html', {'tournaments': tournaments, 'app_status': app_status})

@login_required
def apply_tournament(request, tournament_id):
    """
    A non-admin user can apply to a tournament (creates a TournamentApplication).
    """
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot apply for tournaments.")
    tournament = get_object_or_404(Tournament, id=tournament_id)
    TournamentApplication.objects.get_or_create(team=request.user, tournament=tournament)
    return redirect('tournaments')

@login_required
def tournament_detail(request, tournament_id):
    """
    Shows the schedule and final standings for a given tournament (non-admin view).
    """
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot access team tournament detail page.")
    tournament = get_object_or_404(Tournament, id=tournament_id)
    games = tournament.games.all().order_by('start_time')
    standings = compute_tournament_standings(tournament)
    return render(request, 'tournament_detail.html', {
        'tournament': tournament,
        'games': games,
        'standings': standings,
    })

def index(request):
    """
    Public home page: lists all tournaments and displays the overall standings table.
    """
    tournaments = Tournament.objects.all()
    overall_standings = compute_overall_standings()
    return render(request, 'index.html', {
        'tournaments': tournaments,
        'overall_standings': overall_standings,
    })

# -----------------------------------------
# Scorecard Flow (for referees)
# -----------------------------------------
@login_required
def scorecard_home(request):
    """
    Lists tournaments where the user is approved. Then shows games where user is the referee.
    """
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot use the team scorecard.")
    approved_apps = TournamentApplication.objects.filter(team=request.user, approved=True)
    approved_tournaments = [app.tournament for app in approved_apps]

    selected_tournament_id = request.GET.get('tournament_id')
    selected_tournament = None
    referee_games = []
    if selected_tournament_id:
        selected_tournament = get_object_or_404(Tournament, id=selected_tournament_id)
        referee_games = Game.objects.filter(tournament=selected_tournament, referee=request.user)

    return render(request, 'scorecard_home.html', {
        'approved_tournaments': approved_tournaments,
        'selected_tournament': selected_tournament,
        'referee_games': referee_games,
    })

@login_required
def scorecard_coin_toss(request, game_id):
    """
    Page to handle coin toss result and who starts on offense.
    """
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    if request.method == 'POST':
        coin_toss_winner = request.POST.get('coin_toss_winner')  # "team1" or "team2"
        offense = request.POST.get('offense')  # "team1" or "team2"
        game.coin_toss_winner_is_team1 = (coin_toss_winner == 'team1')
        game.offense_is_team1 = (offense == 'team1')
        game.save()
        return redirect('scorecard_live', game_id=game.id)
    return render(request, 'scorecard_coin_toss.html', {'game': game})

@login_required
def scorecard_live(request, game_id):
    """
    The main scoreboard page for referees: displays current score, which team is on offense,
    and buttons for Touchdown, PAT, Safety, etc. We store events in ScoreEvent.
    """
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    return render(request, 'scorecard_live.html', {'game': game})

@login_required
def record_score_event(request, game_id):
    """
    Receives POST data for a scoring event, updates ScoreEvent, updates Game scores accordingly.
    """
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    if request.method == 'POST':
        event_type = request.POST.get('event_type')  # "TD", "PAT1", "PAT2", "SAFETY"
        trikot_str = request.POST.get('trikot')
        trikot_num = None
        try:
            trikot_num = int(trikot_str) if trikot_str else None
        except ValueError:
            pass

        offense_is_team1 = game.offense_is_team1
        points_awarded = 0

        if event_type == 'TD':
            # 6 points to offense
            points_awarded = 6
        elif event_type == 'PAT1':
            # 1 point to offense
            points_awarded = 1
        elif event_type == 'PAT2':
            # 2 points to offense
            points_awarded = 2
        elif event_type == 'SAFETY':
            # 2 points for the defense
            offense_is_team1 = not offense_is_team1
            points_awarded = 2

        # Create ScoreEvent
        ScoreEvent.objects.create(
            game=game,
            event_type=event_type,
            trikot=trikot_num,
            points_awarded=points_awarded,
        )

        # Update the actual game scores
        if event_type == 'SAFETY':
            # awarding to the defense
            if offense_is_team1:
                if game.team1_score is None:
                    game.team1_score = 0
                game.team1_score += points_awarded
            else:
                if game.team2_score is None:
                    game.team2_score = 0
                game.team2_score += points_awarded
        else:
            # awarding to the offense
            if offense_is_team1:
                if game.team1_score is None:
                    game.team1_score = 0
                game.team1_score += points_awarded
            else:
                if game.team2_score is None:
                    game.team2_score = 0
                game.team2_score += points_awarded

        game.save()
        messages.success(request, f"Event {event_type} recorded with trikot {trikot_num}.")
    return redirect('scorecard_live', game_id=game.id)

@login_required
def switch_offense(request, game_id):
    """
    Toggle which team is on offense.
    """
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    game.offense_is_team1 = not game.offense_is_team1
    game.save()
    return redirect('scorecard_live', game_id=game.id)

def scoreboard_data(request, tournament_id):
    """
    Returns JSON of the scoreboard for all games in a tournament. For auto-refresh on home screen.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    games = tournament.games.all().order_by('start_time')
    data = []
    for g in games:
        data.append({
            'id': g.id,
            'team1': g.team1.username,
            'team2': g.team2.username,
            'score1': g.team1_score if g.team1_score is not None else 0,
            'score2': g.team2_score if g.team2_score is not None else 0,
            'start_time': g.start_time.strftime('%H:%M'),
        })
    return JsonResponse({'games': data})

# -----------------------------------------
# Admin (staff) Views
# -----------------------------------------
@admin_required
def admin_dashboard(request):
    teams = User.objects.filter(is_staff=False)
    return render(request, 'admin_dashboard.html', {'teams': teams})

@admin_required
def admin_team_add(request):
    if request.method == 'POST':
        form = AdminTeamCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Team created successfully.")
            return redirect('admin_dashboard')
    else:
        form = AdminTeamCreationForm()
    return render(request, 'admin_team_add.html', {'form': form})

@admin_required
def admin_team_edit(request, team_id):
    team = get_object_or_404(User, id=team_id, is_staff=False)
    if request.method == 'POST':
        form = AdminTeamEditForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, "Team updated successfully.")
            return redirect('admin_dashboard')
    else:
        form = AdminTeamEditForm(instance=team, initial={'team_name': team.first_name})
    return render(request, 'admin_team_edit.html', {'form': form, 'team': team})

@admin_required
def admin_tournaments(request):
    """
    Renders a list of all tournaments and the overall standings table,
    with no inline creation form. There's a link to create a new tournament
    on a separate page.
    """
    tournaments = Tournament.objects.all()
    overall_standings = compute_overall_standings()
    return render(request, 'admin_tournaments.html', {
        'tournaments': tournaments,
        'overall_standings': overall_standings,
    })

@admin_required
def admin_tournament_create(request):
    """
    Shows a separate page for creating a new tournament.
    After successful POST, redirects back to /custom_admin/tournaments/.
    """
    if request.method == 'POST':
        date = request.POST.get('date')
        name = request.POST.get('name')
        location = request.POST.get('location')
        max_teams = request.POST.get('max_teams')
        number_of_teams = request.POST.get('number_of_teams')
        if date and name and location and max_teams and number_of_teams:
            Tournament.objects.create(
                date=date,
                name=name,
                location=location,
                max_teams=max_teams,
                number_of_teams=number_of_teams
            )
            messages.success(request, "Tournament created successfully.")
            return redirect('admin_tournaments')
    return render(request, 'admin_tournament_form.html', {'action': 'Create'})

@admin_required
def admin_tournament_edit(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if request.method == 'POST':
        if 'edit_tournament' in request.POST:
            date = request.POST.get('date')
            name = request.POST.get('name')
            location = request.POST.get('location')
            max_teams = request.POST.get('max_teams')
            number_of_teams = request.POST.get('number_of_teams')
            if date and name and location and max_teams and number_of_teams:
                tournament.date = date
                tournament.name = name
                tournament.location = location
                tournament.max_teams = max_teams
                tournament.number_of_teams = number_of_teams
                tournament.save()
                messages.success(request, "Tournament updated successfully.")
                return redirect('admin_tournaments')
        elif 'add_team_submit' in request.POST:
            add_team_form = AddTeamToTournamentForm(request.POST, tournament=tournament)
            if add_team_form.is_valid():
                team = add_team_form.cleaned_data['team']
                TournamentApplication.objects.create(team=team, tournament=tournament, approved=True)
                messages.success(request, f"Team {team.username} added to tournament.")
                return redirect('admin_tournament_edit', tournament_id=tournament.id)
    else:
        add_team_form = AddTeamToTournamentForm(tournament=tournament)
    participating_apps = TournamentApplication.objects.filter(tournament=tournament)
    return render(request, 'admin_tournament_form.html', {
        'action': 'Edit',
        'tournament': tournament,
        'add_team_form': add_team_form,
        'participating_apps': participating_apps,
    })

@admin_required
def admin_tournament_remove_team(request, tournament_id, team_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    app = get_object_or_404(TournamentApplication, tournament=tournament, team__id=team_id)
    app.delete()
    messages.success(request, "Team removed from tournament.")
    return redirect('admin_tournament_edit', tournament_id=tournament.id)

@admin_required
def admin_applications(request):
    applications = TournamentApplication.objects.all().order_by('-applied_at')
    return render(request, 'admin_applications.html', {'applications': applications})

@admin_required
def approve_application(request, application_id):
    application = get_object_or_404(TournamentApplication, id=application_id)
    application.approved = True
    application.save()
    return redirect('admin_applications')

@admin_required
def admin_games(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    games = tournament.games.all().order_by('start_time')
    if request.method == 'POST' and 'add_game' in request.POST:
        form = GameForm(request.POST, tournament=tournament)
        if form.is_valid():
            game = form.save(commit=False)
            game.tournament = tournament
            game.save()
            messages.success(request, "Game added successfully.")
            return redirect('admin_games', tournament_id=tournament.id)
    else:
        form = GameForm(tournament=tournament)
    standings = compute_tournament_standings(tournament)
    return render(request, 'admin_games.html', {
        'tournament': tournament,
        'games': games,
        'form': form,
        'standings': standings,
    })

@admin_required
def admin_game_edit(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    tournament = game.tournament
    if request.method == 'POST':
        form = GameForm(request.POST, instance=game, tournament=tournament)
        if form.is_valid():
            form.save()
            messages.success(request, "Game updated successfully.")
            return redirect('admin_games', tournament_id=tournament.id)
    else:
        form = GameForm(instance=game, tournament=tournament)
    return render(request, 'admin_game_edit.html', {'form': form, 'game': game, 'tournament': tournament})

@admin_required
def update_game_score(request, game_id):
    """
    For admin's manual updating of scores, if needed.
    """
    game = get_object_or_404(Game, id=game_id)
    if request.method == 'POST':
        team1_score = request.POST.get('team1_score')
        team2_score = request.POST.get('team2_score')
        try:
            game.team1_score = int(team1_score) if team1_score.strip() != "" else None
            game.team2_score = int(team2_score) if team2_score.strip() != "" else None
            game.save()
            messages.success(request, "Game score updated successfully.")
        except ValueError:
            messages.error(request, "Invalid score value.")
    return redirect('admin_games', tournament_id=game.tournament.id)

@admin_required
def admin_tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    games = tournament.games.all().order_by('start_time')
    approved_apps = TournamentApplication.objects.filter(tournament=tournament, approved=True)
    teams = [app.team for app in approved_apps]
    standings = compute_tournament_standings(tournament)
    return render(request, 'admin_tournament_detail.html', {
        'tournament': tournament,
        'games': games,
        'teams': teams,
        'standings': standings,
    })

@admin_required
def create_schedule(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    approved_apps = TournamentApplication.objects.filter(tournament=tournament, approved=True)
    teams = [app.team for app in approved_apps]
    count = len(teams)
    if count not in [3, 4, 5]:
        messages.error(request, "Schedule can only be created for tournaments with exactly 3, 4, or 5 approved teams.")
        return redirect('admin_tournament_detail', tournament_id=tournament.id)
    random.shuffle(teams)
    tournament.games.all().delete()
    today = datetime.today().date()
    if count in [3, 4]:
        times = ["10:00", "11:10", "12:20", "13:30", "14:40", "15:50"]
        if count == 3:
            pattern = [
                {"team_a": 0, "team_b": 1, "ref": 2},
                {"team_a": 0, "team_b": 2, "ref": 1},
                {"team_a": 2, "team_b": 1, "ref": 0},
                {"team_a": 1, "team_b": 0, "ref": 2},
                {"team_a": 2, "team_b": 0, "ref": 1},
                {"team_a": 1, "team_b": 2, "ref": 0},
            ]
        else:
            pattern = [
                {"team_a": 0, "team_b": 1, "ref": 3},
                {"team_a": 3, "team_b": 2, "ref": 0},
                {"team_a": 2, "team_b": 0, "ref": 1},
                {"team_a": 1, "team_b": 3, "ref": 2},
                {"team_a": 2, "team_b": 1, "ref": 3},
                {"team_a": 0, "team_b": 3, "ref": 1},
            ]
        for i, game_def in enumerate(pattern):
            game_time = datetime.strptime(times[i], "%H:%M").time()
            game_datetime = datetime.combine(today, game_time)
            Game.objects.create(
                tournament=tournament,
                team1=teams[game_def["team_a"]],
                team2=teams[game_def["team_b"]],
                referee=teams[game_def["ref"]],
                start_time=game_datetime
            )
    elif count == 5:
        times = ["10:00", "11:10", "12:20", "13:30", "14:40"]
        pattern_field1 = [
            {"team_a": 0, "team_b": 1, "ref": 4},
            {"team_a": 2, "team_b": 0, "ref": 3},
            {"team_a": 4, "team_b": 2, "ref": 1},
            {"team_a": 3, "team_b": 1, "ref": 2},
            {"team_a": 3, "team_b": 4, "ref": 0},
        ]
        pattern_field2 = [
            {"team_a": 2, "team_b": 3, "ref": 4},
            {"team_a": 1, "team_b": 4, "ref": 3},
            {"team_a": 0, "team_b": 3, "ref": 1},
            {"team_a": 4, "team_b": 0, "ref": 2},
            {"team_a": 1, "team_b": 2, "ref": 0},
        ]
        for i, game_def in enumerate(pattern_field1):
            game_time = datetime.strptime(times[i], "%H:%M").time()
            game_datetime = datetime.combine(today, game_time)
            Game.objects.create(
                tournament=tournament,
                team1=teams[game_def["team_a"]],
                team2=teams[game_def["team_b"]],
                referee=teams[game_def["ref"]],
                start_time=game_datetime,
                field_number=1
            )
        for i, game_def in enumerate(pattern_field2):
            game_time = datetime.strptime(times[i], "%H:%M").time()
            game_datetime = datetime.combine(today, game_time)
            Game.objects.create(
                tournament=tournament,
                team1=teams[game_def["team_a"]],
                team2=teams[game_def["team_b"]],
                referee=teams[game_def["ref"]],
                start_time=game_datetime,
                field_number=2
            )
    messages.success(request, "Schedule created successfully.")
    return redirect('admin_tournament_detail', tournament_id=tournament.id)


@admin_required
def admin_team_players(request, team_id):
    team = get_object_or_404(User, id=team_id, is_staff=False)
    players = team.players.all()
    return render(request, 'admin_team_players.html', {'team': team, 'players': players})

@admin_required
def admin_player_add(request, team_id):
    team = get_object_or_404(User, id=team_id, is_staff=False)
    if request.method == 'POST':
        form = PlayerForm(request.POST)
        if form.is_valid():
            player = form.save(commit=False)
            player.team = team
            player.save()
            messages.success(request, "Player added successfully.")
            return redirect('admin_team_players', team_id=team.id)
    else:
        form = PlayerForm()
    return render(request, 'admin_player_form.html', {'form': form, 'team': team, 'action': 'Add'})

@admin_required
def admin_player_edit(request, player_id):
    player = get_object_or_404(Player, id=player_id)
    if request.method == 'POST':
        form = PlayerForm(request.POST, instance=player)
        if form.is_valid():
            form.save()
            messages.success(request, "Player updated successfully.")
            return redirect('admin_team_players', team_id=player.team.id)
    else:
        form = PlayerForm(instance=player)
    return render(request, 'admin_player_form.html', {'form': form, 'team': player.team, 'action': 'Edit'})

@admin_required
def admin_player_delete(request, player_id):
    player = get_object_or_404(Player, id=player_id)
    team_id = player.team.id
    player.delete()
    messages.success(request, "Player deleted successfully.")
    return redirect('admin_team_players', team_id=team_id)
