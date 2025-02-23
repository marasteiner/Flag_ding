from django.db import models
from django.contrib.auth.models import User

class Player(models.Model):
    team = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players')
    trikot = models.IntegerField()
    vorname = models.CharField(max_length=50)
    nachname = models.CharField(max_length=50)
    passnummer = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.vorname} {self.nachname} (Trikot: {self.trikot})"

class Tournament(models.Model):
    date = models.DateField()
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    max_teams = models.IntegerField(default=0)
    number_of_teams = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} at {self.location} on {self.date}"

class TournamentApplication(models.Model):
    team = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='applications')
    approved = models.BooleanField(default=False)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('team', 'tournament')

    def __str__(self):
        return f"Application of {self.team.username} for {self.tournament.name} (Approved: {self.approved})"

class Game(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='games')
    team1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team1_games')
    team2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team2_games')
    referee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referee_games')
    start_time = models.DateTimeField()
    team1_score = models.IntegerField(null=True, blank=True)
    team2_score = models.IntegerField(null=True, blank=True)
    field_number = models.IntegerField(null=True, blank=True)  # Only used for 5-team tournaments

    # New fields for coin toss & offense
    coin_toss_winner_is_team1 = models.BooleanField(default=True)
    offense_is_team1 = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.team1.username} vs {self.team2.username} at {self.start_time}"

class ScoreEvent(models.Model):
    """
    Records each scoring event in a game:
    - event_type: "TD", "PAT1", "PAT2", "SAFETY"
    - trikot: the trikot number entered by the user
    - points_awarded: how many points this event contributed
    """
    EVENT_TYPES = [
        ("TD", "Touchdown"),
        ("PAT1", "1-Point-Try"),
        ("PAT2", "2-Point-Try"),
        ("SAFETY", "Safety"),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='score_events')
    event_type = models.CharField(max_length=10, choices=EVENT_TYPES)
    trikot = models.IntegerField(null=True, blank=True)
    points_awarded = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} for game {self.game.id} (+{self.points_awarded} points)"
