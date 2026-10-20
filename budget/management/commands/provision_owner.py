import os
import sys
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from budget.identity import provision_owner
from budget.importing import load_private_source


class Command(BaseCommand):
    help = 'Forhåndsregistrer kun den eksplisitte private eieren. Sender ingen e-post og verifiserer ikke adressen.'
    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true')
        parser.add_argument('--family-name', default='Min familie')
        parser.add_argument('--password-stdin', action='store_true')
    def handle(self, *args, **options):
        if not options['confirm']: raise CommandError('Eksplisitt --confirm kreves før forhåndsregistrering.')
        password = sys.stdin.readline().rstrip('\r\n') if options['password_stdin'] else os.environ.get('FAMILIEBLIKK_OWNER_PASSWORD', '')
        try:
            package, binding = load_private_source()
            if binding.get('import_series') != package.get('import_series'): raise ValidationError('Importserie stemmer ikke.')
            member, created = provision_owner(binding, password, options['family_name'])
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages)) from None
        except Exception:
            raise CommandError('Forhåndsregistrering avvist. Kontroller privat eierbinding og database; ingen konto er overtatt.') from None
        self.stdout.write('Eierkonto og tom privat familie opprettet uten e-postverifisering.' if created else 'Samme forhåndsregistrerte eier finnes allerede. Passord og familie er uendret.')
