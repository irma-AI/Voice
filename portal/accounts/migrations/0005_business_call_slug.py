import portal.accounts.models
from django.db import migrations, models


def give_each_business_a_call_slug(apps, schema_editor):
    Business = apps.get_model("accounts", "Business")
    for business in Business.objects.all():
        business.call_slug = portal.accounts.models.new_call_slug()
        business.save(update_fields=["call_slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_module_limit"),
    ]

    operations = [
        # A unique field with a callable default cannot be added in one step: every existing row would get the same value.
        migrations.AddField(
            model_name="business",
            name="call_slug",
            field=models.CharField(max_length=40, null=True),
        ),
        migrations.RunPython(give_each_business_a_call_slug, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="business",
            name="call_slug",
            field=models.CharField(
                default=portal.accounts.models.new_call_slug,
                max_length=40,
                unique=True,
            ),
        ),
    ]
