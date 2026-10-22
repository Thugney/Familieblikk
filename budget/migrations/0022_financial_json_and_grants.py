from django.db import migrations


SQL = r"""
CREATE FUNCTION familieblikk_json_scope(data jsonb, area uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE pair record; child jsonb; target_table text; found_area uuid;
BEGIN
  IF jsonb_typeof(data) = 'array' THEN
    FOR child IN SELECT value FROM jsonb_array_elements(data) LOOP PERFORM familieblikk_json_scope(child, area); END LOOP;
  ELSIF jsonb_typeof(data) = 'object' THEN
    FOR pair IN SELECT * FROM jsonb_each(data) LOOP
      target_table := CASE pair.key
        WHEN 'category_id' THEN 'budget_category' WHEN 'category' THEN 'budget_category' WHEN 'asset_id' THEN 'budget_asset'
        WHEN 'receipt' THEN 'budget_document'
        WHEN 'original_id' THEN 'budget_entry' WHEN 'entry_id' THEN 'budget_entry'
        WHEN 'occurrence_id' THEN 'budget_billoccurrence' WHEN 'bill_id' THEN 'budget_billoccurrence'
        WHEN 'template_id' THEN 'budget_billtemplate' ELSE NULL END;
      IF pair.key = 'financial_area_id' AND pair.value <> 'null'::jsonb AND (pair.value #>> '{}') IS DISTINCT FROM area::text THEN
        RAISE EXCEPTION 'Snapshot belongs to another area' USING ERRCODE='23514';
      END IF;
      IF target_table IS NOT NULL AND pair.value <> 'null'::jsonb THEN
        EXECUTE format('SELECT financial_area_id FROM %%I WHERE id::text=$1', target_table) INTO found_area USING pair.value #>> '{}';
        IF found_area IS DISTINCT FROM area THEN RAISE EXCEPTION 'Snapshot relation belongs to another area' USING ERRCODE='23514'; END IF;
      END IF;
      PERFORM familieblikk_json_scope(pair.value, area);
    END LOOP;
  END IF;
END $$;

CREATE FUNCTION familieblikk_financial_payload_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE area uuid; target_table text; target_area uuid; target_id text;
BEGIN
  IF TG_TABLE_NAME = 'budget_seriesrevision' THEN
    SELECT financial_area_id INTO area FROM budget_billtemplate WHERE id=NEW.template_id;
    SELECT financial_area_id INTO target_area FROM budget_correctionevent WHERE id=NEW.event_id;
    IF area IS DISTINCT FROM target_area THEN RAISE EXCEPTION 'Series event area mismatch' USING ERRCODE='23514'; END IF;
    IF area IS NOT NULL THEN PERFORM familieblikk_json_scope(NEW.values, area); END IF;
    RETURN NEW;
  END IF;
  area := NEW.financial_area_id;
  IF area IS NULL THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME = 'budget_correctionevent' THEN
    PERFORM familieblikk_json_scope(NEW.before, area);
    PERFORM familieblikk_json_scope(NEW.after, area);
    target_table := CASE NEW.object_type WHEN 'entry' THEN 'budget_entry' WHEN 'billoccurrence' THEN 'budget_billoccurrence' WHEN 'billtemplate' THEN 'budget_billtemplate' END;
    target_id := NEW.object_id::text;
  ELSIF TG_TABLE_NAME = 'budget_importrecord' THEN
    PERFORM familieblikk_json_scope(NEW.approved_decision, area);
    target_table := CASE NEW.source_kind WHEN 'categories' THEN 'budget_category' WHEN 'transactions' THEN 'budget_entry'
      WHEN 'debts' THEN 'budget_asset' WHEN 'savings_goals' THEN 'budget_asset' WHEN 'annual_funds' THEN 'budget_asset' WHEN 'recipients' THEN 'budget_asset' END;
    target_id := NEW.target_id::text;
  ELSIF TG_TABLE_NAME = 'budget_workflowcommand' THEN
    PERFORM familieblikk_json_scope(NEW.payload, area);
    IF NEW.operation NOT IN ('shopping_list','shopping_item') THEN
      target_table := CASE WHEN NEW.operation LIKE 'shopping_%%' THEN 'budget_shoppingtrip' ELSE 'budget_document' END;
      target_id := NEW.result_id::text;
    END IF;
  END IF;
  IF target_id IS NOT NULL THEN
    IF target_table IS NULL THEN RAISE EXCEPTION 'Unknown financial target type' USING ERRCODE='23514'; END IF;
    EXECUTE format('SELECT financial_area_id FROM %%I WHERE id::text=$1', target_table) INTO target_area USING target_id;
    IF target_area IS DISTINCT FROM area THEN RAISE EXCEPTION 'Target belongs to another area' USING ERRCODE='23514'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION familieblikk_area_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE member_house uuid; area_house uuid; owner_member_id bigint; area_kind text;
BEGIN
  IF TG_TABLE_NAME = 'budget_financialarea' THEN
    SELECT household_id INTO member_house FROM budget_membership WHERE id=NEW.owner_id;
    IF member_house IS DISTINCT FROM NEW.household_id THEN RAISE EXCEPTION 'Area owner family mismatch' USING ERRCODE='23514'; END IF;
  ELSE
    SELECT household_id, owner_id, kind INTO area_house, owner_member_id, area_kind FROM budget_financialarea WHERE id=NEW.area_id;
    SELECT household_id INTO member_house FROM budget_membership WHERE id=NEW.member_id;
    IF member_house IS DISTINCT FROM area_house OR (NEW.role='editor' AND area_kind<>'shared') OR (NEW.role='owner' AND NEW.member_id<>owner_member_id) THEN
      RAISE EXCEPTION 'Invalid financial grant' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""


def install(apps, schema_editor):
    schema_editor.execute(SQL)
    for name in ['correctionevent', 'importrecord', 'workflowcommand', 'seriesrevision']:
        schema_editor.execute(f'CREATE CONSTRAINT TRIGGER financial_payload_guard AFTER INSERT OR UPDATE ON budget_{name} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION familieblikk_financial_payload_guard()')
    for name in ['financialarea', 'financialareagrant']:
        schema_editor.execute(f'CREATE CONSTRAINT TRIGGER financial_membership_guard AFTER INSERT OR UPDATE ON budget_{name} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION familieblikk_area_membership_guard()')


def uninstall(apps, schema_editor):
    for name in ['correctionevent', 'importrecord', 'workflowcommand', 'seriesrevision']:
        schema_editor.execute(f'DROP TRIGGER financial_payload_guard ON budget_{name}')
    for name in ['financialarea', 'financialareagrant']:
        schema_editor.execute(f'DROP TRIGGER financial_membership_guard ON budget_{name}')
    for name in ['familieblikk_financial_payload_guard()', 'familieblikk_area_membership_guard()', 'familieblikk_json_scope(jsonb, uuid)']:
        schema_editor.execute(f'DROP FUNCTION {name}')


class Migration(migrations.Migration):
    dependencies = [('budget', '0021_area_guard_integer_relations')]
    operations = [migrations.RunPython(install, uninstall)]
