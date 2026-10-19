from django.db import migrations

# A token's label is free text a Business typed and may name a person, so offboarding blanks it (Petter, 2026-10-19).
# 0014's rule gains one exception, access_token_label_is_blanked_only_by_offboarding: with the transaction-local
# voice.offboard_token_labels on (offboard_business switches it, as migration 0008 did for its command), a revoked
# token's label may become `Token <its id>`, the same kind of name offboarding gives the Business; the store refuses
# an empty label (access_token_label_must_not_be_blank). Every other change stays refused, as in 0014.
CREATE = """
CREATE OR REPLACE FUNCTION accounts_access_token_is_fixed() RETURNS trigger AS $$
BEGIN
    IF NEW.label IS DISTINCT FROM OLD.label THEN
        IF coalesce(current_setting('voice.offboard_token_labels', true), '') <> 'on'
            OR OLD.revoked_at IS NULL OR NEW.label IS DISTINCT FROM 'Token ' || OLD.id THEN
            RAISE EXCEPTION 'access_token_label_is_blanked_only_by_offboarding: a token''s label changes only when offboard_business blanks a revoked one, make a new token instead'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    IF (NEW.id, NEW.business_id, NEW.scope, NEW.is_operator, NEW.token_hash, NEW.created_at)
        IS DISTINCT FROM (OLD.id, OLD.business_id, OLD.scope, OLD.is_operator, OLD.token_hash, OLD.created_at) THEN
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
"""
# Back to 0014's rule.
DROP = """
CREATE OR REPLACE FUNCTION accounts_access_token_is_fixed() RETURNS trigger AS $$
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
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0021_store_refuses_future_records_and_stray_deletes")]
    operations = [migrations.RunSQL(CREATE, DROP)]
