from django.db import migrations

# A stored Call record is the base for billing, so no role may change or remove it (CLAUDE.md hard rule 1): a trigger,
# because a permission would only bind the roles we thought of. TRUNCATE is not covered: the transactional tests flush tables with it. The Business row
# a record points at cannot be deleted either: the foreign key has no ON DELETE action, so Postgres refuses it.
# A correction, when one is first needed, will be a new record that points at the old one.
CREATE = """
CREATE FUNCTION accounts_call_record_is_final() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'call_record_is_final: a stored Call record is never changed or deleted, add a correction record instead'
        USING ERRCODE = 'restrict_violation';
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_call_record_is_final BEFORE UPDATE OR DELETE ON accounts_callrecord
    FOR EACH ROW EXECUTE FUNCTION accounts_call_record_is_final();
"""
DROP = """
DROP TRIGGER accounts_call_record_is_final ON accounts_callrecord;
DROP FUNCTION accounts_call_record_is_final();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_call_records")]
    operations = [migrations.RunSQL(CREATE, DROP)]
