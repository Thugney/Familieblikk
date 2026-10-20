from django.db import migrations

RELATIONS = {
    'budget_entry': [('category_id', 'budget_category'), ('asset_id', 'budget_asset'), ('original_id', 'budget_entry'), ('occurrence_id', 'budget_billoccurrence')],
    'budget_monthplan': [('category_id', 'budget_category'), ('asset_id', 'budget_asset')],
    'budget_billtemplate': [('category_id', 'budget_category'), ('asset_id', 'budget_asset')],
    'budget_billoccurrence': [('template_id', 'budget_billtemplate'), ('category_id', 'budget_category'), ('asset_id', 'budget_asset')],
    'budget_fundtopup': [('occurrence_id', 'budget_billoccurrence')],
    'budget_importrecord': [('batch_id', 'budget_importbatch')],
}


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('Familieblikk krever PostgreSQL for familieavgrensede relasjoner.')
    schema_editor.execute('''CREATE FUNCTION familieblikk_guard_relation() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE linked uuid; parent_household uuid;
    BEGIN
      linked := (to_jsonb(NEW)->>TG_ARGV[0])::uuid;
      IF linked IS NOT NULL THEN
        EXECUTE format('SELECT household_id FROM %%I WHERE id=$1', TG_ARGV[1]) INTO parent_household USING linked;
        IF parent_household IS DISTINCT FROM NEW.household_id THEN
          RAISE EXCEPTION 'Koblingen må tilhøre samme familie' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$''')
    for table, relations in RELATIONS.items():
        for column, parent in relations:
            schema_editor.execute(f"CREATE TRIGGER guard_{column} BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION familieblikk_guard_relation('{column}', '{parent}')")


def uninstall(apps, schema_editor):
    for table, relations in RELATIONS.items():
        for column, parent in relations:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS guard_{column} ON {table}')
    schema_editor.execute('DROP FUNCTION IF EXISTS familieblikk_guard_relation()')


class Migration(migrations.Migration):
    dependencies = [('budget', '0001_initial')]
    operations = [migrations.RunPython(install, uninstall)]
