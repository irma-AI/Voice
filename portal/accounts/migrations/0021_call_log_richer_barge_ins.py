from django.db import migrations

# VOI-154: the barge-in lines gain the echo signature, a level trace around each cut, a similarity score and a
# summary in the end event. call_log_events_hold_only_listed_fields (migration 0020) now also lets an event hold
# those fields; `caller_dbfs` and `bot_dbfs` are lists of at most 20 numbers (a level trace), still no words.
# The constraint calls these functions, so redefining them changes the rule for every later write.
FIELDS = """
CREATE OR REPLACE FUNCTION accounts_call_log_fields() RETURNS text[] AS $$
    SELECT ARRAY['t', 'call', 'e', 'vad', 'phase', 'played_ms', 'bot_speaking', 'bot_ms', 'peak_dbfs', 'rms_dbfs',
                 'src', 'echo_corr', 'echo_lag_ms', 'caller_dbfs', 'bot_dbfs', 'words', 'after_barge_in_ms',
                 'similarity', 'reason', 'secs', 'barge_ins', 'no_words', 'cut_share']
$$ LANGUAGE sql IMMUTABLE;
"""
OLD_FIELDS = """
CREATE OR REPLACE FUNCTION accounts_call_log_fields() RETURNS text[] AS $$
    SELECT ARRAY['t', 'call', 'e', 'vad', 'phase', 'played_ms', 'bot_speaking', 'bot_ms', 'peak_dbfs', 'rms_dbfs',
                 'src', 'words', 'after_barge_in_ms', 'reason', 'secs']
$$ LANGUAGE sql IMMUTABLE;
"""
EVENTS = """
CREATE OR REPLACE FUNCTION accounts_call_log_events_are_plain(events jsonb) RETURNS boolean AS $$
    SELECT jsonb_typeof(events) = 'array' AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(events) AS event
        WHERE jsonb_typeof(event) <> 'object' OR EXISTS (
            SELECT 1 FROM jsonb_each(event) AS field(key, value)
            WHERE field.key <> ALL (accounts_call_log_fields())
               OR CASE WHEN field.key = 'vad'
                    -- nested CASEs: Postgres does not promise OR's order, and reading a scalar as an object
                    -- or array raises instead of naming the rule
                    THEN CASE WHEN jsonb_typeof(field.value) <> 'object' THEN true
                              ELSE EXISTS (
                                  SELECT 1 FROM jsonb_each(field.value) AS setting(key, value)
                                  WHERE setting.key !~ '^[a-z_]{1,40}$'
                                     OR NOT accounts_call_log_value_is_plain(setting.value))
                         END
                  WHEN field.key IN ('caller_dbfs', 'bot_dbfs')
                    THEN CASE WHEN jsonb_typeof(field.value) <> 'array' THEN true
                              ELSE jsonb_array_length(field.value) > 20 OR EXISTS (
                                  SELECT 1 FROM jsonb_array_elements(field.value) AS level
                                  WHERE jsonb_typeof(level) <> 'number')
                         END
                    ELSE NOT accounts_call_log_value_is_plain(field.value)
                  END
        )
    )
$$ LANGUAGE sql IMMUTABLE;
"""
OLD_EVENTS = """
CREATE OR REPLACE FUNCTION accounts_call_log_events_are_plain(events jsonb) RETURNS boolean AS $$
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
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_call_log_rules")]
    operations = [migrations.RunSQL(FIELDS + EVENTS, OLD_EVENTS + OLD_FIELDS)]
