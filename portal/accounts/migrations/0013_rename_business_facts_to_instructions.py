# Written by hand: a rename, not a drop and add, so every Business keeps what it wrote (VOI-107).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_business_theme'),
    ]

    operations = [
        migrations.RenameField(
            model_name='business',
            old_name='facts',
            new_name='instructions',
        ),
    ]
