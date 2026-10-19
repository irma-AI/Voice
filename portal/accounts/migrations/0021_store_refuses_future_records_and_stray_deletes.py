from django.db import migrations

# Gaps from the 2026-10-19 audit (VOI-167), closed in the store for every writer (CLAUDE.md hard rules 1 and 2):
# - call_record_must_not_start_in_the_future: a record more than an hour ahead (core clock skew) would count toward
#   every day's spend until that date; the hour allows for the core's clock, as for a Call log (migration 0020).
# - access_token_is_revoked_never_deleted: AccessToken.revoke() is the one way a token stops working, so no DELETE,
#   nor a Business's CASCADE, removes one; offboarding revokes and keeps the Business row (VOI-126).
# - module_is_removed_by_module_remove: Module.remove() is the one way a Module goes (the Modules page and offboarding);
#   it switches the transaction-local voice.module_remove on first, as migration 0008 did for its command.
# TRUNCATE is not covered: the transactional tests flush tables with it.
CREATE = """
CREATE FUNCTION accounts_call_record_must_not_start_in_the_future() RETURNS trigger AS $$
BEGIN
    IF NEW.started_at > now() + interval '1 hour' THEN
        RAISE EXCEPTION 'call_record_must_not_start_in_the_future: a Call record''s start is when its call began'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_call_record_must_not_start_in_the_future BEFORE INSERT ON accounts_callrecord
    FOR EACH ROW EXECUTE FUNCTION accounts_call_record_must_not_start_in_the_future();

CREATE FUNCTION accounts_access_token_is_revoked_never_deleted() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'access_token_is_revoked_never_deleted: an Access token stays listed, use AccessToken.revoke()'
        USING ERRCODE = 'restrict_violation';
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_access_token_is_revoked_never_deleted BEFORE DELETE ON accounts_accesstoken
    FOR EACH ROW EXECUTE FUNCTION accounts_access_token_is_revoked_never_deleted();

CREATE FUNCTION accounts_module_is_removed_by_module_remove() RETURNS trigger AS $$
BEGIN
    IF coalesce(current_setting('voice.module_remove', true), '') <> 'on' THEN
        RAISE EXCEPTION 'module_is_removed_by_module_remove: a Module goes only through Module.remove()'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_module_is_removed_by_module_remove BEFORE DELETE ON accounts_module
    FOR EACH ROW EXECUTE FUNCTION accounts_module_is_removed_by_module_remove();
"""
DROP = """
DROP TRIGGER accounts_module_is_removed_by_module_remove ON accounts_module;
DROP FUNCTION accounts_module_is_removed_by_module_remove();
DROP TRIGGER accounts_access_token_is_revoked_never_deleted ON accounts_accesstoken;
DROP FUNCTION accounts_access_token_is_revoked_never_deleted();
DROP TRIGGER accounts_call_record_must_not_start_in_the_future ON accounts_callrecord;
DROP FUNCTION accounts_call_record_must_not_start_in_the_future();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_call_log_rules")]
    operations = [migrations.RunSQL(CREATE, DROP)]
