from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('events', '0006_game_coin_toss_winner_is_team1_game_offense_is_team1_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='OfficialAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('REF', 'Referee'), ('DJ', 'Down Judge'), ('FJ', 'Field Judge'), ('SJ', 'Side Judge')], max_length=3)),
                ('name', models.CharField(max_length=100)),
                ('license_number', models.CharField(max_length=50)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='official_assignments', to='events.game')),
            ],
        ),
    ]
