import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from budget.document_ocr import process_one


class Command(BaseCommand):
    help = 'Behandler private dokumenter lokalt, separat fra pushkøen.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            process_one()
            if options['once']: return
            time.sleep(3)
