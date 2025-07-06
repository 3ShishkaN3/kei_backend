#!/usr/bin/env python
import os
import django
import sqlite3
import sys

# Setup Django environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
cwd = os.getcwd()
logs_dir = os.path.join(cwd, 'logs')
os.makedirs(logs_dir, exist_ok=True)
for logfile in ('auth_service.log', 'axes.log'):
    open(os.path.join(logs_dir, logfile), 'a').close()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kei_backend.settings')
django.setup()

from lesson_service.models import Section
from django.db import transaction

# Path to legacy SQLite DB
legacy_db_path = os.path.join(BASE_DIR, 'to_migrate', 'db.sqlite3')
print(f"Connecting to legacy DB at {legacy_db_path}")
conn = sqlite3.connect(legacy_db_path)
print("Legacy DB tables:", [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")])
cur = conn.cursor()

# Fetch Test entries from legacy DB, ordered by lesson and id
cur.execute("SELECT lesson_id, id, name FROM kei_school_test ORDER BY lesson_id, id")
rows = cur.fetchall()

current_lesson = None
order = 1
created = 0

with transaction.atomic():
    for lesson_id, test_id, name in rows:
        if lesson_id != current_lesson:
            current_lesson = lesson_id
            order = 1
        title = name or f"Раздел {order}"
        Section.objects.create(lesson_id=lesson_id, title=title, order=order)
        order += 1
        created += 1

print(f"Successfully migrated {created} sections") 