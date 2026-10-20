import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from budget.models import ImportBatch
from budget.importing import reconcile_batch


class Command(BaseCommand):
    help = 'Skriv privat radavstemming uten kildeverdier i terminalen.'
    def add_arguments(self, parser):
        parser.add_argument('--household-id', required=True)
        parser.add_argument('--output', required=True)
    def handle(self, *args, **options):
        root = Path(settings.PRIVATE_IMPORT_ROOT).resolve()
        target = Path(options['output']).resolve()
        if root not in target.parents: raise CommandError('Avstemming må lagres under privat importmappe.')
        batches = ImportBatch.objects.filter(household_id=options['household_id'])
        result = []
        for batch in batches:
            reconcile_batch(batch)
            rows = list(batch.importrecord_set.order_by('source_id').values('source_id', 'source_kind', 'status', 'target_id', 'reason'))
            result.append({'series': batch.series, 'sha256': batch.sha256, 'reconciliation': batch.reconciliation, 'records': rows})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write('Privat avstemmingsfil er skrevet. Finansielle summer må fortsatt godkjennes mot avklarte kildeposter.')
