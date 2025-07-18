import os
import sys
import psycopg2
import sqlite3
import django

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kei_backend'))

# Настройка Django для доступа к моделям
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kei_backend.settings")
django.setup()

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from auth_service.models import User

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
    """Мигрирует пользователей из SQLite в PostgreSQL, исправляя username."""
    print("\nНачинаю миграцию/обновление пользователей...")
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
            # Ищем пользователя в новой БД по email, так как он должен быть уникальным
            user_to_update = User.objects.filter(email__iexact=old_user_data['email']).first()
            
            if not user_to_update:
                print(f"Пользователь с email {old_user_data['email']} не найден в новой базе. Пропускаю.")
                skipped_count += 1
                continue

            new_username = old_user_data['nickname'] if old_user_data['nickname'] else old_user_data['old_username']

            if user_to_update.username == new_username:
                print(f"Username для {user_to_update.email} уже корректен ('{new_username}'). Пропускаю.")
                skipped_count += 1
                continue

            # Проверяем на конфликт username перед сохранением
            if User.objects.filter(username__iexact=new_username).exclude(pk=user_to_update.pk).exists():
                print(f"Новый username '{new_username}' для пользователя {user_to_update.email} уже занят другим пользователем. Пропускаю.")
                skipped_count += 1
                continue

            print(f"Обновляю username для {user_to_update.email}: '{user_to_update.username}' -> '{new_username}'")
            user_to_update.username = new_username
            user_to_update.save(update_fields=['username'])
            updated_count += 1
            
        except Exception as e:
            print(f"Ошибка при обновлении пользователя с email {old_user_data.get('email', 'N/A')}: {e}")
            skipped_count += 1

    print(f"\nОбновление пользователей завершено.")
    print(f"Обновлено: {updated_count}")
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


if __name__ == '__main__':
    sqlite_conn = get_sqlite_connection()
    postgres_conn = get_postgres_connection()

    if sqlite_conn and postgres_conn:
        migrate_users(sqlite_conn)
        migrate_groups_and_permissions(sqlite_conn)

    if sqlite_conn:
        sqlite_conn.close()
    if postgres_conn:
        postgres_conn.close() 