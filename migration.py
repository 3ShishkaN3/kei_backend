import os
import sys
import psycopg2
import sqlite3
import django
import shutil
import datetime
from django.utils import timezone
from django.conf import settings

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kei_backend'))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kei_backend.settings")
django.setup()

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from auth_service.models import User
from user_service.models import UserProfile, UserSettings
from course_service.models import Course, CourseEnrollment, CourseTeacher
from lesson_service.models import Lesson, Section, LessonCompletion
from dict_service.models import DictionarySection, DictionaryEntry, UserLearnedEntry
from material_service.models import TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial
from lesson_service.models import SectionItem
from progress_service.models import LearningStats

SQLITE_DB_PATH = 'to_migrate/db.sqlite3'

POSTGRES_DB_NAME = "kei_db"
POSTGRES_USER = "kei_user"
POSTGRES_PASSWORD = "kei_password"
POSTGRES_HOST = "postgres"
POSTGRES_PORT = "5432"

def get_sqlite_connection():
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        print("Успешное подключение к SQLite.")
        return conn
    except sqlite3.Error as e:
        print(f"Ошибка подключения к SQLite: {e}")
        return None

def get_postgres_connection():
    try:
        conn = psycopg2.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            client_encoding='UTF8'
        )
        print("Успешное подключение к PostgreSQL.")
        return conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к PostgreSQL: {e}")
        return None

def migrate_users(sqlite_conn):
    print("\nНачинаю миграцию/обновление пользователей (username и роли)...")
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("""
        SELECT 
            u.id, u.password, u.last_login, u.is_superuser, u.username as old_username, 
            u.first_name, u.last_name, u.email, u.is_staff, u.is_active, u.date_joined, 
            ui.nickname 
        FROM auth_user u
        LEFT JOIN kei_school_userinfo ui ON u.id = ui.user_id
    """)
    old_users = sqlite_cursor.fetchall()

    updated_count = 0
    skipped_count = 0

    for old_user_data in old_users:
        try:
            user_to_update = User.objects.filter(email__iexact=old_user_data['email']).first()
            if not user_to_update:
                if old_user_data['is_superuser']:
                    new_role = User.Role.ADMIN
                elif old_user_data['is_staff']:
                    new_role = User.Role.TEACHER
                else:
                    new_role = User.Role.STUDENT

                new_username = old_user_data['nickname'] if old_user_data['nickname'] else old_user_data['old_username']

                base_username = new_username
                unique_username = base_username
                suffix_i = 1
                while User.objects.filter(username__iexact=unique_username).exists():
                    unique_username = f"{base_username}_{suffix_i}"
                    suffix_i += 1
                new_username = unique_username

                user_to_update = User.objects.create(
                    username=new_username,
                    email=old_user_data['email'].lower(),
                    password=old_user_data['password'],
                    is_superuser=old_user_data['is_superuser'],
                    is_staff=old_user_data['is_staff'],
                    is_active=old_user_data['is_active'],
                    date_joined=old_user_data['date_joined'],
                    last_login=old_user_data['last_login'],
                    role=new_role
                )
                print(f"Создан пользователь с email {user_to_update.email}.")
                updated_count += 1
                continue

            if old_user_data['is_superuser']:
                new_role = User.Role.ADMIN
            elif old_user_data['is_staff']:
                new_role = User.Role.TEACHER
            else:
                new_role = User.Role.STUDENT

            new_username = old_user_data['nickname'] if old_user_data['nickname'] else old_user_data['old_username']
            
            username_changed = user_to_update.username != new_username
            role_changed = user_to_update.role != new_role

            if not username_changed and not role_changed:
                print(f"Данные для {user_to_update.email} уже корректны. Пропускаю.")
                skipped_count += 1
                continue

            fields_to_update = []
            if username_changed:
                if User.objects.filter(username__iexact=new_username).exclude(pk=user_to_update.pk).exists():
                    print(f"Новый username '{new_username}' для пользователя {user_to_update.email} уже занят. Пропускаю обновление username.")
                else:
                    print(f"Обновляю username для {user_to_update.email}: '{user_to_update.username}' -> '{new_username}'")
                    user_to_update.username = new_username
                    fields_to_update.append('username')

            if role_changed:
                print(f"Обновляю роль для {user_to_update.email}: '{user_to_update.role}' -> '{new_role}'")
                user_to_update.role = new_role
                fields_to_update.append('role')

            if fields_to_update:
                user_to_update.save(update_fields=fields_to_update)
                updated_count += 1
            else:
                skipped_count += 1

        except Exception as e:
            print(f"Ошибка при обновлении пользователя с email {old_user_data['email']}: {e}")
            skipped_count += 1

    print(f"\nОбновление пользователей завершено.")
    print(f"Обновлено записей: {updated_count}")
    print(f"Пропущено: {skipped_count}")


def migrate_groups_and_permissions(sqlite_conn):
    print("\nНачинаю миграцию групп и связей...")
    sqlite_cursor = sqlite_conn.cursor()

    sqlite_cursor.execute("SELECT * FROM auth_group")
    old_groups = sqlite_cursor.fetchall()
    for old_group in old_groups:
        group, created = Group.objects.get_or_create(
            id=old_group['id'],
            defaults={'name': old_group['name']}
        )
        if created:
            print(f"Группа '{group.name}' создана.")
        else:
            print(f"Группа '{group.name}' уже существует.")

    sqlite_cursor.execute("SELECT * FROM auth_user_groups")
    old_user_groups = sqlite_cursor.fetchall()
    for user_group in old_user_groups:
        try:
            user = User.objects.get(id=user_group['user_id'])
            group = Group.objects.get(id=user_group['group_id'])
            user.groups.add(group)
            print(f"Пользователь '{user.username}' добавлен в группу '{group.name}'.")
        except User.DoesNotExist:
            print(f"Пользователь с id={user_group['user_id']} не найден. Пропускаю связь с группой.")
        except Group.DoesNotExist:
            print(f"Группа с id={user_group['group_id']} не найдена. Пропускаю связь.")


def migrate_user_service(sqlite_conn):
    print("\nНачинаю миграцию user_service...")
    sqlite_cursor = sqlite_conn.cursor()

    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    print("Мигрирую UserProfile (включая аватары)...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userinfo")
    old_user_infos = sqlite_cursor.fetchall()
    for info in old_user_infos:
        try:
            user = User.objects.get(id=info['user_id'])
            
            old_avatar_relative_path = info['avatar']
            new_avatar_db_path = None

            if old_avatar_relative_path:
                source_path = os.path.join(OLD_MEDIA_ROOT, old_avatar_relative_path)
                dest_path = os.path.join(NEW_MEDIA_ROOT, old_avatar_relative_path)
                
                if os.path.exists(source_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    new_avatar_db_path = old_avatar_relative_path
                    print(f"Скопирован аватар для '{user.username}'.")
                else:
                    print(f"Файл аватара не найден: {source_path}")

            profile, created = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    'phone_number': info['phone_number'],
                    'avatar': new_avatar_db_path
                }
            )
            
            if created:
                print(f"Создан профиль для пользователя '{user.username}'.")
            else:
                print(f"Обновлен профиль для пользователя '{user.username}'.")

        except User.DoesNotExist:
            print(f"Пользователь с id={info['user_id']} не найден. Пропускаю профиль.")

    print("\nМигрирую UserSettings...")
    sqlite_cursor.execute("SELECT * FROM kei_school_usersettings")
    old_user_settings = sqlite_cursor.fetchall()
    for setting in old_user_settings:
        try:
            user = User.objects.get(id=setting['user_id'])
            user_settings, created = UserSettings.objects.update_or_create(
                user=user,
                defaults={'show_learned_items': setting['show_completed_answers']}
            )
            if created:
                print(f"Созданы настройки для пользователя '{user.username}'.")
            else:
                user_settings.show_learned_items = setting['show_completed_answers']
                user_settings.save()
                print(f"Обновлены настройки для пользователя '{user.username}'.")
        except User.DoesNotExist:
            print(f"Пользователь с id={setting['user_id']} не найден. Пропускаю настройки.")

    print("\nМиграция user_service завершена.")


def migrate_course_service(sqlite_conn):
    print("\nНачинаю миграцию course_service...")
    sqlite_cursor = sqlite_conn.cursor()

    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    print("Мигрирую курсы...")
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()
    
    status_mapping = {
        'Открыт': 'published',
        'Закрыт': 'draft',
    }

    sqlite_cursor.execute("SELECT * FROM kei_school_course")
    old_courses = sqlite_cursor.fetchall()
    for course_data in old_courses:
        old_image_path = course_data['image']
        new_image_db_path = None
        if old_image_path:
            source_path = os.path.join(OLD_MEDIA_ROOT, old_image_path)
            dest_path = os.path.join(NEW_MEDIA_ROOT, old_image_path)
            if os.path.exists(source_path):
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(source_path, dest_path)
                new_image_db_path = old_image_path
                print(f"Скопировано изображение для курса '{course_data['name']}'.")
            else:
                print(f"Файл изображения не найден: {source_path}")

        new_status = status_mapping.get(course_data['status'], 'draft')

        course, created = Course.objects.update_or_create(
            id=course_data['id'],
            defaults={
                'title': course_data['name'],
                'subtitle': course_data['short_description'],
                'description': course_data['description'],
                'status': new_status,
                'cover_image': new_image_db_path,
                'created_by': default_author
            }
        )
        if created:
            print(f"Курс '{course.title}' создан.")
        else:
            print(f"Курс '{course.title}' обновлен.")

    print("\nМигрирую связи пользователей с курсами...")
    sqlite_cursor.execute("SELECT * FROM kei_school_usercourse")
    old_enrollments = sqlite_cursor.fetchall()
    for enroll_data in old_enrollments:
        try:
            user = User.objects.get(id=enroll_data['user_id'])
            course = Course.objects.get(id=enroll_data['course_id'])

            enrollment, created = CourseEnrollment.objects.get_or_create(
                student=user,
                course=course
            )
            if created:
                print(f"Пользователь '{user.username}' записан на курс '{course.title}'.")
            
            if user.role in [User.Role.TEACHER, User.Role.ADMIN]:
                teacher, created = CourseTeacher.objects.get_or_create(
                    teacher=user,
                    course=course,
                )
                if created:
                     print(f"Пользователь '{user.username}' назначен преподавателем на курс '{course.title}'.")

        except User.DoesNotExist:
            print(f"Пользователь с id={enroll_data['user_id']} не найден. Пропускаю запись на курс.")
        except Course.DoesNotExist:
            print(f"Курс с id={enroll_data['course_id']} не найден. Пропускаю запись.")

    print("\nМиграция course_service завершена.")


def migrate_lesson_service(sqlite_conn):
    print("\nНачинаю миграцию lesson_service...")
    sqlite_cursor = sqlite_conn.cursor()

    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'
    
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()

    print("Мигрирую уроки и создаю разделы...")
    sqlite_cursor.execute("SELECT * FROM kei_school_lesson")
    old_lessons = sqlite_cursor.fetchall()
    for lesson_data in old_lessons:
        try:
            course = Course.objects.get(id=lesson_data['course_id'])

            old_image_path = lesson_data['image']
            new_image_db_path = None
            if old_image_path:
                source_path = os.path.join(OLD_MEDIA_ROOT, old_image_path)
                dest_path = os.path.join(NEW_MEDIA_ROOT, old_image_path)
                if os.path.exists(source_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    new_image_db_path = old_image_path
                    print(f"Скопировано изображение для урока '{lesson_data['name']}'.")
                else:
                    print(f"Файл изображения не найден: {source_path}")

            lesson, created = Lesson.objects.update_or_create(
                id=lesson_data['id'],
                defaults={
                    'course': course,
                    'title': lesson_data['name'],
                    'cover_image': new_image_db_path,
                    'created_by': default_author
                }
            )
            if created:
                print(f"Урок '{lesson.title}' создан.")
            else:
                print(f"Урок '{lesson.title}' обновлен.")


        except Course.DoesNotExist:
            print(f"Курс с id={lesson_data['course_id']} не найден. Пропускаю урок '{lesson_data['name']}'.")

    print("\nМигрирую прогресс прохождения уроков...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userlesson WHERE is_complete = 1")
    old_completions = sqlite_cursor.fetchall()
    for completion_data in old_completions:
        try:
            user = User.objects.get(id=completion_data['user_id'])
            lesson = Lesson.objects.get(id=completion_data['lesson_id'])

            completion, created = LessonCompletion.objects.get_or_create(
                student=user,
                lesson=lesson,
                defaults={'completed_at': completion_data['complete_date']}
            )
            if created:
                print(f"Зафиксировано прохождение урока '{lesson.title}' пользователем '{user.username}'.")

        except User.DoesNotExist:
            print(f"Пользователь с id={completion_data['user_id']} не найден. Пропускаю запись о прохождении.")
        except Lesson.DoesNotExist:
            print(f"Урок с id={completion_data['lesson_id']} не найден. Пропускаю запись о прохождении.")

    print("\nМиграция lesson_service завершена.")


def migrate_sections(sqlite_conn):
    print("\nНачинаю миграцию разделов (Section) из kei_school_test...")
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("SELECT * FROM kei_school_test")
    old_tests = sqlite_cursor.fetchall()
    for test_data in old_tests:
        try:
            lesson = Lesson.objects.get(id=test_data['lesson_id'])
            title = test_data['name'] or test_data['title'] or f"Section {test_data['id']}"
            section, created = Section.objects.update_or_create(
                lesson=lesson,
                order=test_data['id'],
                defaults={'title': title}
            )
            if created:
                print(f"Создан раздел '{title}' для урока '{lesson.title}'.")
            else:
                print(f"Обновлен раздел '{title}' для урока '{lesson.title}'.")
        except Lesson.DoesNotExist:
            print(f"Урок с id={test_data['lesson_id']} не найден. Пропускаю раздел '{test_data.get('name', test_data['id'])}'.")
    print("\nМиграция разделов завершена.")


def migrate_section_texts(sqlite_conn):
    print("\nНачинаю миграцию текстовых материалов разделов...")
    sqlite_cursor = sqlite_conn.cursor()
    from material_service.models import TextMaterial
    from lesson_service.models import SectionItem
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()
    sqlite_cursor.execute("SELECT * FROM kei_school_test")
    old_tests = sqlite_cursor.fetchall()
    for test_data in old_tests:
        try:
            section = Section.objects.get(lesson_id=test_data['lesson_id'], order=test_data['id'])
        except Section.DoesNotExist:
            print(f"Раздел для теста id={test_data['id']} не найден. Пропускаю текстовый материал.")
            continue
        subtitle = test_data['subtitle']
        description = test_data['description']
        if subtitle or description:
            content = f"{subtitle}\n\n{description}".strip()
            text_material = TextMaterial.objects.create(
                title='',
                content=content,
                is_markdown=False,
                created_by=default_author
            )
            content_type = ContentType.objects.get_for_model(TextMaterial)
            item_order = section.items.count() + 1
            SectionItem.objects.create(
                section=section,
                order=item_order,
                item_type='text',
                content_type=content_type,
                object_id=text_material.id
            )
            print(f"Создан текстовый материал для раздела '{section.title}' (id={section.id})")
    print("Миграция текстовых материалов завершена.")


def migrate_dict_service(sqlite_conn):
    print("\nНачинаю миграцию dict_service...")
    sqlite_cursor = sqlite_conn.cursor()

    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()

    print("Мигрирую разделы словаря...")
    sqlite_cursor.execute("SELECT * FROM kei_school_practice")
    old_practices = sqlite_cursor.fetchall()
    
    practice_to_section_mapping = {}
    
    for practice_data in old_practices:
        try:
            course = Course.objects.get(id=practice_data['course_id'])
            
            old_image_path = practice_data['image']
            new_image_db_path = None
            if old_image_path:
                source_path = os.path.join(OLD_MEDIA_ROOT, old_image_path)
                dest_path = os.path.join(NEW_MEDIA_ROOT, old_image_path)
                if os.path.exists(source_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    new_image_db_path = old_image_path
                    print(f"Скопировано изображение для раздела '{practice_data['name']}'.")
                else:
                    print(f"Файл изображения не найден: {source_path}")

            is_primary = not DictionarySection.objects.filter(course=course).exists()

            section, created = DictionarySection.objects.update_or_create(
                course=course,
                title=practice_data['name'],
                defaults={
                    'banner_image': new_image_db_path,
                    'is_primary': is_primary,
                    'created_by': default_author
                }
            )
            
            practice_to_section_mapping[practice_data['id']] = section
            
            if created:
                print(f"Создан раздел словаря '{section.title}' для курса '{course.title}'.")
            else:
                print(f"Обновлен раздел словаря '{section.title}' для курса '{course.title}'.")

        except Course.DoesNotExist:
            print(f"Курс с id={practice_data['course_id']} не найден. Пропускаю раздел '{practice_data['name']}'.")

    print("\nМигрирую словарные записи...")
    sqlite_cursor.execute("SELECT * FROM kei_school_practicecard")
    old_practice_cards = sqlite_cursor.fetchall()
    
    for card_data in old_practice_cards:
        try:
            section = practice_to_section_mapping.get(card_data['practice_id'])
            if not section:
                print(f"Раздел словаря для practice_id={card_data['practice_id']} не найден. Пропускаю карточку.")
                continue

            lesson = None
            if card_data['target_lesson_id']:
                try:
                    lesson = Lesson.objects.get(id=card_data['target_lesson_id'])
                except Lesson.DoesNotExist:
                    print(f"Урок с id={card_data['target_lesson_id']} не найден. Карточка будет без привязки к уроку.")

            old_audio_path = card_data['audio']
            new_audio_db_path = None
            if old_audio_path:
                source_path = os.path.join(OLD_MEDIA_ROOT, old_audio_path)
                dest_path = os.path.join(NEW_MEDIA_ROOT, 'dict_pronunciations', old_audio_path)
                if os.path.exists(source_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    new_audio_db_path = f'dict_pronunciations/{old_audio_path}'
                    print(f"Скопировано аудио для карточки '{card_data['text_front']}'.")
                else:
                    print(f"Аудио файл не найден: {source_path}")

            entry, created = DictionaryEntry.objects.update_or_create(
                section=section,
                term=card_data['text_front'],
                defaults={
                    'reading': card_data['text_back'],
                    'translation': card_data['description_back'],
                    'pronunciation_audio': new_audio_db_path,
                    'lesson': lesson,
                    'created_by': default_author
                }
            )
            
            if created:
                print(f"Создана словарная запись '{entry.term}' в разделе '{section.title}'.")
            else:
                print(f"Обновлена словарная запись '{entry.term}' в разделе '{section.title}'.")

        except Exception as e:
            print(f"Ошибка при миграции карточки {card_data['id']}: {e}")

    print("\nМигрирую изученные записи...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userpractice WHERE is_complete = 1")
    old_user_practices = sqlite_cursor.fetchall()
    
    for user_practice in old_user_practices:
        try:
            user = User.objects.get(id=user_practice['user_id'])
            
            sqlite_cursor.execute("SELECT * FROM kei_school_practicecard WHERE id = ?", (user_practice['practice_card_id'],))
            card_data = sqlite_cursor.fetchone()
            
            if not card_data:
                print(f"Карточка с id={user_practice['practice_card_id']} не найдена. Пропускаю изученную запись.")
                continue
            
            section = practice_to_section_mapping.get(card_data['practice_id'])
            if not section:
                print(f"Раздел словаря для practice_id={card_data['practice_id']} не найден. Пропускаю изученную запись.")
                continue
            
            entry = DictionaryEntry.objects.filter(
                section=section,
                term=card_data['text_front']
            ).first()
            
            if not entry:
                print(f"Словарная запись '{card_data['text_front']}' не найдена. Пропускаю изученную запись.")
                continue
            
            learned_entry, created = UserLearnedEntry.objects.get_or_create(
                user=user,
                entry=entry
            )
            
            if created:
                print(f"Зафиксировано изучение '{entry.term}' пользователем '{user.username}'.")

        except User.DoesNotExist:
            print(f"Пользователь с id={user_practice['user_id']} не найден. Пропускаю изученную запись.")
        except Exception as e:
            print(f"Ошибка при миграции изученной записи: {e}")

    print("\nМиграция dict_service завершена.")


def migrate_material_service(sqlite_conn):
    import os
    import shutil
    from auth_service.models import User
    from material_service.models import TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial
    from lesson_service.models import Section, SectionItem
    from django.contrib.contenttypes.models import ContentType

    print("\nНачинаю миграцию material_service (статичных материалов)...")
    sqlite_cursor = sqlite_conn.cursor()

    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()

    counts = {'images': 0, 'audio': 0, 'videos': 0, 'docs': 0, 'skipped': 0}
    old_to_material_map = {}

    for root, dirs, files in os.walk(OLD_MEDIA_ROOT):
        for fname in files:
            ext = fname.lower().rsplit('.', 1)[-1]
            old_path = os.path.join(root, fname)
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'heic', 'heif', 'hevc', 'avif']:
                ModelClass = ImageMaterial
                file_field = ModelClass.get_file_field_name()
                subdir = 'material_images'
                key = 'images'
            elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'wma', 'm4b', 'm4r', 'm4p', 'm4v', 'm4a', 'm4b', 'm4r', 'm4p', 'm4v']:
                ModelClass = AudioMaterial
                file_field = ModelClass.get_file_field_name()
                subdir = 'material_audio'
                key = 'audio'
            elif ext in ['mp4', 'mov', 'avi', 'wmv', 'webm', 'mkv', 'flv', 'vob', 'm4v', 'm4b', 'm4r', 'm4p', 'm4v']:
                ModelClass = VideoMaterial
                file_field = 'video_file'
                subdir = 'material_video'
                key = 'videos'
            elif ext in ['pdf', 'ppt', 'pptx', 'doc', 'docx', 'txt', 'md',]:
                ModelClass = DocumentMaterial
                file_field = 'document_file'
                subdir = 'material_docs'
                key = 'docs'
            else:
                ModelClass = DocumentMaterial
                file_field = 'document_file'
                subdir = 'material_docs'
                key = 'docs'

            old_rel_path = os.path.relpath(old_path, OLD_MEDIA_ROOT)
            new_file_db_path = f"{subdir}/{old_rel_path}"
            field = ModelClass._meta.get_field(file_field)
            max_len = field.max_length
            if len(new_file_db_path) > max_len:
                dirname, basename = os.path.split(new_file_db_path)
                name, dot, ext2 = basename.rpartition('.')
                allow_len = max_len - len(dirname) - 1
                if allow_len <= len(ext2) + 1:
                    basename = basename[-allow_len:]
                else:
                    basename = name[:allow_len - (len(ext2) + 1)] + "." + ext2
                new_file_db_path = os.path.join(dirname, basename)
                print(f"Нормализован путь материала: {new_file_db_path}")
            defaults = {'title': '', 'created_by': default_author}
            if file_field == 'video_file':
                defaults['source_type'] = 'file'
            try:
                material, created = ModelClass.objects.get_or_create(
                    **{file_field: new_file_db_path},
                    defaults=defaults
                )
                if created:
                    print(f"Создан {ModelClass.__name__} для файла {new_file_db_path}")
                    counts[key] += 1
                    old_to_material_map[old_rel_path] = material
            except Exception as e:
                print(f"Ошибка создания записи {ModelClass.__name__} для {new_file_db_path}: {e}")
                continue
            dest_path = os.path.join(NEW_MEDIA_ROOT, new_file_db_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(old_path, dest_path)
            except Exception as e:
                print(f"Ошибка копирования {old_path} -> {dest_path}: {e}")

    print("\nМиграция material_service (статичных материалов) завершена.")
    print("\nНачинаю привязку материалов к разделам...")
    sqlite_cursor.execute(
        """
        SELECT tm.test_id, tm.photo, tm.audio, tm.video, tm.presentation, t.lesson_id
        FROM kei_school_testmedia tm
        JOIN kei_school_test t ON tm.test_id = t.id
        """
    )
    old_media = sqlite_cursor.fetchall()
    for media in old_media:
        try:
            section = Section.objects.get(lesson_id=media['lesson_id'], order=media['test_id'])
        except Section.DoesNotExist:
            print(f"Раздел для теста id={media['test_id']} не найден. Пропускаю привязку медиа.")
            continue
        for field, item_type in [('photo','image'), ('audio','audio'), ('video','video'), ('presentation','document')]:
            path = media[field]
            if not path:
                continue
            if path not in old_to_material_map:
                print(f"Материал '{path}' не найден среди импортированных.")
                continue
            material = old_to_material_map[path]
            content_type = ContentType.objects.get_for_model(material)
            item_order = section.items.count() + 1
            SectionItem.objects.create(
                section=section,
                order=item_order,
                item_type=item_type,
                content_type=content_type,
                object_id=material.id
            )
            print(f"Привязан {item_type} материал '{path}' к разделу '{section.title}'.")
    print("Привязка материалов к разделам завершена.")
    print(f"Изображений: {counts['images']}, Аудио: {counts['audio']}, Видео: {counts['videos']}, Документов: {counts['docs']}, Пропущено: {counts['skipped']}")


def migrate_tests(sqlite_conn):
    print("\nНачинаю миграцию тестов...")
    sqlite_cursor = sqlite_conn.cursor()
    
    from material_service.models import (
        Test, MCQOption, FreeTextQuestion, WordOrderSentence, 
        MatchingPair, TestSubmission, MCQSubmissionAnswer, 
        FreeTextSubmissionAnswer, WordOrderSubmissionAnswer, 
        DragDropSubmissionAnswer
    )
    from lesson_service.models import Section, SectionItem
    from django.contrib.contenttypes.models import ContentType
    
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()
    
    old_to_material_map = {}
    
    print("Создаю маппинг материалов для тестов...")
    for root, dirs, files in os.walk(OLD_MEDIA_ROOT):
        for fname in files:
            old_path = os.path.join(root, fname)
            old_rel_path = os.path.relpath(old_path, OLD_MEDIA_ROOT)
            
            try:
                if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp')):
                    material = ImageMaterial.objects.filter(image__endswith=fname).first()
                elif fname.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                    material = AudioMaterial.objects.filter(audio_file__endswith=fname).first()
                else:
                    continue
                    
                if material:
                    old_to_material_map[old_rel_path] = material
            except Exception as e:
                print(f"Ошибка при поиске материала {fname}: {e}")
    
    type_mapping = {
        'choice_test': 'mcq-single',
        'text_test': 'free-text',
        'order_test': 'word-order',
        'correlation_test': 'drag-and-drop'
    }
    
    sqlite_cursor.execute("""
        SELECT 
            tt.id as testtype_id,
            tt.type,
            tt.ask,
            tt.test_id,
            tt.image,
            tt.audio,
            t.lesson_id,
            t.name as test_name
        FROM kei_school_testtype tt
        JOIN kei_school_test t ON tt.test_id = t.id
        ORDER BY t.lesson_id, tt.id
    """)
    old_tests = sqlite_cursor.fetchall()
    
    test_counts = {'mcq-single': 0, 'mcq-multi': 0, 'free-text': 0, 'word-order': 0, 'drag-and-drop': 0}
    
    for test_data in old_tests:
        testtype_id, old_type, question, test_id, image_path, audio_path, lesson_id, test_name = test_data
        
        try:
            section = Section.objects.get(lesson_id=lesson_id, order=test_id)
        except Section.DoesNotExist:
            print(f"Раздел для теста {testtype_id} (lesson_id={lesson_id}, test_id={test_id}) не найден. Пропускаю.")
            continue
        
        new_type = type_mapping.get(old_type)
        if not new_type:
            print(f"Неизвестный тип теста: {old_type}. Пропускаю тест {testtype_id}.")
            continue
        
        attached_image = None
        attached_audio = None
        
        if image_path:
            if image_path in old_to_material_map:
                attached_image = old_to_material_map[image_path]
            else:
                print(f"Изображение {image_path} не найдено в материалах.")
        
        if audio_path:
            if audio_path in old_to_material_map:
                attached_audio = old_to_material_map[audio_path]
            else:
                print(f"Аудио {audio_path} не найдено в материалах.")
        
        title = question[:250] if question else f"Тест {testtype_id}"
        test = Test.objects.create(
            title=title,
            description='',
            test_type=new_type,
            attached_image=attached_image,
            attached_audio=attached_audio,
            created_by=default_author
        )
        
        if old_type == 'choice_test':
            sqlite_cursor.execute("""
                SELECT 
                    a.id as answer_id,
                    a.is_correct,
                    a.explanation,
                    ac.choice_answer
                FROM kei_school_answer a
                JOIN kei_school_answerchoice ac ON ac.answer_id = a.id
                WHERE a.test_id = ?
                ORDER BY a.id
            """, (testtype_id,))
            
            choices = sqlite_cursor.fetchall()
            correct_count = sum(1 for choice in choices if choice[1])
            
            if correct_count > 1:
                test.test_type = 'mcq-multi'
                test.save()
                test_counts['mcq-multi'] += 1
            else:
                test_counts['mcq-single'] += 1
            
            for i, choice in enumerate(choices):
                MCQOption.objects.create(
                    test=test,
                    text=choice[3] or f'Вариант {i+1}',
                    is_correct=bool(choice[1]),
                    explanation=choice[2] or '',
                    order=i + 1
                )
            
            print(f"Создан MCQ тест '{title}' с {len(choices)} вариантами ответов.")
            
        elif old_type == 'text_test':
            sqlite_cursor.execute("""
                SELECT 
                    a.explanation,
                    at.text_answer
                FROM kei_school_answer a
                JOIN kei_school_answertext at ON at.answer_id = a.id
                WHERE a.test_id = ?
                LIMIT 1
            """, (testtype_id,))
            
            text_answer = sqlite_cursor.fetchone()
            if text_answer:
                FreeTextQuestion.objects.create(
                    test=test,
                    reference_answer=text_answer[1] or '',
                    explanation=text_answer[0] or ''
                )
            
            test_counts['free-text'] += 1
            print(f"Создан текстовый тест '{title}'.")
            
        elif old_type == 'order_test':
            sqlite_cursor.execute("""
                SELECT 
                    a.explanation,
                    ao.order_answer
                FROM kei_school_answer a
                JOIN kei_school_answerorder ao ON ao.answer_id = a.id
                WHERE a.test_id = ?
                ORDER BY a.id
            """, (testtype_id,))
            
            order_answers = sqlite_cursor.fetchall()
            correct_order = [answer[1] for answer in order_answers if answer[1]]
            
            if correct_order:
                all_options = list(set(correct_order))
                test.draggable_options_pool = all_options
                test.save()
                
                WordOrderSentence.objects.create(
                    test=test,
                    correct_ordered_texts=correct_order,
                    display_prompt='',
                    explanation=order_answers[0][0] or ''
                )
            
            test_counts['word-order'] += 1
            print(f"Создан тест на порядок слов '{title}' с {len(correct_order)} элементами.")
            
        elif old_type == 'correlation_test':
            sqlite_cursor.execute("""
                SELECT 
                    a.id as answer_id,
                    a.is_correct,
                    a.explanation,
                    ac.correlation_answer,
                    am.photo
                FROM kei_school_answer a
                JOIN kei_school_answercorrelation ac ON ac.answer_id = a.id
                LEFT JOIN kei_school_answermedia am ON am.answer_id = a.id
                WHERE a.test_id = ?
                ORDER BY a.id
            """, (testtype_id,))
            
            correlations = sqlite_cursor.fetchall()
            
            all_options = list(set(corr[3] for corr in correlations if corr[3]))
            test.draggable_options_pool = all_options
            test.save()
            
            for i, corr in enumerate(correlations):
                prompt_image = None
                if corr[4]:
                    if corr[4] in old_to_material_map:
                        prompt_image = old_to_material_map[corr[4]]
                
                MatchingPair.objects.create(
                    test=test,
                    prompt_text='',
                    prompt_image=prompt_image,
                    prompt_audio=None,
                    correct_answer_text=corr[3] or '',
                    order=i + 1,
                    explanation=corr[2] or ''
                )
            
            test_counts['drag-and-drop'] += 1
            print(f"Создан тест на соотнесение '{title}' с {len(correlations)} парами.")
        
        content_type = ContentType.objects.get_for_model(Test)
        item_order = section.items.count() + 1
        SectionItem.objects.create(
            section=section,
            order=item_order,
            item_type='test',
            content_type=content_type,
            object_id=test.id
        )
    
    print(f"\nМиграция тестов завершена.")
    print(f"Создано тестов:")
    for test_type, count in test_counts.items():
        print(f"  {test_type}: {count}")


def migrate_test_submissions(sqlite_conn):
    print("\nНачинаю миграцию ответов пользователей на тесты...")
    sqlite_cursor = sqlite_conn.cursor()

    from material_service.models import (
        Test, TestSubmission, MCQSubmissionAnswer, FreeTextSubmissionAnswer,
        WordOrderSubmissionAnswer, DragDropSubmissionAnswer, MCQOption,
        WordOrderSentence, MatchingPair
    )
    from lesson_service.models import Section, SectionItem
    from django.contrib.contenttypes.models import ContentType

    print("  Создаю карту соответствия старых и новых тестов...")
    old_to_new_test_map = {}
    all_new_tests = Test.objects.all()
    for new_test in all_new_tests:
        try:
            if new_test.title and 'Тест ' in new_test.title:
                old_id = int(new_test.title.split('Тест ')[-1])
                old_to_new_test_map[old_id] = new_test
        except (ValueError, IndexError):
            continue
    print(f"  Карта создана, найдено {len(old_to_new_test_map)} сопоставлений.")

    sqlite_cursor.execute("""
        SELECT ua.id, ua.user_id, ua.text, ua.test_id as testtype_id
        FROM kei_school_useranswers ua
        JOIN kei_school_testtype tt ON ua.test_id = tt.id
        WHERE tt.type = 'text_test' AND ua.text IS NOT NULL AND ua.text != ''
    """,)
    free_text_answers = sqlite_cursor.fetchall()
    text_submission_count = 0

    for answer in free_text_answers:
        try:
            user = User.objects.get(id=answer['user_id'])
            new_test = old_to_new_test_map.get(answer['testtype_id'])

            if not new_test:
                continue
            
            if TestSubmission.objects.filter(test=new_test, student=user).exists():
                continue

            submission = TestSubmission.objects.create(
                test=new_test, student=user, status='graded', score=100.0
            )
            FreeTextSubmissionAnswer.objects.create(
                submission=submission, answer_text=answer['text']
            )
            text_submission_count += 1
        except User.DoesNotExist:
            continue
        except Exception as e:
            print(f"  Ошибка при миграции текстового ответа {answer['id']}: {e}")
    print(f"  Мигрировано {text_submission_count} текстовых ответов.")

    sqlite_cursor.execute("""
        SELECT ua.user_id, ua.test_id as testtype_id
        FROM kei_school_useranswers ua
        JOIN kei_school_testtype tt ON ua.test_id = tt.id
        WHERE ua.is_complete = 1 AND tt.type != 'text_test'
    """)
    passed_answers = sqlite_cursor.fetchall()
    inferred_submission_count = 0

    for p_answer in passed_answers:
        try:
            user = User.objects.get(id=p_answer['user_id'])
            new_test = old_to_new_test_map.get(p_answer['testtype_id'])

            if not new_test:
                continue

            if TestSubmission.objects.filter(test=new_test, student=user).exists():
                continue

            submission = TestSubmission.objects.create(
                test=new_test, student=user, status='auto_passed', score=100.0
            )

            if new_test.test_type in ['mcq-single', 'mcq-multi']:
                correct_options = MCQOption.objects.filter(test=new_test, is_correct=True)
                if correct_options.exists():
                    mcq_answer = MCQSubmissionAnswer.objects.create(submission=submission)
                    mcq_answer.selected_options.set(correct_options)

            elif new_test.test_type == 'word-order':
                details = WordOrderSentence.objects.filter(test=new_test).first()
                if details:
                    WordOrderSubmissionAnswer.objects.create(
                        submission=submission,
                        submitted_order_words=details.correct_ordered_texts
                    )

            elif new_test.test_type == 'drag-and-drop':
                slots = MatchingPair.objects.filter(test=new_test)
                for slot in slots:
                    DragDropSubmissionAnswer.objects.create(
                        submission=submission, slot=slot,
                        dropped_option_text=slot.correct_answer_text, is_correct=True
                    )
            
            inferred_submission_count += 1
        except User.DoesNotExist:
            continue
        except Exception as e:
            print(f"  Ошибка при создании выведенного ответа для testtype_id {p_answer['testtype_id']}: {e}")

    print(f"  Создано {inferred_submission_count} выведенных успешных ответов.")


def migrate_section_item_views(sqlite_conn):
    print("\nНачинаю миграцию просмотров элементов секций (SectionItemView)...")
    from lesson_service.models import Lesson, SectionItem
    from auth_service.models import User
    from progress_service.models import SectionItemView

    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("SELECT user_id, lesson_id FROM kei_school_userlesson WHERE is_complete = 1")
    completed_lessons = sqlite_cursor.fetchall()

    view_count = 0
    created_views = set()

    for user_id, lesson_id in completed_lessons:
        try:
            user = User.objects.get(id=user_id)
            lesson = Lesson.objects.get(id=lesson_id)
        except (User.DoesNotExist, Lesson.DoesNotExist):
            continue

        section_items = SectionItem.objects.filter(section__lesson=lesson).exclude(item_type='test')

        for item in section_items:
            if (user.id, item.id) in created_views:
                continue

            _, created = SectionItemView.objects.get_or_create(
                user=user,
                section_item_id=item.id,
                defaults={'section_id': item.section.id}
            )
            if created:
                view_count += 1
                created_views.add((user.id, item.id))
    
    print(f"Создано {view_count} новых записей о просмотрах элементов.")


def migrate_user_learning_stats(sqlite_cursor, user, learning_stats):
    print(f"  Мигрирую LearningStats для {user.username}")
    print("    - Очки опыта будут пересчитаны на основе прогресса после миграции тестов")

    sqlite_cursor.execute("""
        SELECT complete_date as activity_date FROM kei_school_usertest WHERE user_id = ? AND is_complete = 1
        UNION
        SELECT complete_date as activity_date FROM kei_school_userlesson WHERE user_id = ? AND is_complete = 1
    """, (user.id, user.id))
    
    activity_dates = set()
    for row in sqlite_cursor.fetchall():
        if row['activity_date']:
            date_str = str(row['activity_date']).split(' ')[0]
            activity_dates.add(date_str)

    sorted_dates = sorted(list(activity_dates))

    if sorted_dates:
        total_study_days = len(sorted_dates)
        longest_streak = 0
        current_streak = 0
        
        if total_study_days > 0:
            longest_streak = 1
            current_streak = 1
            for i in range(1, len(sorted_dates)):
                prev_date = datetime.datetime.strptime(sorted_dates[i-1], '%Y-%m-%d').date()
                curr_date = datetime.datetime.strptime(sorted_dates[i], '%Y-%m-%d').date()
                if (curr_date - prev_date).days == 1:
                    current_streak += 1
                else:
                    longest_streak = max(longest_streak, current_streak)
                    current_streak = 1
            longest_streak = max(longest_streak, current_streak)

        today = timezone.now().date()
        last_activity_date = datetime.datetime.strptime(sorted_dates[-1], '%Y-%m-%d').date()
        if (today - last_activity_date).days > 1:
            current_streak = 0

        learning_stats.total_study_days = total_study_days
        learning_stats.longest_streak_days = longest_streak
        learning_stats.current_streak_days = current_streak
        print(f"    - Статистика по дням: Всего дней={total_study_days}, Макс. стрик={longest_streak}, Текущий стрик={current_streak}")

    learning_stats.save()


def recalculate_user_experience_from_progress(user, learning_stats=None):
    from progress_service.models import LearningStats, TestProgress

    if learning_stats is None:
        learning_stats, _ = LearningStats.objects.get_or_create(
            user=user,
            defaults={'level': 1}
        )

    total_experience = 0

    passed_tests = TestProgress.objects.filter(user=user, status='passed')
    for test_progress in passed_tests:
        score = test_progress.best_score if test_progress.best_score is not None else test_progress.last_score
        if score is None:
            continue
        try:
            total_experience += int(score)
        except (ValueError, TypeError):
            continue

    total_experience = max(total_experience, 0)

    learning_stats.experience_points = total_experience
    learning_stats.save(update_fields=['experience_points', 'updated_at'])
    print(f"    - Пересчитан опыт по новым правилам: {learning_stats.experience_points}")

def migrate_progress_service(sqlite_conn):
    """Миграция прогресса пользователей из старой БД"""
    print("\nНачинаю миграцию progress_service...")
    sqlite_cursor = sqlite_conn.cursor()
    
    from progress_service.models import (
        UserProgress, CourseProgress, LessonProgress, 
        SectionProgress, TestProgress, LearningStats, SectionItemView
    )
    from course_service.models import CourseEnrollment
    from lesson_service.models import Section
    from material_service.models import Test
    
    students = User.objects.filter(role=User.Role.STUDENT)
    
    for student in students:
        print(f"\nОбрабатываю прогресс для пользователя {student.username} (ID: {student.id})")
        
        user_progress, created = UserProgress.objects.get_or_create(
            user=student,
            defaults={'last_activity': timezone.now()}
        )
        
        learning_stats, created = LearningStats.objects.get_or_create(
            user=student,
            defaults={'level': 1, 'experience_points': 0}
        )
        migrate_user_learning_stats(sqlite_cursor, student, learning_stats)
        
        migrate_user_test_progress(sqlite_cursor, student, user_progress)
        recalculate_user_experience_from_progress(student, learning_stats)
        
        migrate_user_section_progress(sqlite_cursor, student, user_progress)
        
        migrate_user_lesson_progress(sqlite_cursor, student, user_progress)
        
        migrate_user_course_progress(sqlite_cursor, student, user_progress)
        
        update_user_overall_progress(student, user_progress)
        
        print(f"Прогресс для пользователя {student.username} обработан")


def migrate_user_test_progress(sqlite_cursor, user, user_progress):
    """Миграция прогресса по тестам для конкретного пользователя"""
    print(f"  Мигрирую прогресс по тестам для {user.username}")
    
    from progress_service.models import TestProgress
    from material_service.models import Test
    from lesson_service.models import Section, SectionItem
    from django.contrib.contenttypes.models import ContentType
    
    sqlite_cursor.execute("""
        SELECT 
            ua.test_id as testtype_id,
            ua.is_complete,
            tt.type as test_type,
            tt.ask as test_question,
            tt.test_id as section_test_id,
            t.name as section_name,
            t.lesson_id
        FROM kei_school_useranswers ua
        JOIN kei_school_testtype tt ON ua.test_id = tt.id
        JOIN kei_school_test t ON tt.test_id = t.id
        WHERE ua.user_id = ? AND ua.is_complete = 1
    """, (user.id,))
    
    user_tests = sqlite_cursor.fetchall()
    
    for test_data in user_tests:
        testtype_id, is_complete, test_type, test_question, section_test_id, section_name, lesson_id = test_data
        
        try:
            section = None
            try:
                section = Section.objects.get(lesson_id=lesson_id, order=section_test_id)
            except Section.DoesNotExist:
                print(f"    Секция для lesson_id={lesson_id}, section_test_id={section_test_id} не найдена")
                continue
            
            test = None
            if section:
                test_content_type = ContentType.objects.get_for_model(Test)
                section_items = SectionItem.objects.filter(
                    section=section,
                    item_type='test',
                    content_type=test_content_type
                )
                
                for section_item in section_items:
                    test_obj = section_item.content_object
                    if test_obj and test_obj.title and test_question:
                        if test_question.lower() in test_obj.title.lower() or test_obj.title.lower() in test_question.lower():
                            test = test_obj
                            break
                
                if not test and section_items.exists():
                    test = section_items.first().content_object
            
            if not test:
                print(f"    Тест '{test_question}' (testtype_id={testtype_id}) не найден в новой системе")
                continue
            
            status = 'passed' if is_complete else 'failed'
            
            section_id = section.id if section else 0
            lesson_id_new = section.lesson.id if section else 0
            course_id_new = section.lesson.course.id if section else 0
            
            test_progress, created = TestProgress.objects.get_or_create(
                user=user,
                test_id=test.id,
                defaults={
                    'test_title': test.title,
                    'test_type': test.test_type,
                    'section_id': section_id,
                    'lesson_id': lesson_id_new,
                    'course_id': course_id_new,
                    'attempts_count': 1,
                    'best_score': 100.0 if is_complete else 0.0,
                    'last_score': 100.0 if is_complete else 0.0,
                    'status': status,
                    'first_attempt_at': timezone.now(),
                    'last_attempt_at': timezone.now(),
                    'completed_at': timezone.now() if is_complete else None
                }
            )
            
            if created:
                print(f"    Создан прогресс по тесту: {test.title}")
            
        except Exception as e:
            print(f"    Ошибка при миграции теста {test_question}: {e}")


def migrate_user_section_progress(sqlite_cursor, user, user_progress):
    """Миграция прогресса по секциям для конкретного пользователя"""
    print(f"  Мигрирую прогресс по секциям для {user.username}")
    
    from progress_service.models import SectionProgress, TestProgress
    from lesson_service.models import Section
    
    sqlite_cursor.execute("""
        SELECT DISTINCT
            t.lesson_id,
            t.id as section_test_id,
            t.name as section_name,
            ut.is_complete,
            ut.complete_date
        FROM kei_school_usertest ut
        JOIN kei_school_test t ON ut.test_id = t.id
        WHERE ut.user_id = ? AND ut.is_complete = 1
    """, (user.id,))
    
    user_sections = sqlite_cursor.fetchall()
    
    for section_data in user_sections:
        lesson_id, section_test_id, section_name, is_complete, complete_date = section_data
        
        try:
            section = Section.objects.filter(lesson_id=lesson_id, order=section_test_id).first()
            
            if not section:
                print(f"    Секция для lesson_id={lesson_id}, section_test_id={section_test_id} не найдена")
                continue
            
            total_items = section.items.count()
            
            total_tests = section.items.filter(item_type='test').count()
            
            passed_tests = TestProgress.objects.filter(
                user=user,
                section_id=section.id,
                status='passed'
            ).count()
            
            failed_tests = TestProgress.objects.filter(
                user=user,
                section_id=section.id,
                status='failed'
            ).count()
            
            if is_complete:
                completion_percentage = 100.0
                completed_items = total_items 
            else:
                completion_percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0
                completed_items = passed_tests
            
            section_progress, created = SectionProgress.objects.get_or_create(
                user=user,
                section=section,
                defaults={
                    'total_items': total_items,
                    'completed_items': completed_items,
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'completion_percentage': completion_percentage,
                    'is_visited': True,
                    'visited_at': timezone.now(),
                    'started_at': timezone.now(),
                    'completed_at': timezone.now() if completion_percentage >= 100 else None,
                    'last_activity': timezone.now()
                }
            )
            
            if created:
                print(f"    Создан прогресс по секции: {section.title} ({completion_percentage:.1f}%) - завершена в старой БД: {is_complete}")
            
        except Exception as e:
            print(f"    Ошибка при миграции секции lesson_id={lesson_id}, section_test_id={section_test_id}: {e}")


def migrate_user_lesson_progress(sqlite_cursor, user, user_progress):
    """Миграция прогресса по урокам для конкретного пользователя"""
    print(f"  Мигрирую прогресс по урокам для {user.username}")
    
    from progress_service.models import LessonProgress, SectionProgress, TestProgress
    from lesson_service.models import Lesson
    
    sqlite_cursor.execute("""
        SELECT DISTINCT
            t.lesson_id,
            l.name as lesson_name
        FROM kei_school_usertest ut
        JOIN kei_school_test t ON ut.test_id = t.id
        JOIN kei_school_lesson l ON t.lesson_id = l.id
        WHERE ut.user_id = ? AND ut.is_complete = 1
    """, (user.id,))
    
    user_lessons = sqlite_cursor.fetchall()
    
    for lesson_data in user_lessons:
        lesson_id, lesson_name = lesson_data
        
        try:
            lesson = Lesson.objects.filter(id=lesson_id).first()
            
            if not lesson:
                print(f"    Урок {lesson_name} (ID: {lesson_id}) не найден в новой системе")
                continue
            
            total_sections = lesson.sections.count()
            
            completed_sections = SectionProgress.objects.filter(
                user=user,
                section__lesson=lesson,
                completion_percentage=100
            ).count()
            
            total_tests = TestProgress.objects.filter(
                user=user,
                lesson_id=lesson.id
            ).count()
            
            passed_tests = TestProgress.objects.filter(
                user=user,
                lesson_id=lesson.id,
                status='passed'
            ).count()
            
            failed_tests = TestProgress.objects.filter(
                user=user,
                lesson_id=lesson.id,
                status='failed'
            ).count()
            
            completion_percentage = (completed_sections / total_sections * 100) if total_sections > 0 else 0
            
            lesson_progress, created = LessonProgress.objects.get_or_create(
                user=user,
                lesson=lesson,
                defaults={
                    'total_sections': total_sections,
                    'completed_sections': completed_sections,
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'completion_percentage': completion_percentage,
                    'started_at': timezone.now(),
                    'completed_at': timezone.now() if completion_percentage >= 100 else None,
                    'last_activity': timezone.now()
                }
            )
            
            if created:
                print(f"    Создан прогресс по уроку: {lesson.title} ({completion_percentage:.1f}%)")
            
        except Exception as e:
            print(f"    Ошибка при миграции урока {lesson_name}: {e}")


def migrate_user_course_progress(sqlite_cursor, user, user_progress):
    """Миграция прогресса по курсам для конкретного пользователя"""
    print(f"  Мигрирую прогресс по курсам для {user.username}")
    
    from progress_service.models import CourseProgress, SectionProgress, TestProgress
    from course_service.models import Course, CourseEnrollment
    
    sqlite_cursor.execute("""
        SELECT DISTINCT
            uc.course_id,
            c.name as course_name
        FROM kei_school_usercourse uc
        JOIN kei_school_course c ON uc.course_id = c.id
        WHERE uc.user_id = ?
    """, (user.id,))
    
    user_courses = sqlite_cursor.fetchall()
    
    for course_data in user_courses:
        course_id, course_name = course_data
        
        try:
            course = Course.objects.filter(id=course_id).first()
            
            if not course:
                print(f"    Курс {course_name} (ID: {course_id}) не найден в новой системе")
                continue
            
            enrollment, created = CourseEnrollment.objects.get_or_create(
                student=user,
                course=course,
                defaults={'status': 'active'}
            )
            
            total_lessons = course.lessons.count()
            
            completed_lessons = LessonProgress.objects.filter(
                user=user,
                lesson__course=course,
                completion_percentage=100
            ).count()
            
            total_tests = TestProgress.objects.filter(
                user=user,
                course_id=course.id
            ).count()
            
            passed_tests = TestProgress.objects.filter(
                user=user,
                course_id=course.id,
                status='passed'
            ).count()
            
            failed_tests = TestProgress.objects.filter(
                user=user,
                course_id=course.id,
                status='failed'
            ).count()
            
            completion_percentage = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0
            
            total_sections = sum(lesson.sections.count() for lesson in course.lessons.all())
            
            completed_sections = SectionProgress.objects.filter(
                user=user,
                section__lesson__course=course,
                completion_percentage=100
            ).count()
            
            course_progress, created = CourseProgress.objects.get_or_create(
                user=user,
                course=course,
                defaults={
                    'total_lessons': total_lessons,
                    'completed_lessons': completed_lessons,
                    'total_sections': total_sections,
                    'completed_sections': completed_sections,
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'completion_percentage': completion_percentage,
                    'started_at': timezone.now(),
                    'completed_at': timezone.now() if completion_percentage >= 100 else None,
                    'last_activity': timezone.now()
                }
            )
            
            if created:
                print(f"    Создан прогресс по курсу: {course.title} ({completion_percentage:.1f}%)")
            
        except Exception as e:
            print(f"    Ошибка при миграции курса {course_name}: {e}")


def update_user_overall_progress(user, user_progress):
    """Обновление общей статистики пользователя"""
    print(f"  Обновляю общую статистику для {user.username}")
    
    from progress_service.models import CourseProgress, LessonProgress, SectionProgress, TestProgress
    
    user_progress.total_courses_enrolled = CourseProgress.objects.filter(user=user).count()
    user_progress.total_courses_completed = CourseProgress.objects.filter(
        user=user, completion_percentage=100
    ).count()
    user_progress.total_lessons_completed = LessonProgress.objects.filter(
        user=user, completion_percentage=100
    ).count()
    user_progress.total_sections_completed = SectionProgress.objects.filter(
        user=user, completion_percentage=100
    ).count()
    user_progress.total_tests_passed = TestProgress.objects.filter(
        user=user, status='passed'
    ).count()
    user_progress.total_tests_failed = TestProgress.objects.filter(
        user=user, status='failed'
    ).count()
    user_progress.last_activity = timezone.now()
    
    user_progress.save()
    
    print(f"    Обновлена статистика: курсов={user_progress.total_courses_enrolled}, "
          f"уроков={user_progress.total_lessons_completed}, "
          f"тестов={user_progress.total_tests_passed}")


def migrate_achievements(sqlite_conn):
    print("\nНачинаю миграцию достижений...")
    sqlite_cursor = sqlite_conn.cursor()
    
    from achievement_service.models import Achievement, UserAchievement
    
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'
    
    # Hardcoded achievements based on legacy DB
    # Creating rule_graph with trigger and condition nodes
    # NOTE: lesson_id values updated to match new PostgreSQL database
    achievements_data = [
        {
            'id': 4,
            'title': 'Первопроходец',
            'description': 'Прохождение первого урока на 100％',
            'xp_reward': 10,
            'icon_src': 'achivement_icons/photo_2024-08-17_10-38-56.jpg',
            'rule_graph': {
                'nodes': [
                    {
                        'id': 'trigger-1',
                        'type': 'trigger',
                        'data': {'trigger': 'ON_LESSON_COMPLETE'},
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'condition-1',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 4  # Урок 1 в новой БД
                        },
                        'position': {'x': 100, 'y': 200}
                    },
                    {
                        'id': 'condition-2',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 1  # Введение
                        },
                        'position': {'x': 300, 'y': 200}
                    },
                    {
                        'id': 'logic-1',
                        'type': 'logic',
                        'data': {
                            'logic_type': 'OR'
                        },
                        'position': {'x': 200, 'y': 350}
                    }
                ],
                'edges': [
                    {
                        'id': 'e1',
                        'source': 'trigger-1',
                        'target': 'condition-1'
                    },
                    {
                        'id': 'e2',
                        'source': 'trigger-1',
                        'target': 'condition-2'
                    },
                    {
                        'id': 'e3',
                        'source': 'condition-1',
                        'target': 'logic-1'
                    },
                    {
                        'id': 'e4',
                        'source': 'condition-2',
                        'target': 'logic-1'
                    }
                ]
            }
        },
        {
            'id': 6,
            'title': 'Выжить в Японии',
            'description': 'Пройти 18 уроков',
            'xp_reward': 100,
            'icon_src': 'achivement_icons/photo_2024-08-17_11-46-50.jpg',
            'rule_graph': {
                'nodes': [
                    {
                        'id': 'trigger-1',
                        'type': 'trigger',
                        'data': {'trigger': 'ON_LESSON_COMPLETE'},
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'condition-1',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 25  # Урок 18 в новой БД
                        },
                        'position': {'x': 100, 'y': 200}
                    }
                ],
                'edges': [
                    {
                        'id': 'e1',
                        'source': 'trigger-1',
                        'target': 'condition-1'
                    }
                ]
            }
        },
        {
            'id': 7,
            'title': 'Тысяча и один иероглиф',
            'description': 'Изучить 100 иероглифов',
            'xp_reward': 150,
            'icon_src': 'achivement_icons/photo_2024-08-17_11-47-01.jpg',
            'rule_graph': {
                'nodes': [
                    {
                        'id': 'trigger-1',
                        'type': 'trigger',
                        'data': {'trigger': 'ON_LESSON_COMPLETE'},
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'condition-1',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 34  # Урок 27 в новой БД
                        },
                        'position': {'x': 100, 'y': 200}
                    }
                ],
                'edges': [
                    {
                        'id': 'e1',
                        'source': 'trigger-1',
                        'target': 'condition-1'
                    }
                ]
            }
        },
        {
            'id': 8,
            'title': 'Это база! ',
            'description': 'Выучить хирагану и катакану',
            'xp_reward': 10,
            'icon_src': 'achivement_icons/photo_14_2024-08-17_11-53-35_wq0TlpT.jpg',
            'rule_graph': {
                'nodes': [
                    {
                        'id': 'trigger-1',
                        'type': 'trigger',
                        'data': {'trigger': 'ON_LESSON_COMPLETE'},
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'condition-1',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 4  # Урок 1 в новой БД
                        },
                        'position': {'x': 100, 'y': 200}
                    }
                ],
                'edges': [
                    {
                        'id': 'e1',
                        'source': 'trigger-1',
                        'target': 'condition-1'
                    }
                ]
            }
        },
        {
            'id': 9,
            'title': 'Опять твои китайцы!',
            'description': 'Пройти первый диалог с виртуальным сенсеем',
            'xp_reward': 15,
            'icon_src': 'achivement_icons/photo_11_2024-08-17_11-53-35.jpg',
            'rule_graph': {
                'nodes': [
                    {
                        'id': 'trigger-1',
                        'type': 'trigger',
                        'data': {'trigger': 'ON_LESSON_COMPLETE'},
                        'position': {'x': 100, 'y': 100}
                    },
                    {
                        'id': 'condition-1',
                        'type': 'condition',
                        'data': {
                            'variable': 'event.lesson_id',
                            'operator': '==',
                            'value': 4  # Урок 1 в новой БД
                        },
                        'position': {'x': 100, 'y': 200}
                    }
                ],
                'edges': [
                    {
                        'id': 'e1',
                        'source': 'trigger-1',
                        'target': 'condition-1'
                    }
                ]
            }
        }
    ]
    
    achievement_map = {} # old_id -> new_achievement_obj
    
    print("Создаю/обновляю достижения...")
    for ach_data in achievements_data:
        old_icon_path = ach_data['icon_src']
        new_icon_db_path = None
        
        if old_icon_path:
            source_path = os.path.join(OLD_MEDIA_ROOT, old_icon_path)
            # achievements/icons/<filename>
            filename = os.path.basename(old_icon_path)
            new_rel_path = os.path.join('achievements', 'icons', filename)
            dest_path = os.path.join(NEW_MEDIA_ROOT, new_rel_path)
            
            if os.path.exists(source_path):
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(source_path, dest_path)
                new_icon_db_path = new_rel_path.replace('\\', '/') 
                print(f"  Скопирована иконка для '{ach_data['title']}'")
            else:
                print(f"  Иконка не найдена: {source_path}")
        
        achievement, created = Achievement.objects.update_or_create(
            title=ach_data['title'],
            defaults={
                'description': ach_data['description'],
                'xp_reward': ach_data['xp_reward'],
                'icon': new_icon_db_path,
                'rule_graph': ach_data['rule_graph'],
                'is_active': True
            }
        )
        
        achievement_map[ach_data['id']] = achievement
        
        if created:
            print(f"  Создано достижение: {achievement.title}")
        else:
            print(f"  Обновлено достижение: {achievement.title}")

    print("\nМигрирую полученные достижения пользователей...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userachievement")
    old_user_achievements = sqlite_cursor.fetchall()
    
    count_awarded = 0
    for ua_data in old_user_achievements:
        old_ach_id = ua_data['achievement_id']
        user_id = ua_data['user_id']
        achieved_at = ua_data['achieved_at']
        
        if old_ach_id not in achievement_map:
            print(f"  Пропущено: достижение с ID {old_ach_id} не в списке миграции.")
            continue
            
        try:
            user = User.objects.get(id=user_id)
            achievement = achievement_map[old_ach_id]

            ua, created = UserAchievement.objects.get_or_create(
                user=user,
                achievement=achievement,
            )
            
            if created:
                
                ua.awarded_at = achieved_at
                ua.save()
                count_awarded += 1
                print(f"  Выдано '{achievement.title}' пользователю {user.username}")
            else:
                 ua.awarded_at = achieved_at
                 ua.save()
        
        except User.DoesNotExist:
            print(f"  Пользователь с ID {user_id} не найден.")
        except Exception as e:
            print(f"  Ошибка при выдаче достижения: {e}")
            
    print(f"Миграция достижений завершена. Выдано: {count_awarded}")


def migrate_user_levels_and_coins(sqlite_conn):
    print("\nНачинаю миграцию уровней и монеток...")
    
    stats_list = LearningStats.objects.all()
    count = 0
    for stats in stats_list:
        stats.coins = stats.experience_points
        
        new_level = stats.calculate_level()
        stats.level = new_level
        
        stats.save()
        count += 1
        print(f"Обновлен пользователь {stats.user.username}: XP={stats.experience_points}, Coins={stats.coins}, Level={stats.level}")

    print(f"Миграция уровней и монеток завершена. Обновлено: {count}")


def migrate_bonus_service(sqlite_conn):
    print("\nНачинаю миграцию bonus_service...")
    sqlite_cursor = sqlite_conn.cursor()
    
    from bonus_service.models import Bonus
    from material_service.models import VideoMaterial
    from auth_service.models import User
    import shutil
    
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = settings.MEDIA_ROOT
    
    print("Мигрирую бонусы...")
    sqlite_cursor.execute("SELECT * FROM kei_school_bonus")
    old_bonuses = sqlite_cursor.fetchall()
    
    for bonus_data in old_bonuses:
        try:
            old_video_path = bonus_data['video']
            new_video_material = None
            
            if old_video_path:
                old_file_full_path = os.path.join(OLD_MEDIA_ROOT, old_video_path)
                
                if os.path.exists(old_file_full_path):
                    filename = os.path.basename(old_video_path)
                    
                    # material_video/filename (strip bonuses_videos/ prefix)
                    new_relative_path = f"material_video/{filename}"
                    new_file_full_path = os.path.join(NEW_MEDIA_ROOT, new_relative_path)
                    
                    os.makedirs(os.path.dirname(new_file_full_path), exist_ok=True)
                    
                    shutil.copy2(old_file_full_path, new_file_full_path)
                    print(f"  Скопирован видео файл: {old_video_path} -> {new_relative_path}")
                    
                    new_video_material = VideoMaterial.objects.create(
                        title=f"Бонус: {bonus_data['title']}",
                        source_type='file',
                        video_file=new_relative_path,
                        created_by=User.objects.filter(is_staff=True).first()
                    )
                else:
                    print(f"  Видео файл для бонуса '{bonus_data['title']}' не найден по пути: {old_file_full_path}")
            
            Bonus.objects.create(
                title=bonus_data['title'],
                description=bonus_data['description'],
                price=100,
                bonus_type='video',
                video_material=new_video_material
            )
            print(f"Создан бонус '{bonus_data['title']}'.")
            
        except Exception as e:
            print(f"Ошибка миграции бонуса {bonus_data.get('title')}: {e}")

    print("Миграция bonus_service завершена.")



if __name__ == '__main__':
    sqlite_conn = get_sqlite_connection()
    postgres_conn = get_postgres_connection()

    if sqlite_conn and postgres_conn:
        migrate_users(sqlite_conn)
        migrate_groups_and_permissions(sqlite_conn)
        migrate_user_service(sqlite_conn)
        migrate_course_service(sqlite_conn)
        migrate_lesson_service(sqlite_conn)
        migrate_sections(sqlite_conn)
        migrate_section_texts(sqlite_conn)
        migrate_dict_service(sqlite_conn)
        migrate_material_service(sqlite_conn)
        migrate_tests(sqlite_conn)
        migrate_test_submissions(sqlite_conn)
        migrate_section_item_views(sqlite_conn)
        migrate_progress_service(sqlite_conn)
        migrate_achievements(sqlite_conn)
        migrate_bonus_service(sqlite_conn)
        migrate_user_levels_and_coins(sqlite_conn)

    if sqlite_conn:
        sqlite_conn.close()
    if postgres_conn:
        postgres_conn.close()