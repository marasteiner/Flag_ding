# Generated by Django 5.1.6 on 2025-02-22 23:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_game'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='team1_score',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='game',
            name='team2_score',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
