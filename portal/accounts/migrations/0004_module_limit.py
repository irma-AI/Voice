from django.db import migrations

# A count cannot be a CHECK constraint, so the limit of ten Modules per Business (contract/business-settings.schema.json
# maxItems; the core refuses a whole call past it) is a trigger. It locks the Business row first, so two Modules added at
# the same moment cannot both pass.
CREATE = """
CREATE FUNCTION accounts_module_limit() RETURNS trigger AS $$
BEGIN
    PERFORM 1 FROM accounts_business WHERE id = NEW.business_id FOR UPDATE;
    IF (SELECT count(*) FROM accounts_module WHERE business_id = NEW.business_id) >= 10 THEN
        RAISE EXCEPTION 'module_limit: a Business has at most 10 Modules, remove one first'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER accounts_module_limit BEFORE INSERT ON accounts_module
    FOR EACH ROW EXECUTE FUNCTION accounts_module_limit();
"""
DROP = """
DROP TRIGGER accounts_module_limit ON accounts_module;
DROP FUNCTION accounts_module_limit();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_modules")]
    operations = [migrations.RunSQL(CREATE, DROP)]
