from django.db import migrations

# VOI-159: the config event gains what the call page says the browser applied, and the end event the page's count of
# playback gaps. call_log_events_hold_only_listed_fields (migrations 0020 and 0023) now also lets an event hold those fields,
# each a number, true or false, or a short code with no space like every other field: a user-agent string cannot fit.
# The list stays in the order the recorder writes each event's fields (the Call log pages show them in it).
# The constraint calls this function, so redefining it changes the rule for every later write.
FIELDS = """
CREATE OR REPLACE FUNCTION accounts_call_log_fields() RETURNS text[] AS $$
    SELECT ARRAY['t', 'call', 'e', 'vad', 'page_facts', 'echo_cancellation', 'noise_suppression', 'auto_gain_control',
                 'loopback', 'sample_rate', 'base_latency_ms', 'output_latency_ms', 'browser', 'os', 'os_version',
                 'phase', 'played_ms', 'bot_speaking', 'bot_ms', 'peak_dbfs', 'rms_dbfs',
                 'src', 'echo_corr', 'echo_lag_ms', 'words', 'after_barge_in_ms', 'caller_dbfs', 'bot_dbfs',
                 'similarity', 'reason', 'secs', 'barge_ins', 'no_words', 'cut_share', 'playback_gaps']
$$ LANGUAGE sql IMMUTABLE;
"""
OLD_FIELDS = """
CREATE OR REPLACE FUNCTION accounts_call_log_fields() RETURNS text[] AS $$
    SELECT ARRAY['t', 'call', 'e', 'vad', 'phase', 'played_ms', 'bot_speaking', 'bot_ms', 'peak_dbfs', 'rms_dbfs',
                 'src', 'echo_corr', 'echo_lag_ms', 'words', 'after_barge_in_ms', 'caller_dbfs', 'bot_dbfs',
                 'similarity', 'reason', 'secs', 'barge_ins', 'no_words', 'cut_share']
$$ LANGUAGE sql IMMUTABLE;
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0023_call_log_richer_barge_ins")]
    operations = [migrations.RunSQL(FIELDS, OLD_FIELDS)]
