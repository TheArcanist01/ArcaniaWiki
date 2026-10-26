from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("arcaniawiki", "0011_enemy_trivia"),
    ]

    operations = [
        migrations.AddField(
            model_name="enemy",
            name="location_note",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Optional note shown in brackets after the level name in the Location "
                    'heading, e.g. "rare spawn anywhere in the map".'
                ),
                max_length=200,
            ),
        ),
    ]
