from django.db import migrations

# An Access token is made once and then only used or revoked (CLAUDE.md hard rule 1): a trigger, because a permission would only bind the roles we thought of.
# Allowed: last_used_at changes, and revoked_at goes from empty to the database's own clock (AccessToken.revoke). A revoked token stays revoked.
CREATE = """
CREATE FUNCTION accounts_access_token_is_fixed() RETURNS trigger AS $$
BEGIN
    IF (NEW.id, NEW.business_id, NEW.label, NEW.scope, NEW.is_operator, NEW.token_hash, NEW.created_at)
        IS DISTINCT FROM (OLD.id, OLD.business_id, OLD.label, OLD.scope, OLD.is_operator, OLD.token_hash, OLD.created_at) THEN
        RAISE EXCEPTION 'access_token_is_fixed: only last_used_at and a first revoked_at of an Access token change, make a new token instead'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.revoked_at IS DISTINCT FROM OLD.revoked_at
        AND (OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS DISTINCT FROM statement_timestamp()) THEN
        RAISE EXCEPTION 'access_token_revoked_at_is_set_once_by_revoke: a revoked token stays revoked, use AccessToken.revoke()'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_access_token_is_fixed BEFORE UPDATE ON accounts_accesstoken
    FOR EACH ROW EXECUTE FUNCTION accounts_access_token_is_fixed();
"""
DROP = """
DROP TRIGGER accounts_access_token_is_fixed ON accounts_accesstoken;
DROP FUNCTION accounts_access_token_is_fixed();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_access_tokens")]
    operations = [migrations.RunSQL(CREATE, DROP)]
