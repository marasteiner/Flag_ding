from django import forms
from django.contrib.auth.models import User
from .models import Game, Player

class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ['team1', 'team2', 'referee', 'start_time', 'team1_score', 'team2_score']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'team1_score': forms.NumberInput(attrs={'placeholder': 'Score for Team 1 (optional)'}),
            'team2_score': forms.NumberInput(attrs={'placeholder': 'Score for Team 2 (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        tournament = kwargs.pop('tournament', None)
        super().__init__(*args, **kwargs)
        if tournament:
            applied_teams = User.objects.filter(applications__tournament=tournament).distinct()
            self.fields['team1'].queryset = applied_teams
            self.fields['team2'].queryset = applied_teams
            self.fields['referee'].queryset = applied_teams

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['trikot', 'vorname', 'nachname', 'passnummer']

class AdminTeamCreationForm(forms.ModelForm):
    team_name = forms.CharField(max_length=150, required=True, label="Team Name")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def save(self, commit=True):
        user = super().save(commit=False)
        # Save the team name in first_name field
        user.first_name = self.cleaned_data['team_name']
        user.set_password(self.cleaned_data['password'])
        user.is_staff = False  # ensure team users are not admins
        if commit:
            user.save()
        return user

class AdminTeamEditForm(forms.ModelForm):
    team_name = forms.CharField(max_length=150, required=True, label="Team Name")
    password = forms.CharField(widget=forms.PasswordInput, label="Password", required=False)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
    
    def __init__(self, *args, **kwargs):
        initial = kwargs.get('initial', {})
        if 'instance' in kwargs and kwargs['instance']:
            initial.setdefault('team_name', kwargs['instance'].first_name)
            kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['team_name']
        # Update password only if provided
        if self.cleaned_data['password']:
            user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

class AddTeamToTournamentForm(forms.Form):
    team = forms.ModelChoiceField(queryset=User.objects.none(), label="Team")
    
    def __init__(self, *args, **kwargs):
        tournament = kwargs.pop('tournament')
        super().__init__(*args, **kwargs)
        applied_team_ids = tournament.applications.values_list('team__id', flat=True)
        self.fields['team'].queryset = User.objects.filter(is_staff=False).exclude(id__in=applied_team_ids)