import budget.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('budget', '0012_pushdelivery_push_pending_queue_and_more')]
    operations = [
        migrations.AddField(model_name='membership', name='module_access', field=models.JSONField(blank=True, default=dict, validators=[budget.models.validate_module_access])),
        migrations.AddField(model_name='membership', name='access_version', field=models.PositiveIntegerField(default=1)),
    ]
