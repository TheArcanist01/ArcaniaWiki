# The enemy description field is now the enemy's trivia (shown under "Trivia").

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("arcaniawiki", "0010_item_thumbnail"),
    ]

    operations = [
        migrations.RenameField(model_name="enemy", old_name="content", new_name="trivia"),
    ]
