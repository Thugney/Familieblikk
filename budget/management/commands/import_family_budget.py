from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from budget import importing
from budget.models import Membership


class Command(BaseCommand):
    help = 'Importer privat kilde til eksisterende eier med godkjent identitetsproveniens. Oppretter aldri brukere.'

    def add_arguments(self, parser):
        parser.add_argument('--owner-email', required=True)
        parser.add_argument('--household-id', required=True)
        parser.add_argument('--confirm', action='store_true')

    def handle(self, *args, **options):
        if not options['confirm']: raise CommandError('Bruk --confirm etter privat kildegjennomgang.')
        try:
            package, binding = importing.load_private_source()
            owner = get_user_model().objects.get(email=options['owner_email'].lower())
            member = Membership.objects.get(user=owner, household_id=options['household_id'], role='admin')
            context = {'identity_method': member.identity_method, 'preregistered_membership_id': member.pk, 'provisioning_digest': member.provisioning_digest} if member.identity_method == 'preregistered_owner' else None
            batch = importing.apply_import(owner, owner.email.lower() if member.verified_at else None, package, binding, auth_context=context)
        except Exception as exc:
            raise CommandError('Import avvist. Kontroller verifisert eier, familie, kildeversjon og privat konfigurasjon.') from exc
        self.stdout.write(self.style.SUCCESS(f'Importserie behandlet. Bevarte rader: {batch.reconciliation.get("preserved", 0)}. Trenger avklaring: {batch.reconciliation.get("needs_review", 0)}.'))
