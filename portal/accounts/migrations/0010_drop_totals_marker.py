# db-test: skip drops a column and its trigger; test_call_link.py migrates through it both ways
from importlib import import_module

from django.db import migrations

marker = import_module("portal.accounts.migrations.0008_account_totals_marker")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_drop_unused_call_limits"),
    ]

    operations = [
        migrations.RunSQL(marker.DROP, marker.CREATE),
        migrations.RemoveField(model_name="account", name="sees_totals"),
    ]
