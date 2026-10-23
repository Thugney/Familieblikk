from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('budget', '0023_preserve_shared_shopping_commands')]
    operations = [
        migrations.AddField(
            model_name='calendarnotification', name='proposal',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, to='budget.areaaccesschange'),
        ),
        migrations.AddField(
            model_name='calendarnotification', name='shopping_list',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, to='budget.shoppinglist'),
        ),
    ]
