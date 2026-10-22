from django.db import migrations, models
import uuid

class Migration(migrations.Migration):
    dependencies = [('budget', '0015_documents_shopping')]
    operations = [
        migrations.AlterField("document", "filename", models.CharField(max_length=180, blank=True)),
        migrations.AlterField("document", "content_type", models.CharField(max_length=40, blank=True)),
        migrations.AlterField("document", "sha256", models.CharField(max_length=64, db_index=True, blank=True)),
        migrations.AddField('document', 'transient', models.BooleanField(default=False)),
        migrations.AddField('document', 'expires_at', models.DateTimeField(null=True, blank=True)),
        migrations.AddField('document', 'cleanup_pending', models.BooleanField(default=False)),
        migrations.AddField('document', 'photo_deleted_at', models.DateTimeField(null=True, blank=True)),
        migrations.AddField('document', 'cancelled', models.BooleanField(default=False)),
        migrations.AddField('documentjob', 'generation', models.UUIDField(default=uuid.uuid4)),
    ]
