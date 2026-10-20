import os
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql


class Command(BaseCommand):
    help = 'Opprett en begrenset runtime-rolle med eier-/migrasjonsforbindelsen.'
    def handle(self, *args, **options):
        role = os.environ.get('POSTGRES_APP_USER', '')
        password = os.environ.get('POSTGRES_APP_PASSWORD', '')
        if not role or not password or role == connection.settings_dict['USER']:
            raise CommandError('Angi separat POSTGRES_APP_USER og POSTGRES_APP_PASSWORD.')
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', [role])
                verb = 'ALTER' if cursor.fetchone() else 'CREATE'
                cursor.execute(sql.SQL(verb + ' ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
                cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(connection.settings_dict['NAME']), sql.Identifier(role)))
                cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
                cursor.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
                cursor.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(role)))
                cursor.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}').format(sql.Identifier(role)))
                cursor.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}').format(sql.Identifier(role)))
        except Exception as exc:
            raise CommandError('Oppretting av begrenset runtime-rolle feilet. Ingen hemmeligheter skrives ut.') from exc
        self.stdout.write('Separat runtime-rolle er konfigurert uten skjemaeierskap eller DDL-rettigheter.')
