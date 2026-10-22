from django.db import migrations


def install(apps, schema_editor):
    schema_editor.execute("""
    CREATE FUNCTION familieblikk_area_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_area uuid; parent_house uuid; linked text; i integer;
    BEGIN
      IF TG_TABLE_NAME = 'budget_audit' AND to_jsonb(NEW)->>'operation' IN ('modultilgang', 'lokal registrering', 'handlelistevare') THEN
        IF NEW.financial_area_id IS NOT NULL THEN RAISE EXCEPTION 'Metadata cannot belong to financial area' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF NEW.financial_area_id IS NULL THEN
        IF TG_OP = 'INSERT' THEN RAISE EXCEPTION 'New financial rows require area' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF TG_OP = 'UPDATE' AND OLD.financial_area_id IS DISTINCT FROM NEW.financial_area_id THEN
        IF OLD.financial_area_id IS NOT NULL OR current_setting('familieblikk.legacy_assignment', true) IS DISTINCT FROM NEW.household_id::text THEN
          RAISE EXCEPTION 'Financial area is immutable' USING ERRCODE='23514';
        END IF;
      END IF;
      SELECT household_id INTO parent_house FROM budget_financialarea WHERE id=NEW.financial_area_id;
      IF parent_house IS DISTINCT FROM NEW.household_id THEN RAISE EXCEPTION 'Area belongs to another family' USING ERRCODE='23514'; END IF;
      i := 0;
      WHILE i < TG_NARGS LOOP
        linked := to_jsonb(NEW)->>TG_ARGV[i];
        IF linked IS NOT NULL THEN
          EXECUTE format('SELECT financial_area_id, household_id FROM %%I WHERE id::text=$1', TG_ARGV[i+1]) INTO parent_area, parent_house USING linked;
          IF parent_area IS DISTINCT FROM NEW.financial_area_id OR parent_house IS DISTINCT FROM NEW.household_id THEN
            RAISE EXCEPTION 'Relation belongs to another financial area' USING ERRCODE='23514';
          END IF;
        END IF;
        i := i + 2;
      END LOOP;
      RETURN NEW;
    END $$;
    """)
    for model in apps.get_app_config('budget').get_models():
        names = {f.name for f in model._meta.fields}
        if 'financial_area' not in names:
            continue
        arguments = []
        for field in model._meta.fields:
            if field.is_relation and field.name != 'financial_area' and any(f.name == 'financial_area' for f in field.related_model._meta.fields):
                arguments += [field.column, field.related_model._meta.db_table]
        params = ','.join("'%s'" % arg for arg in arguments)
        schema_editor.execute(f'CREATE CONSTRAINT TRIGGER financial_area_guard AFTER INSERT OR UPDATE ON {model._meta.db_table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION familieblikk_area_guard({params})')


def uninstall(apps, schema_editor):
    for model in apps.get_app_config('budget').get_models():
        if any(f.name == 'financial_area' for f in model._meta.fields):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS financial_area_guard ON {model._meta.db_table}')
    schema_editor.execute('DROP FUNCTION IF EXISTS familieblikk_area_guard()')


class Migration(migrations.Migration):
    dependencies = [('budget', '0019_alter_billoccurrence_options_and_more')]
    operations = [migrations.RunPython(install, uninstall)]
