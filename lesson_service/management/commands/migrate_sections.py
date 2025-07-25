#!/usr/bin/env python
import os
import sqlite3
from django.conf import settings
from django.db import transaction
from django.core.management.base import BaseCommand
from lesson_service.models import Section, Lesson
from course_service.models import Course

class Command(BaseCommand):
    help = 'Migrate lesson sections from the legacy SQLite DB to the new Section model'

    def handle(self, *args, **options):
        legacy_db_path = os.path.join(settings.BASE_DIR, 'to_migrate', 'db.sqlite3')
        self.stdout.write(f'Connecting to legacy DB at {legacy_db_path}')

        Section.objects.all().delete()
        self.stdout.write(self.style.WARNING('Cleared existing Section entries'))
        conn = sqlite3.connect(legacy_db_path)
        cur = conn.cursor()

        cur.execute("SELECT lesson_id, id, name FROM kei_school_test ORDER BY lesson_id, id")
        rows = cur.fetchall()

        cur.execute("SELECT id, name FROM kei_school_course")
        legacy_courses = {cid: cname for cid, cname in cur.fetchall()}
        cur.execute("SELECT id, course_id, name FROM kei_school_lesson")
        legacy_lessons = cur.fetchall()

        db_courses = {c.title: c for c in Course.objects.all()}
        lesson_map = {}
        skipped = []
        for legacy_id, legacy_course_id, legacy_lesson_name in legacy_lessons:
            course_name = legacy_courses.get(legacy_course_id)
            new_course = db_courses.get(course_name)
            if not new_course:
                skipped.append((legacy_id, f"Course '{course_name}' not found"))
                continue
            new_lesson = Lesson.objects.filter(course=new_course, title=legacy_lesson_name).first()
            if not new_lesson:
                skipped.append((legacy_id, f"Lesson '{legacy_lesson_name}' not found in course '{course_name}'"))
                continue
            lesson_map[legacy_id] = new_lesson.id
        if skipped:
            for lid, reason in skipped:
                self.stdout.write(self.style.WARNING(f"Skipping legacy lesson {lid}: {reason}"))

        remapped = []
        for legacy_lesson_id, test_id, name in rows:
            new_lesson_id = lesson_map.get(legacy_lesson_id)
            if new_lesson_id:
                remapped.append((new_lesson_id, test_id, name))
        rows = remapped

        current_lesson = None
        order = 1
        created = 0

        with transaction.atomic():
            for new_lesson_id, test_id, name in rows:
                if new_lesson_id != current_lesson:
                    current_lesson = new_lesson_id
                    order = 1
                title = name or f'Раздел {order}'
                Section.objects.create(lesson_id=new_lesson_id, title=title, order=order)
                order += 1
                created += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully migrated {created} sections')) 