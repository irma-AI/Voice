from django.db import migrations

# A Call log's expiry is 30 days of 24 hours after its start (VOI-261). `started + interval '30 days'` added calendar days in the
# session's time zone, so a psql session on Europe/Stockholm across a DST change moved the expiry an hour, and the trigger let a
# delete through an hour early. Hours don't depend on the time zone, so the function is IMMUTABLE as declared.
# tests/portal/test_call_logs.py checks it in a Stockholm session.
FIXED = """
CREATE OR REPLACE FUNCTION accounts_call_log_expires_at(started timestamptz) RETURNS timestamptz AS $$
    SELECT started + interval '720 hours'
$$ LANGUAGE sql IMMUTABLE;
"""
CALENDAR = """
CREATE OR REPLACE FUNCTION accounts_call_log_expires_at(started timestamptz) RETURNS timestamptz AS $$
    SELECT started + interval '30 days'
$$ LANGUAGE sql IMMUTABLE;
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0032_greeting_language")]
    operations = [migrations.RunSQL(FIXED, CALENDAR)]
