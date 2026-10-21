import signal
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from budget.push_services import claim_delivery, deliver_claim


class Command(BaseCommand):
    help = 'Restartbar køarbeider for vedvarende Web Push-leveringer.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        if not options['once']:
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
        while not stopping:
            try:
                close_old_connections()
                claim = claim_delivery()
                if claim: deliver_claim(*claim)
                elif options['once']: break
                else: time.sleep(2)
            except Exception:
                # Never emit request errors, endpoints, tokens or private key material.
                self.stderr.write('Pusharbeider: midlertidig feil; køen beholdes.')
                if options['once']: raise
                time.sleep(5)
            if options['once']: break
