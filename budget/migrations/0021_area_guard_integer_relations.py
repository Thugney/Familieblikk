from importlib import import_module
from django.db import migrations


def repair(apps, schema_editor):
    guards = import_module('budget.migrations.0020_financial_area_guards')
    guards.uninstall(apps, schema_editor)
    guards.install(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('budget', '0020_financial_area_guards')]
    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
