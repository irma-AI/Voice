import django.db.models.deletion
import django.utils.timezone
import portal.accounts.models
from django.db import migrations, models


def give_each_business_a_call_slug(apps, schema_editor):
    Business = apps.get_model("accounts", "Business")
    for business in Business.objects.all():
        business.call_slug = portal.accounts.models.new_call_slug()
        business.save(update_fields=["call_slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_business_facts_business_languages_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
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
        migrations.CreateModel(
            name="Call",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("seconds", models.IntegerField(null=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="calls",
                        to="accounts.business",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="call",
            index=models.Index(
                fields=["business", "started_at"],
                name="accounts_ca_busines_5f4efc_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="call",
            constraint=models.CheckConstraint(
                condition=models.Q(("seconds__isnull", True), ("seconds__gte", 0), _connector="OR"),
                name="call_seconds_must_not_be_negative",
            ),
        ),
    ]
