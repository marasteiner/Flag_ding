# Generated by Django 5.1.6 on 2025-02-23 02:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0004_tournament_max_teams_tournament_number_of_teams'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='field_number',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
