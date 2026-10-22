from django.db import migrations


def preserve(apps, schema_editor):
    old = apps.get_model('budget', 'WorkflowCommand')
    shared = apps.get_model('budget', 'ShoppingCommand')
    # This copies only family-shared list commands; it assigns no finance owner.
    for command in old.objects.filter(operation__in=['shopping_list', 'shopping_item']).iterator():
        shared.objects.get_or_create(household_id=command.household_id,
            created_by_id=command.created_by_id, key=command.key,
            defaults={'operation': command.operation, 'payload': command.payload, 'result_id': command.result_id})


class Migration(migrations.Migration):
    dependencies = [('budget', '0022_financial_json_and_grants')]
    operations = [migrations.RunPython(preserve, migrations.RunPython.noop)]
