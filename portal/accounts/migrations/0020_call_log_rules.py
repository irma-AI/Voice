from django.db import migrations

# The Call log's rules (VOI-153), in the store so every writer meets them (CLAUDE.md hard rule 1):
# - call_log_is_final: a stored log is never changed (a trigger, for every role).
# - call_log_is_kept_until_expiry: a log is deleted only once accounts_call_log_expires_at (30 days after the call's
#   start, Petter 2026-10-19) has passed; the deleting job is VOI-157.
# - call_log_events_hold_only_listed_fields: each event is an object whose fields are the ones .claude/rules/security.md
#   lists for a barge-in line (accounts_call_log_fields, which tests/portal/test_call_logs.py holds to that list), and
#   whose values are numbers, true or false, or short codes (no spaces, so no sentence); `vad` is an object of the same.
# TRUNCATE is not covered: the transactional tests flush tables with it.
CREATE = """
CREATE FUNCTION accounts_call_log_fields() RETURNS text[] AS $$
    SELECT ARRAY['t', 'call', 'e', 'vad', 'phase', 'played_ms', 'bot_speaking', 'bot_ms', 'peak_dbfs', 'rms_dbfs',
                 'src', 'words', 'after_barge_in_ms', 'reason', 'secs']
$$ LANGUAGE sql IMMUTABLE;

CREATE FUNCTION accounts_call_log_value_is_plain(value jsonb) RETURNS boolean AS $$
    SELECT jsonb_typeof(value) IN ('number', 'boolean')
        OR (jsonb_typeof(value) = 'string' AND value #>> '{}' ~ '^[A-Za-z0-9_-]{1,64}$')
$$ LANGUAGE sql IMMUTABLE;

CREATE FUNCTION accounts_call_log_events_are_plain(events jsonb) RETURNS boolean AS $$
    SELECT jsonb_typeof(events) = 'array' AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(events) AS event
        WHERE jsonb_typeof(event) <> 'object' OR EXISTS (
            SELECT 1 FROM jsonb_each(event) AS field(key, value)
            WHERE field.key <> ALL (accounts_call_log_fields())
               OR CASE WHEN field.key = 'vad'
                    THEN jsonb_typeof(field.value) <> 'object' OR EXISTS (
                        SELECT 1 FROM jsonb_each(field.value) AS setting(key, value)
                        WHERE setting.key !~ '^[a-z_]{1,40}$' OR NOT accounts_call_log_value_is_plain(setting.value))
                    ELSE NOT accounts_call_log_value_is_plain(field.value)
                  END
        )
    )
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE accounts_calllog ADD CONSTRAINT call_log_events_hold_only_listed_fields
    CHECK (accounts_call_log_events_are_plain(events));

CREATE FUNCTION accounts_call_log_expires_at(started timestamptz) RETURNS timestamptz AS $$
    SELECT started + interval '30 days'
$$ LANGUAGE sql IMMUTABLE;

CREATE FUNCTION accounts_call_log_is_final() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'call_log_is_final: a stored Call log is never changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF now() < accounts_call_log_expires_at(OLD.started_at) THEN
        RAISE EXCEPTION 'call_log_is_kept_until_expiry: a Call log is deleted only after accounts_call_log_expires_at, 30 days after the call started'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_call_log_is_final BEFORE UPDATE OR DELETE ON accounts_calllog
    FOR EACH ROW EXECUTE FUNCTION accounts_call_log_is_final();
"""
DROP = """
DROP TRIGGER accounts_call_log_is_final ON accounts_calllog;
DROP FUNCTION accounts_call_log_is_final();
DROP FUNCTION accounts_call_log_expires_at(timestamptz);
ALTER TABLE accounts_calllog DROP CONSTRAINT call_log_events_hold_only_listed_fields;
DROP FUNCTION accounts_call_log_events_are_plain(jsonb);
DROP FUNCTION accounts_call_log_value_is_plain(jsonb);
DROP FUNCTION accounts_call_log_fields();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_call_logs")]
    operations = [migrations.RunSQL(CREATE, DROP)]
