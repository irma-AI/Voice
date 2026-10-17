from django.db import migrations, models

# The marker that opens the totals page may be changed only by the `totals_marker` command (CLAUDE.md hard rule 2): a trigger, so a page, a script or an admin
# cannot set it either. The command switches a transaction-local setting on first. Whoever can run SQL on the server can do the same, which is the point:
# the marker follows server access, not a login.
CREATE = """
CREATE FUNCTION accounts_account_totals_marker_by_command() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'INSERT' AND NEW.sees_totals) OR (TG_OP = 'UPDATE' AND NEW.sees_totals IS DISTINCT FROM OLD.sees_totals) THEN
        IF coalesce(current_setting('voice.totals_marker_command', true), '') <> 'on' THEN
            RAISE EXCEPTION 'account_totals_marker_by_command: only the totals_marker command sets or clears sees_totals'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_account_totals_marker_by_command BEFORE INSERT OR UPDATE ON accounts_account
    FOR EACH ROW EXECUTE FUNCTION accounts_account_totals_marker_by_command();
"""
DROP = """
DROP TRIGGER accounts_account_totals_marker_by_command ON accounts_account;
DROP FUNCTION accounts_account_totals_marker_by_command();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_call_record_is_final")]
    operations = [
        migrations.AddField(
            model_name="account",
            name="sees_totals",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.RunSQL(CREATE, DROP),
    ]
