"""Preserve both category drafts and the monthly plans saved by import review."""
from django.db import migrations


SQL = r"""
CREATE OR REPLACE FUNCTION familieblikk_financial_payload_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
    -- Reviewing an undated category limit stores the resulting MonthPlan id.
    -- Accept only confirmed category plans in this same family and budget.
    IF NEW.source_kind = 'categories' AND NEW.status = 'confirmed' AND EXISTS (
      SELECT 1 FROM budget_monthplan p JOIN budget_category c ON c.id=p.category_id
      WHERE p.id=NEW.target_id AND p.financial_area_id=area AND p.household_id=NEW.household_id
        AND c.financial_area_id=area AND c.household_id=NEW.household_id
    ) THEN
      target_table := 'budget_monthplan';
    END IF;
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
"""


def install(apps, schema_editor):
    schema_editor.execute(SQL)


class Migration(migrations.Migration):
    dependencies = [('budget', '0024_notification_targets')]
    # Reversing this compatibility repair must not strand valid reviewed rows.
    # No source, financial record, approval or grant is changed by this migration.
    operations = [migrations.RunPython(install, migrations.RunPython.noop)]
