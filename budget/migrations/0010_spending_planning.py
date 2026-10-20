import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def guards(apps, schema_editor):
    schema_editor.execute("""CREATE FUNCTION familieblikk_spending_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE h uuid;
    BEGIN
      IF TG_TABLE_NAME='budget_monthlybudgetheader' THEN
        SELECT household_id INTO h FROM budget_membership WHERE user_id=NEW.created_by_id;
        IF extract(day FROM NEW.month) <> 1 THEN RAISE EXCEPTION 'Planning month must start on day one' USING ERRCODE='23514'; END IF;
      ELSE
        SELECT household_id INTO h FROM budget_membership WHERE user_id=NEW.actor_id;
      END IF;
      IF h IS DISTINCT FROM NEW.household_id THEN RAISE EXCEPTION 'Planning household mismatch' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$""")
    for table in ('monthlybudgetheader', 'planningrequest'):
        schema_editor.execute(f'CREATE TRIGGER spending_guard BEFORE INSERT OR UPDATE ON budget_{table} FOR EACH ROW EXECUTE FUNCTION familieblikk_spending_guard()')


def unguards(apps, schema_editor):
    for table in ('monthlybudgetheader', 'planningrequest'):
        schema_editor.execute(f'DROP TRIGGER spending_guard ON budget_{table}')
    schema_editor.execute('DROP FUNCTION familieblikk_spending_guard()')


class Migration(migrations.Migration):
    dependencies = [('budget', '0009_calendar'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='MonthlyBudgetHeader', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('version', models.PositiveIntegerField(default=1)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('month', models.DateField()),
            ('expected_income_ore', models.PositiveBigIntegerField(blank=True, null=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('household', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='budget.household')),
        ], options={'constraints': [models.UniqueConstraint(fields=('household', 'month'), name='spending_unique_header')]}),
        migrations.CreateModel(name='PlanningRequest', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('key', models.UUIDField(default=uuid.uuid4)),
            ('digest', models.CharField(max_length=64)),
            ('result', models.JSONField(default=dict)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('household', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='budget.household')),
        ], options={'constraints': [models.UniqueConstraint(fields=('household', 'key'), name='spending_unique_request')]}),
        migrations.RunPython(guards, unguards),
    ]
