from django.core.management.base import BaseCommand, CommandError
from budget.push_services import ensure_key


class Command(BaseCommand):
    help = 'Klargjør stabil, kryptert Web Push-nøkkel i eksisterende database.'

    def handle(self, *args, **options):
        try: ensure_key()
        except Exception:
            raise CommandError('Pushnøkkelen kunne ikke klargjøres. Kontroller database og opprinnelig DJANGO_SECRET_KEY; ingen hemmeligheter skrives ut.') from None
        self.stdout.write('Web Push-nøkkel er klar. Eksisterende nøkkel er bevart.')
