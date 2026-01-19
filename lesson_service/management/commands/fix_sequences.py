from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Resets database sequences for all models in all apps'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    quote_ident(t.relname) AS table_name,
                    quote_ident(s.relname) AS sequence_name,
                    quote_ident(a.attname) AS column_name
                FROM pg_class s
                JOIN pg_depend d ON d.objid = s.oid
                JOIN pg_class t ON t.oid = d.refobjid
                JOIN pg_attribute a ON (a.attrelid = d.refobjid AND a.attnum = d.refobjsubid)
                WHERE s.relkind = 'S' 
                AND d.deptype IN ('a', 'i')
                AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
            """)
            
            rows = cursor.fetchall()
            if not rows:
                self.stdout.write(self.style.WARNING("No sequences found to reset."))
                return

            for table_name, sequence_name, column_name in rows:
                self.stdout.write(f"Resetting sequence {sequence_name} for table {table_name}...")
                cursor.execute(f"SELECT setval('{sequence_name}', COALESCE((SELECT MAX({column_name}) FROM {table_name}), 0) + 1, false);")
            
            self.stdout.write(self.style.SUCCESS("All sequences have been reset successfully."))
