import os
import sys
import psycopg2
import sqlite3
import django
import shutil

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kei_backend'))

# Настройка Django для доступа к моделям
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

# --- НАСТРОЙКИ ---
# Старая база данных SQLite
SQLITE_DB_PATH = 'to_migrate/db.sqlite3'

# Новая база данных PostgreSQL (данные из docker-compose.yml)
POSTGRES_DB_NAME = "kei_db"
POSTGRES_USER = "kei_user"
POSTGRES_PASSWORD = "kei_password"
POSTGRES_HOST = "postgres" # Имя сервиса из docker-compose
POSTGRES_PORT = "5432"
# --- КОНЕЦ НАСТРОЕК ---

def get_sqlite_connection():
    """Подключается к базе данных SQLite."""
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        print("Успешное подключение к SQLite.")
        return conn
    except sqlite3.Error as e:
        print(f"Ошибка подключения к SQLite: {e}")
        return None

def get_postgres_connection():
    """Подключается к базе данных PostgreSQL."""
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
    """Мигрирует пользователей из SQLite в PostgreSQL, исправляя username и роли."""
    print("\nНачинаю миграцию/обновление пользователей (username и роли)...")
    sqlite_cursor = sqlite_conn.cursor()
    # Объединяем с userinfo, чтобы получить nickname
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
            # Если пользователь не найден в новой базе, создаем нового пользователя
            if not user_to_update:
                # Определяем роль на основе старых данных
                if old_user_data['is_superuser']:
                    new_role = User.Role.ADMIN
                elif old_user_data['is_staff']:
                    new_role = User.Role.TEACHER
                else:
                    new_role = User.Role.STUDENT

                # Определяем username (nickname если есть, иначе старый username)
                new_username = old_user_data['nickname'] if old_user_data['nickname'] else old_user_data['old_username']

                # Обеспечиваем уникальность username
                base_username = new_username
                unique_username = base_username
                suffix_i = 1
                while User.objects.filter(username__iexact=unique_username).exists():
                    unique_username = f"{base_username}_{suffix_i}"
                    suffix_i += 1
                new_username = unique_username

                # Создаем нового пользователя
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

            # --- Логика определения роли ---
            if old_user_data['is_superuser']:
                new_role = User.Role.ADMIN
            elif old_user_data['is_staff']:
                new_role = User.Role.TEACHER
            else:
                new_role = User.Role.STUDENT
            # --- Конец логики ---

            new_username = old_user_data['nickname'] if old_user_data['nickname'] else old_user_data['old_username']
            
            username_changed = user_to_update.username != new_username
            role_changed = user_to_update.role != new_role

            if not username_changed and not role_changed:
                print(f"Данные для {user_to_update.email} уже корректны. Пропускаю.")
                skipped_count += 1
                continue

            fields_to_update = []
            if username_changed:
                # Проверяем на конфликт username перед сохранением
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
    """Мигрирует группы и их связи с пользователями."""
    print("\nНачинаю миграцию групп и связей...")
    sqlite_cursor = sqlite_conn.cursor()

    # Миграция групп
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

    # Миграция связей пользователь-группа
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
    """Мигрирует данные для UserProfile и UserSettings, включая аватары."""
    print("\nНачинаю миграцию user_service...")
    sqlite_cursor = sqlite_conn.cursor()

    # Пути к медиа-папкам внутри контейнера
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    # Миграция UserProfile из старой UserInfo
    print("Мигрирую UserProfile (включая аватары)...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userinfo")
    old_user_infos = sqlite_cursor.fetchall()
    for info in old_user_infos:
        try:
            user = User.objects.get(id=info['user_id'])
            
            # --- Миграция файла аватара ---
            old_avatar_relative_path = info['avatar']
            new_avatar_db_path = None  # Путь для записи в БД по умолчанию

            if old_avatar_relative_path:
                source_path = os.path.join(OLD_MEDIA_ROOT, old_avatar_relative_path)
                dest_path = os.path.join(NEW_MEDIA_ROOT, old_avatar_relative_path)
                
                if os.path.exists(source_path):
                    # Убедимся, что директория для нового файла существует
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)  # copy2 сохраняет метаданные
                    new_avatar_db_path = old_avatar_relative_path  # Путь в БД - относительный
                    print(f"Скопирован аватар для '{user.username}'.")
                else:
                    print(f"Файл аватара не найден: {source_path}")
            # --- Конец миграции файла ---

            # Используем update_or_create для идемпотентного создания/обновления
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

    # Миграция UserSettings (логика остается прежней)
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
    """Мигрирует данные для Course, CourseEnrollment и CourseTeacher."""
    print("\nНачинаю миграцию course_service...")
    sqlite_cursor = sqlite_conn.cursor()

    # Пути к медиа-папкам внутри контейнера
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    # 1. Миграция основных данных курсов
    print("Мигрирую курсы...")
    # Ищем автора по умолчанию (первый админ или учитель)
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()
    
    status_mapping = {
        'Открыт': 'published',
        'Закрыт': 'draft',
    }

    sqlite_cursor.execute("SELECT * FROM kei_school_course")
    old_courses = sqlite_cursor.fetchall()
    for course_data in old_courses:
        # --- Миграция изображения курса ---
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
        # --- Конец миграции изображения ---

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

    # 2. Миграция связей пользователей с курсами
    print("\nМигрирую связи пользователей с курсами...")
    sqlite_cursor.execute("SELECT * FROM kei_school_usercourse")
    old_enrollments = sqlite_cursor.fetchall()
    for enroll_data in old_enrollments:
        try:
            user = User.objects.get(id=enroll_data['user_id'])
            course = Course.objects.get(id=enroll_data['course_id'])

            # Создаем CourseEnrollment для всех
            enrollment, created = CourseEnrollment.objects.get_or_create(
                student=user,
                course=course
            )
            if created:
                print(f"Пользователь '{user.username}' записан на курс '{course.title}'.")
            
            # Если пользователь - учитель или админ, делаем его CourseTeacher
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
    """Мигрирует данные для Lesson, Section и LessonCompletion."""
    print("\nНачинаю миграцию lesson_service...")
    sqlite_cursor = sqlite_conn.cursor()

    # Пути к медиа-папкам
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'
    
    # Автор по умолчанию для уроков
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()

    # 1. Миграция уроков и создание одного раздела для каждого
    print("Мигрирую уроки и создаю разделы...")
    sqlite_cursor.execute("SELECT * FROM kei_school_lesson")
    old_lessons = sqlite_cursor.fetchall()
    for lesson_data in old_lessons:
        try:
            course = Course.objects.get(id=lesson_data['course_id'])

            # --- Миграция изображения урока ---
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
            # --- Конец миграции изображения ---

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

    # 2. Миграция прогресса прохождения уроков
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
    """
    Мигрирует разделы (Section) из старой таблицы Test (kei_school_test).
    Только структуры разделов, без содержимого.
    """
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
    """Мигрирует текстовые материалы разделов из старой таблицы Test."""
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
    """Мигрирует данные словаря из старой таблицы Practice и PracticeCard."""
    print("\nНачинаю миграцию dict_service...")
    sqlite_cursor = sqlite_conn.cursor()

    # Пути к медиа-папкам внутри контейнера
    OLD_MEDIA_ROOT = 'to_migrate/media'
    NEW_MEDIA_ROOT = 'media'

    # Автор по умолчанию для словарных записей
    default_author = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).first()

    # 1. Миграция разделов словаря (DictionarySection) из kei_school_practice
    print("Мигрирую разделы словаря...")
    sqlite_cursor.execute("SELECT * FROM kei_school_practice")
    old_practices = sqlite_cursor.fetchall()
    
    practice_to_section_mapping = {}  # Для связи старых practice_id с новыми section_id
    
    for practice_data in old_practices:
        try:
            course = Course.objects.get(id=practice_data['course_id'])
            
            # --- Миграция изображения раздела ---
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
            # --- Конец миграции изображения ---

            # Определяем, является ли раздел основным (первый раздел курса)
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

    # 2. Миграция словарных записей (DictionaryEntry) из kei_school_practicecard
    print("\nМигрирую словарные записи...")
    sqlite_cursor.execute("SELECT * FROM kei_school_practicecard")
    old_practice_cards = sqlite_cursor.fetchall()
    
    for card_data in old_practice_cards:
        try:
            # Получаем соответствующий раздел словаря
            section = practice_to_section_mapping.get(card_data['practice_id'])
            if not section:
                print(f"Раздел словаря для practice_id={card_data['practice_id']} не найден. Пропускаю карточку.")
                continue

            # Получаем урок, если указан target_lesson_id
            lesson = None
            if card_data['target_lesson_id']:
                try:
                    lesson = Lesson.objects.get(id=card_data['target_lesson_id'])
                except Lesson.DoesNotExist:
                    print(f"Урок с id={card_data['target_lesson_id']} не найден. Карточка будет без привязки к уроку.")

            # --- Миграция аудио файла ---
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
            # --- Конец миграции аудио ---

            # Создаем словарную запись
            # text_front -> term (кандзи/слово)
            # text_back -> reading (произношение)
            # description_back -> translation (перевод)
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

    # 3. Миграция изученных записей (UserLearnedEntry) из kei_school_userpractice
    print("\nМигрирую изученные записи...")
    sqlite_cursor.execute("SELECT * FROM kei_school_userpractice WHERE is_complete = 1")
    old_user_practices = sqlite_cursor.fetchall()
    
    for user_practice in old_user_practices:
        try:
            user = User.objects.get(id=user_practice['user_id'])
            
            # Находим соответствующую словарную запись
            # Для этого нужно найти карточку по practice_card_id и затем найти запись
            sqlite_cursor.execute("SELECT * FROM kei_school_practicecard WHERE id = ?", (user_practice['practice_card_id'],))
            card_data = sqlite_cursor.fetchone()
            
            if not card_data:
                print(f"Карточка с id={user_practice['practice_card_id']} не найдена. Пропускаю изученную запись.")
                continue
            
            # Находим раздел словаря
            section = practice_to_section_mapping.get(card_data['practice_id'])
            if not section:
                print(f"Раздел словаря для practice_id={card_data['practice_id']} не найден. Пропускаю изученную запись.")
                continue
            
            # Находим словарную запись
            entry = DictionaryEntry.objects.filter(
                section=section,
                term=card_data['text_front']
            ).first()
            
            if not entry:
                print(f"Словарная запись '{card_data['text_front']}' не найдена. Пропускаю изученную запись.")
                continue
            
            # Создаем запись об изучении
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
    """Мигрирует статичные материалы: текст, изображения, аудио, видео, документы."""
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
    # Словарь для маппинга старого пути к импортированному материалу
    old_to_material_map = {}

    for root, dirs, files in os.walk(OLD_MEDIA_ROOT):
        for fname in files:
            ext = fname.lower().rsplit('.', 1)[-1]
            old_path = os.path.join(root, fname)
            # Определяем класс материала по расширению (все форматы поддерживаются)
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
                # Остальные форматы считаем документами
                ModelClass = DocumentMaterial
                file_field = 'document_file'
                subdir = 'material_docs'
                key = 'docs'

            # Подготовка пути для поля в БД (используем относительный путь из OLD_MEDIA_ROOT)
            old_rel_path = os.path.relpath(old_path, OLD_MEDIA_ROOT)
            new_file_db_path = f"{subdir}/{old_rel_path}"
            # Ограничиваем длину пути согласно max_length поля
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
            # Создание записи в БД
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
                    # Запоминаем материал для последующей привязки
                    old_to_material_map[old_rel_path] = material
            except Exception as e:
                print(f"Ошибка создания записи {ModelClass.__name__} для {new_file_db_path}: {e}")
                continue
            # Копирование файла после создания записи
            dest_path = os.path.join(NEW_MEDIA_ROOT, new_file_db_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(old_path, dest_path)
            except Exception as e:
                print(f"Ошибка копирования {old_path} -> {dest_path}: {e}")

    print("\nМиграция material_service (статичных материалов) завершена.")
    # Привязка материалов к разделам на основе старой БД
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

    if sqlite_conn:
        sqlite_conn.close()
    if postgres_conn:
        postgres_conn.close() 