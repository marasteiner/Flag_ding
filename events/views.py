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
    ScoreEvent,
    OfficialAssignment,
)
from .forms import (
    GameForm,
    PlayerForm,
    AdminTeamCreationForm,
    AdminTeamEditForm,
    AddTeamToTournamentForm,
)

def admin_required(view_func):
    decorated_view_func = login_required(user_passes_test(lambda u: u.is_staff)(view_func))
    return decorated_view_func

############################################
# Helper to get per-team stats in one tournament
############################################
def get_team_stats_in_tournament(team, tournament):
    """
    Return a dict:
      {
        'points': total 2/1/0 from W/T,
        'pf': total points scored,
        'pa': total points allowed,
        'pd': pf - pa,
        'games': number of completed games,
        'opponents': {
            opponent_user: {
                'points_for': X,
                'points_against': Y,
                'result_points': 2/1/0
            }, ...
        }
      }
    This is used for tie-break logic (head-to-head).
    """
    from collections import defaultdict
    stats = {
        'points': 0,
        'pf': 0,
        'pa': 0,
        'pd': 0,
        'games': 0,
        'opponents': defaultdict(lambda: {'points_for':0, 'points_against':0, 'result_points':0}),
    }
    # Only consider completed games (both scores not None)
    all_games = tournament.games.filter(team1_score__isnull=False, team2_score__isnull=False)
    for g in all_games:
        if g.team1 == team or g.team2 == team:
            stats['games'] += 1
            if g.team1 == team:
                pf = g.team1_score
                pa = g.team2_score
                opp = g.team2
            else:
                pf = g.team2_score
                pa = g.team1_score
                opp = g.team1
            stats['pf'] += pf
            stats['pa'] += pa
            # 2/1/0 for W/T/L
            if pf > pa:
                rp = 2
            elif pf == pa:
                rp = 1
            else:
                rp = 0
            stats['points'] += rp
            stats['opponents'][opp]['points_for'] += pf
            stats['opponents'][opp]['points_against'] += pa
            stats['opponents'][opp]['result_points'] += rp

    stats['pd'] = stats['pf'] - stats['pa']
    return stats

############################################
# Tie-break for single tournament
############################################
from functools import cmp_to_key

def tie_break_teams_in_tournament(tournament, team_list):
    """
    team_list: list of dicts with keys: ['team','points','pf','pa','pd'].
    If teams are tied on 'points', apply tie-break steps:
      1) head-to-head percentage
      2) head-to-head net point differential
      3) head-to-head points scored
      4) total net point differential
      5) total points scored
    """
    # Build stats map for head-to-head checks
    stats_map = {}
    for d in team_list:
        t = d['team']
        stats_map[t] = get_team_stats_in_tournament(t, tournament)

    def compare(a, b):
        # First compare total points descending
        if a['points'] != b['points']:
            return b['points'] - a['points']

        # tie => apply step by step
        A = a['team']
        B = b['team']
        Astats = stats_map[A]
        Bstats = stats_map[B]

        # Step 1: head-to-head
        if B in Astats['opponents'] and A in Bstats['opponents']:
            A_head_points = Astats['opponents'][B]['result_points']
            B_head_points = Bstats['opponents'][A]['result_points']
            if A_head_points != B_head_points:
                return B_head_points - A_head_points
            # Step 2: head-to-head net diff
            A_head_pd = Astats['opponents'][B]['points_for'] - Astats['opponents'][B]['points_against']
            B_head_pd = Bstats['opponents'][A]['points_for'] - Bstats['opponents'][A]['points_against']
            if A_head_pd != B_head_pd:
                return B_head_pd - A_head_pd
            # Step 3: head-to-head points scored
            A_head_pf = Astats['opponents'][B]['points_for']
            B_head_pf = Bstats['opponents'][A]['points_for']
            if A_head_pf != B_head_pf:
                return B_head_pf - A_head_pf

        # Step 4: total net point differential
        if a['pd'] != b['pd']:
            return b['pd'] - a['pd']
        # Step 5: total points scored
        if a['pf'] != b['pf']:
            return b['pf'] - a['pf']

        # still tied => alphabetical
        if A.username < B.username:
            return -1
        elif A.username > B.username:
            return 1
        else:
            return 0

    sorted_list = sorted(team_list, key=cmp_to_key(compare))
    return sorted_list

def compute_tournament_standings(tournament):
    """
    Return a list of dicts:
      {
        'team': <User>,
        'points': <int>,
        'pf': <int>,
        'pa': <int>,
        'pd': <int>,
        'rank': <int>,
      }
    """
    apps = TournamentApplication.objects.filter(tournament=tournament, approved=True)
    data = []
    for app in apps:
        team = app.team
        st = get_team_stats_in_tournament(team, tournament)
        data.append({
            'team': team,
            'points': st['points'],
            'pf': st['pf'],
            'pa': st['pa'],
            'pd': st['pd'],
        })
    sorted_list = tie_break_teams_in_tournament(tournament, data)
    rank = 1
    out = []
    for item in sorted_list:
        item['rank'] = rank
        out.append(item)
        rank += 1
    return out

############################################
# Overall Standings (best 5 tournaments)
# Tie-break:
#   1) fewer tournaments
#   2) wins/games
#   3) PD/games
#   4) PF/games
#   5) PA/games
############################################
def gather_team_tournament_stats(team, tournament):
    st = get_team_stats_in_tournament(team, tournament)
    # st has 'points', 'pf', 'pa', 'games'
    # we can figure out wins/ties/losses from the actual game records:
    all_games = tournament.games.filter(team1_score__isnull=False, team2_score__isnull=False)
    w = 0
    t = 0
    l = 0
    for g in all_games:
        if g.team1 == team or g.team2 == team:
            if g.team1 == team:
                pf = g.team1_score
                pa = g.team2_score
            else:
                pf = g.team2_score
                pa = g.team1_score
            if pf > pa:
                w += 1
            elif pf == pa:
                t += 1
            else:
                l += 1
    return {
        'points': st['points'],
        'pf': st['pf'],
        'pa': st['pa'],
        'pd': st['pd'],
        'games': st['games'],
        'wins': w,
        'ties': t,
        'losses': l,
    }

def compute_overall_standings():
    from collections import defaultdict
    all_teams = User.objects.filter(is_staff=False)
    # build (team -> list of tournament-stats)
    team_data = defaultdict(list)

    # gather all tournaments for which the user has an approved application
    for team in all_teams:
        apps = TournamentApplication.objects.filter(team=team, approved=True)
        for app in apps:
            st = gather_team_tournament_stats(team, app.tournament)
            # only add if the team actually has at least 1 completed game
            if st['games'] > 0:
                team_data[team].append(st)

    # pick best 5 for each team
    def compare_tstats(a, b):
        # sort descending by 'points', then PD, then PF
        if a['points'] != b['points']:
            return b['points'] - a['points']
        if a['pd'] != b['pd']:
            return b['pd'] - a['pd']
        if a['pf'] != b['pf']:
            return b['pf'] - a['pf']
        return 0

    results = []
    for team in all_teams:
        stats_list = team_data[team]
        if not stats_list:
            # no tournaments
            results.append({
                'team': team,
                'used_tournaments': 0,
                'total_points': 0,
                'wins': 0,
                'ties': 0,
                'losses': 0,
                'pf': 0,
                'pa': 0,
                'pd': 0,
            })
            continue
        sorted_stats = sorted(stats_list, key=cmp_to_key(compare_tstats))
        best_5 = sorted_stats[:5]
        sum_points = sum(x['points'] for x in best_5)
        sum_wins = sum(x['wins'] for x in best_5)
        sum_ties = sum(x['ties'] for x in best_5)
        sum_losses = sum(x['losses'] for x in best_5)
        sum_pf = sum(x['pf'] for x in best_5)
        sum_pa = sum(x['pa'] for x in best_5)
        sum_pd = sum_pf - sum_pa
        used = len(best_5)

        results.append({
            'team': team,
            'used_tournaments': used,
            'total_points': sum_points,
            'wins': sum_wins,
            'ties': sum_ties,
            'losses': sum_losses,
            'pf': sum_pf,
            'pa': sum_pa,
            'pd': sum_pd,
        })

    def compare_overall(a, b):
        if a['total_points'] != b['total_points']:
            return b['total_points'] - a['total_points']

        # 1) fewer tournaments
        if a['used_tournaments'] != b['used_tournaments']:
            return a['used_tournaments'] - b['used_tournaments']
        # 2) wins/games
        a_g = a['wins'] + a['ties'] + a['losses']
        b_g = b['wins'] + b['ties'] + b['losses']
        a_wg = a['wins']/a_g if a_g else 0.0
        b_wg = b['wins']/b_g if b_g else 0.0
        if abs(a_wg - b_wg) > 1e-9:
            return -1 if (b_wg < a_wg) else 1 if (b_wg > a_wg) else 0
        # 3) PD/games
        a_pdg = a['pd']/a_g if a_g else 0.0
        b_pdg = b['pd']/b_g if b_g else 0.0
        if abs(a_pdg - b_pdg) > 1e-9:
            return -1 if (b_pdg < a_pdg) else 1 if (b_pdg > a_pdg) else 0
        # 4) PF/games
        a_pfg = a['pf']/a_g if a_g else 0.0
        b_pfg = b['pf']/b_g if b_g else 0.0
        if abs(a_pfg - b_pfg) > 1e-9:
            return -1 if (b_pfg < a_pfg) else 1 if (b_pfg > a_pfg) else 0
        # 5) PA/games
        a_pag = a['pa']/a_g if a_g else 0.0
        b_pag = b['pa']/b_g if b_g else 0.0
        if abs(a_pag - b_pag) > 1e-9:
            return -1 if (b_pag < a_pag) else 1 if (b_pag > a_pag) else 0
        # final fallback => alphabetical
        A = a['team'].username
        B = b['team'].username
        if A < B:
            return -1
        elif A > B:
            return 1
        else:
            return 0

    sorted_res = sorted(results, key=cmp_to_key(compare_overall))
    rank = 1
    final = []
    for item in sorted_res:
        item['rank'] = rank
        final.append(item)
        rank += 1
    return final

###########################################
# Custom Login/Logout
###########################################
class CustomLoginView(LoginView):
    def get_success_url(self):
        return '/'

class CustomLogoutView(LogoutView):
    http_method_names = ['get', 'post']
    def get_next_page(self):
        return '/'

###########################################
# Team (non-admin) Views
###########################################
@login_required
def players_view(request):
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
    player = get_object_or_404(Player, id=player_id)
    if player.team != request.user:
        return HttpResponseForbidden("You cannot delete this player.")
    player.delete()
    return redirect('players')

@login_required
def tournaments_view(request):
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot access team tournament page.")
    tournaments = Tournament.objects.all()
    applications = TournamentApplication.objects.filter(team=request.user)
    app_status = {app.tournament.id: app for app in applications}
    return render(request, 'tournaments.html', {'tournaments': tournaments, 'app_status': app_status})

@login_required
def apply_tournament(request, tournament_id):
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot apply for tournaments.")
    tournament = get_object_or_404(Tournament, id=tournament_id)
    TournamentApplication.objects.get_or_create(team=request.user, tournament=tournament)
    return redirect('tournaments')

@login_required
def tournament_detail(request, tournament_id):
    if request.user.is_staff:
        return HttpResponseForbidden("Admins cannot access team tournament detail page.")
    tournament = get_object_or_404(Tournament, id=tournament_id)
    games = tournament.games.all().order_by('start_time')
    all_finished = True
    for g in games:
        if g.team1_score is None or g.team2_score is None:
            all_finished = False
            break
    standings = compute_tournament_standings(tournament)
    return render(request, 'tournament_detail.html', {
        'tournament': tournament,
        'games': games,
        'standings': standings,
        'all_finished': all_finished,
    })

def index(request):
    tournaments = Tournament.objects.all()
    overall_standings = compute_overall_standings()
    return render(request, 'index.html', {
        'tournaments': tournaments,
        'overall_standings': overall_standings,
    })

###########################################
# Scorecard (referee) Views
###########################################
@login_required
def scorecard_home(request):
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
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    if request.method == 'POST':
        OfficialAssignment.objects.filter(game=game).delete()

        ref_name = request.POST.get('ref_name')
        ref_license = request.POST.get('ref_license')
        dj_name = request.POST.get('dj_name')
        dj_license = request.POST.get('dj_license')
        fj_name = request.POST.get('fj_name')
        fj_license = request.POST.get('fj_license')
        sj_name = request.POST.get('sj_name')
        sj_license = request.POST.get('sj_license')

        OfficialAssignment.objects.create(game=game, role="REF", name=ref_name, license_number=ref_license)
        OfficialAssignment.objects.create(game=game, role="DJ", name=dj_name, license_number=dj_license)
        OfficialAssignment.objects.create(game=game, role="FJ", name=fj_name, license_number=fj_license)
        OfficialAssignment.objects.create(game=game, role="SJ", name=sj_name, license_number=sj_license)

        coin_toss_winner = request.POST.get('coin_toss_winner')
        offense = request.POST.get('offense')
        game.coin_toss_winner_is_team1 = (coin_toss_winner == 'team1')
        game.offense_is_team1 = (offense == 'team1')
        game.save()
        return redirect('scorecard_live', game_id=game.id)
    return render(request, 'scorecard_coin_toss.html', {'game': game})

@login_required
def scorecard_live(request, game_id):
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    return render(request, 'scorecard_live.html', {'game': game})

def recompute_game_score(game):
    team1_total = 0
    team2_total = 0
    for ev in game.score_events.all():
        if ev.awarded_to_team1:
            team1_total += ev.points_awarded
        else:
            team2_total += ev.points_awarded
    game.team1_score = team1_total
    game.team2_score = team2_total
    game.save()

@login_required
def record_score_event(request, game_id):
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    if request.method == 'POST':
        event_type = request.POST.get('event_type')
        trikot_str = request.POST.get('trikot')
        trikot_num = None
        try:
            trikot_num = int(trikot_str) if trikot_str else None
        except ValueError:
            pass
        awarding_team_is_team1 = game.offense_is_team1
        if event_type == 'SAFETY':
            awarding_team_is_team1 = not awarding_team_is_team1

        points_awarded = 0
        if event_type == 'TD':
            points_awarded = 6
        elif event_type == 'PAT1':
            points_awarded = 1
        elif event_type == 'PAT2':
            points_awarded = 2
        elif event_type == 'SAFETY':
            points_awarded = 2

        ScoreEvent.objects.create(
            game=game,
            event_type=event_type,
            trikot=trikot_num,
            points_awarded=points_awarded,
            awarded_to_team1=awarding_team_is_team1,
        )
        recompute_game_score(game)
        messages.success(request, f"Event {event_type} recorded with trikot {trikot_num}.")
    return redirect('scorecard_live', game_id=game.id)

@login_required
def switch_offense(request, game_id):
    game = get_object_or_404(Game, id=game_id, referee=request.user)
    game.offense_is_team1 = not game.offense_is_team1
    game.save()
    return redirect('scorecard_live', game_id=game.id)

@login_required
def delete_score_event(request, game_id, event_id):
    game = get_object_or_404(Game, id=game_id)
    if game.referee != request.user:
        return HttpResponseForbidden("You are not the referee for this game.")
    ev = get_object_or_404(ScoreEvent, id=event_id, game=game)
    ev.delete()
    recompute_game_score(game)
    messages.success(request, "Scoring event deleted successfully.")
    return redirect('scorecard_live', game_id=game.id)

def scoreboard_data(request, tournament_id):
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

###########################################
# Admin (staff) Views
###########################################
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
    tournaments = Tournament.objects.all()
    # Show the overall table with PF, PA, PD using best-5 logic
    overall_standings = compute_overall_standings()
    return render(request, 'admin_tournaments.html', {
        'tournaments': tournaments,
        'overall_standings': overall_standings,
    })

@admin_required
def admin_tournament_create(request):
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

    all_finished = True
    for g in games:
        if g.team1_score is None or g.team2_score is None:
            all_finished = False
            break

    standings = compute_tournament_standings(tournament)
    return render(request, 'admin_games.html', {
        'tournament': tournament,
        'games': games,
        'form': form,
        'standings': standings,
        'all_finished': all_finished,
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
        else:  # count == 4
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

@admin_required
def admin_official_assignments(request):
    assignments = OfficialAssignment.objects.select_related('game','game__tournament').order_by('license_number')
    return render(request, 'admin_official_assignments.html', {'assignments': assignments})
