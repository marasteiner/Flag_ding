from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('events', '0007_officialassignment'),  # or your latest migration
    ]

    operations = [
        migrations.AddField(
            model_name='scoreevent',
            name='awarded_to_team1',
            field=models.BooleanField(default=False),
        ),
    ]
