import os
import sqlite3
import shutil
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.contrib.contenttypes.models import ContentType
from django.db import models

from auth_service.models import User
from user_service.models import UserProfile, UserSettings
from course_service.models import Course, CourseTeacher, CourseEnrollment
from lesson_service.models import Lesson, Section, SectionItem
from dict_service.models import DictionarySection, DictionaryEntry, UserLearnedEntry
from material_service.models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial,
    Test, MCQOption, FreeTextQuestion, WordOrderSentence, MatchingPair
)


class Command(BaseCommand):
    help = 'Мигрирует данные из старой SQLite базы в новую PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite-path',
            type=str,
            default='to_migrate/db.sqlite3',
            help='Путь к старой SQLite базе данных'
        )
        parser.add_argument(
            '--media-path',
            type=str,
            default='to_migrate/media/',
            help='Путь к старым медиа файлам'
        )

    def handle(self, *args, **options):
        sqlite_path = options['sqlite_path']
        media_path = options['media_path']
        
        if not os.path.exists(sqlite_path):
            self.stdout.write(
                self.style.ERROR(f'SQLite база данных не найдена: {sqlite_path}')
            )
            return

        self.stdout.write('Начинаю миграцию данных...')
        
        # Подключение к SQLite
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        cursor = conn.cursor()
        
        try:
            with transaction.atomic():
                self.migrate_users(cursor, media_path)
                self.migrate_courses(cursor, media_path)
                self.migrate_lessons(cursor, media_path)
                self.migrate_dictionaries(cursor, media_path)
                self.migrate_lesson_content(cursor, media_path)
                self.migrate_standalone_materials(cursor, media_path)
                
            self.stdout.write(
                self.style.SUCCESS('Миграция данных успешно завершена!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка миграции: {str(e)}')
            )
        finally:
            conn.close()

    def migrate_users(self, cursor, media_path):
        self.stdout.write('Мигрирую пользователей...')
        
        # Проверяем, есть ли уже пользователи в базе
        if User.objects.count() > 0:
            self.stdout.write('Пользователи уже мигрированы, пропускаю...')
            return
        
        # Получаем данные из старой базы
        cursor.execute('''
            SELECT 
                u.id,
                u.email,
                u.password,
                u.is_staff,
                u.is_superuser,
                ui.nickname,
                ui.phone_number,
                ui.avatar,
                us.show_completed_answers
            FROM auth_user u
            LEFT JOIN kei_school_userinfo ui ON u.id = ui.user_id
            LEFT JOIN kei_school_usersettings us ON u.id = us.user_id
        ''')
        
        old_users = cursor.fetchall()
        
        for old_user in old_users:
            # Определяем роль пользователя
            if old_user['is_superuser']:
                role = User.Role.ADMIN
            elif old_user['is_staff']:
                role = User.Role.TEACHER
            else:
                role = User.Role.STUDENT

            # Создаем нового пользователя
            base_username = old_user['nickname'] if old_user['nickname'] else f"user{old_user['id']}"
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
                
            user, created = User.objects.get_or_create(
                email=old_user['email'],
                defaults={
                    'password': old_user['password'],  # Пароли уже хешированы
                    'role': role,
                    'is_active': True,
                    'username': username,
                    'is_staff': old_user['is_staff'],
                    'is_superuser': old_user['is_superuser']
                }
            )
            
            if created:
                self.stdout.write(f'Создан пользователь: {user.email}')
                
                # Создаем профиль пользователя
                profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'phone_number': old_user['phone_number'] or '',
                    }
                )
                
                # Копируем аватар если есть
                if old_user['avatar'] and profile_created:
                    old_avatar_path = os.path.join(media_path, old_user['avatar'])
                    if os.path.exists(old_avatar_path):
                        try:
                            with open(old_avatar_path, 'rb') as f:
                                avatar_name = os.path.basename(old_user['avatar'])
                                profile.avatar.save(avatar_name, File(f), save=True)
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось скопировать аватар для {user.email}: {e}')
                            )
                
                # Создаем настройки пользователя
                settings_obj, settings_created = UserSettings.objects.get_or_create(
                    user=user,
                    defaults={
                        'show_test_answers': old_user['show_completed_answers'] if old_user['show_completed_answers'] is not None else True,
                        'show_learned_items': True,  # По умолчанию
                        'theme': 'light'  # По умолчанию
                    }
                )
            else:
                self.stdout.write(f'Пользователь уже существует: {user.email}')

    def migrate_courses(self, cursor, media_path):
        self.stdout.write('Мигрирую курсы...')
        
        # Получаем данные курсов из старой базы
        cursor.execute('''
            SELECT 
                id,
                name,
                description,
                image,
                short_description,
                status
            FROM kei_school_course
        ''')
        
        old_courses = cursor.fetchall()
        
        for old_course in old_courses:
            # Маппинг статусов
            status_mapping = {
                'Открыт': 'free',
                'Закрыт': 'draft'
            }
            
            new_status = status_mapping.get(old_course['status'], 'free')
            
            course, created = Course.objects.get_or_create(
                title=old_course['name'] or f'Курс {old_course["id"]}',
                defaults={
                    'subtitle': old_course['short_description'] or '',
                    'description': old_course['description'] or '',
                    'status': new_status,
                }
            )
            
            if created:
                self.stdout.write(f'Создан курс: {course.title}')
                
                # Копируем изображение курса если есть
                if old_course['image']:
                    old_image_path = os.path.join(media_path, old_course['image'])
                    if os.path.exists(old_image_path):
                        try:
                            with open(old_image_path, 'rb') as f:
                                image_name = os.path.basename(old_course['image'])
                                course.cover_image.save(image_name, File(f), save=True)
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось скопировать изображение для курса {course.title}: {e}')
                            )
                
                # Мигрируем связи CourseTeacher для преподавателей
                cursor.execute('''
                    SELECT DISTINCT u.email
                    FROM auth_user u
                    WHERE u.is_staff = 1
                ''')
                
                teachers = cursor.fetchall()
                for teacher_row in teachers:
                    try:
                        teacher = User.objects.get(email=teacher_row['email'])
                        CourseTeacher.objects.get_or_create(
                            course=course,
                            teacher=teacher,
                            defaults={'is_primary': True}
                        )
                    except User.DoesNotExist:
                        continue
                
                # Мигрируем UserCourse в CourseEnrollment
                cursor.execute('''
                    SELECT u.email
                    FROM kei_school_usercourse uc
                    JOIN auth_user u ON u.id = uc.user_id
                    WHERE uc.course_id = ?
                ''', (old_course['id'],))
                
                enrolled_users = cursor.fetchall()
                for user_row in enrolled_users:
                    try:
                        student = User.objects.get(email=user_row['email'])
                        CourseEnrollment.objects.get_or_create(
                            course=course,
                            student=student,
                            defaults={'status': 'active'}
                        )
                    except User.DoesNotExist:
                        continue
            else:
                self.stdout.write(f'Курс уже существует: {course.title}')

    def migrate_lessons(self, cursor, media_path):
        self.stdout.write('Мигрирую уроки...')
        
        # Получаем данные уроков из старой базы
        cursor.execute('''
            SELECT 
                l.id,
                l.course_id,
                l.name,
                l.image,
                c.name as course_name
            FROM kei_school_lesson l
            JOIN kei_school_course c ON c.id = l.course_id
        ''')
        
        old_lessons = cursor.fetchall()
        
        for old_lesson in old_lessons:
            try:
                # Находим соответствующий курс в новой базе
                course = Course.objects.get(title=old_lesson['course_name'])
                
                lesson, created = Lesson.objects.get_or_create(
                    course=course,
                    title=old_lesson['name'] or f'Урок {old_lesson["id"]}',
                    defaults={}
                )
                
                if created:
                    self.stdout.write(f'Создан урок: {lesson.title} в курсе {course.title}')
                    
                    # Копируем изображение урока если есть
                    if old_lesson['image']:
                        old_image_path = os.path.join(media_path, old_lesson['image'])
                        if os.path.exists(old_image_path):
                            try:
                                with open(old_image_path, 'rb') as f:
                                    image_name = os.path.basename(old_lesson['image'])
                                    lesson.cover_image.save(image_name, File(f), save=True)
                            except Exception as e:
                                self.stdout.write(
                                    self.style.WARNING(f'Не удалось скопировать изображение для урока {lesson.title}: {e}')
                                )
                else:
                    self.stdout.write(f'Урок уже существует: {lesson.title}')
                    
            except Course.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Не найден курс для урока: {old_lesson["name"]}')
                )
                continue

    def migrate_dictionaries(self, cursor, media_path):
        self.stdout.write('Мигрирую словари...')
        
        # Получаем данные практик из старой базы
        cursor.execute('''
            SELECT 
                p.id,
                p.name,
                p.image,
                p.course_id,
                c.name as course_name
            FROM kei_school_practice p
            JOIN kei_school_course c ON c.id = p.course_id
        ''')
        
        old_practices = cursor.fetchall()
        
        for old_practice in old_practices:
            try:
                # Находим соответствующий курс в новой базе
                course = Course.objects.get(title=old_practice['course_name'])
                
                section, created = DictionarySection.objects.get_or_create(
                    course=course,
                    title=old_practice['name'] or f'Словарь {old_practice["id"]}',
                    defaults={'is_primary': True}  # Делаем основным разделом курса
                )
                
                if created:
                    self.stdout.write(f'Создан раздел словаря: {section.title} для курса {course.title}')
                    
                    # Копируем изображение раздела если есть
                    if old_practice['image']:
                        old_image_path = os.path.join(media_path, old_practice['image'])
                        if os.path.exists(old_image_path):
                            try:
                                with open(old_image_path, 'rb') as f:
                                    image_name = os.path.basename(old_practice['image'])
                                    section.banner_image.save(image_name, File(f), save=True)
                            except Exception as e:
                                self.stdout.write(
                                    self.style.WARNING(f'Не удалось скопировать изображение для раздела {section.title}: {e}')
                                )
                else:
                    self.stdout.write(f'Раздел словаря уже существует: {section.title}')
                
                # Мигрируем карточки практик
                self.migrate_practice_cards(cursor, media_path, old_practice['id'], section)
                
            except Course.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Не найден курс для практики: {old_practice["name"]}')
                )
                continue

    def migrate_practice_cards(self, cursor, media_path, old_practice_id, section):
        # Получаем карточки практик из старой базы
        cursor.execute('''
            SELECT 
                pc.id,
                pc.text_front,
                pc.text_back,
                pc.description_back,
                pc.audio,
                pc.hidden,
                pc.target_lesson_id,
                pc.target_lesson_name
            FROM kei_school_practicecard pc
            WHERE pc.practice_id = ?
        ''', (old_practice_id,))
        
        old_cards = cursor.fetchall()
        
        for old_card in old_cards:
            # Находим соответствующий урок если указан
            lesson = None
            if old_card['target_lesson_name']:
                try:
                    lesson = Lesson.objects.get(
                        course=section.course,
                        title=old_card['target_lesson_name']
                    )
                except Lesson.DoesNotExist:
                    pass
            
            entry, created = DictionaryEntry.objects.get_or_create(
                section=section,
                term=old_card['text_front'] or 'Без термина',
                reading=old_card['text_back'] or '',
                defaults={
                    'translation': old_card['description_back'] or '',
                    'lesson': lesson
                }
            )
            
            if created:
                self.stdout.write(f'Создана словарная запись: {entry.term}')
                
                # Копируем аудио если есть
                if old_card['audio']:
                    old_audio_path = os.path.join(media_path, old_card['audio'])
                    if os.path.exists(old_audio_path):
                        try:
                            with open(old_audio_path, 'rb') as f:
                                audio_name = os.path.basename(old_card['audio'])
                                entry.pronunciation_audio.save(audio_name, File(f), save=True)
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось скопировать аудио для записи {entry.term}: {e}')
                            )
                
                # Мигрируем прогресс пользователей
                # Если hidden=False, значит карточка выучена
                if not old_card['hidden']:
                    self.migrate_user_practice_progress(cursor, old_card['id'], entry)
            else:
                self.stdout.write(f'Словарная запись уже существует: {entry.term}')

    def migrate_user_practice_progress(self, cursor, old_card_id, entry):
        # Получаем прогресс пользователей для карточки
        cursor.execute('''
            SELECT 
                up.user_id,
                up.is_complete,
                u.email
            FROM kei_school_userpractice up
            JOIN auth_user u ON u.id = up.user_id
            WHERE up.practice_card_id = ? AND up.is_complete = 1
        ''', (old_card_id,))
        
        user_progress = cursor.fetchall()
        
        for progress in user_progress:
            try:
                user = User.objects.get(email=progress['email'])
                learned_entry, created = UserLearnedEntry.objects.get_or_create(
                    user=user,
                    entry=entry
                )
                if created:
                    self.stdout.write(f'Отмечена изученная запись: {user.username} -> {entry.term}')
            except User.DoesNotExist:
                continue

    def migrate_lesson_content(self, cursor, media_path):
        self.stdout.write('Мигрирую содержимое уроков...')
        
        # Получаем все тесты из старой базы
        cursor.execute('''
            SELECT 
                t.id,
                t.name,
                t.title,
                t.subtitle,
                t.description,
                t.hint,
                t.lesson_id,
                l.name as lesson_name,
                c.name as course_name
            FROM kei_school_test t
            JOIN kei_school_lesson l ON l.id = t.lesson_id
            JOIN kei_school_course c ON c.id = l.course_id
        ''')
        
        old_tests = cursor.fetchall()
        
        for old_test in old_tests:
            try:
                # Находим соответствующий урок в новой базе
                course = Course.objects.get(title=old_test['course_name'])
                lesson = Lesson.objects.get(course=course, title=old_test['lesson_name'])
                
                # Создаем раздел урока на основе теста
                section, created = Section.objects.get_or_create(
                    lesson=lesson,
                    title=old_test['title'] or old_test['name'] or f'Раздел {old_test["id"]}',
                    defaults={'order': old_test['id']}
                )
                
                if created:
                    self.stdout.write(f'Создан раздел: {section.title} в уроке {lesson.title}')
                else:
                    self.stdout.write(f'Раздел уже существует: {section.title}')
                
                # Мигрируем типы тестов как элементы раздела
                self.migrate_test_types(cursor, media_path, old_test['id'], section)
                
            except (Course.DoesNotExist, Lesson.DoesNotExist):
                self.stdout.write(
                    self.style.WARNING(f'Не найден урок для теста: {old_test["name"]}')
                )
                continue

    def migrate_test_types(self, cursor, media_path, old_test_id, section):
        # Получаем типы тестов для данного теста
        cursor.execute('''
            SELECT 
                tt.id,
                tt.type,
                tt.ask,
                tt.image,
                tt.audio
            FROM kei_school_testtype tt
            WHERE tt.test_id = ?
        ''', (old_test_id,))
        
        test_types = cursor.fetchall()
        
        for i, test_type in enumerate(test_types):
            # Создаем материал теста
            test = self.create_test_from_testtype(cursor, media_path, test_type)
            
            if test:
                # Создаем элемент раздела
                content_type = ContentType.objects.get_for_model(test)
                section_item, created = SectionItem.objects.get_or_create(
                    section=section,
                    order=i + 1,
                    item_type='test',
                    defaults={
                        'content_type': content_type,
                        'object_id': test.id
                    }
                )
                
                if created:
                    self.stdout.write(f'Создан элемент раздела: тест "{test.title}"')

    def create_test_from_testtype(self, cursor, media_path, test_type):
        # Маппинг типов тестов
        type_mapping = {
            'choice_test': 'mcq-single',  # Будем проверять количество правильных ответов
            'text_test': 'free-text',
            'order_test': 'word-order',
            'correlation_test': 'drag-and-drop'
        }
        
        new_type = type_mapping.get(test_type['type'])
        if not new_type:
            return None
        
        # Создаем тест
        title = test_type['ask'] or f'Тест {test_type["id"]}'
        # Обрезаем название если оно слишком длинное
        if len(title) > 250:
            title = title[:247] + '...'
            
        test = Test.objects.create(
            title=title,
            description='',
            test_type=new_type
        )
        
        # Добавляем медиа к тесту если есть
        self.attach_test_media(cursor, media_path, test_type['id'], test)
        
        # Создаем ответы в зависимости от типа
        if test_type['type'] == 'choice_test':
            self.create_mcq_options(cursor, test_type['id'], test)
        elif test_type['type'] == 'text_test':
            self.create_free_text_question(cursor, test_type['id'], test)
        elif test_type['type'] == 'order_test':
            self.create_word_order_question(cursor, test_type['id'], test)
        elif test_type['type'] == 'correlation_test':
            self.create_matching_question(cursor, test_type['id'], test)
        
        return test

    def attach_test_media(self, cursor, media_path, testtype_id, test):
        # Получаем медиа для типа теста
        cursor.execute('''
            SELECT audio, photo, video, presentation
            FROM kei_school_testmedia
            WHERE test_id = ?
        ''', (testtype_id,))
        
        media = cursor.fetchone()
        if not media:
            return
            
        # Создаем аудио материал если есть
        if media['audio']:
            audio_path = os.path.join(media_path, media['audio'])
            if os.path.exists(audio_path):
                try:
                    audio_material = AudioMaterial.objects.create(
                        title=f'Аудио для теста {test.title}'
                    )
                    with open(audio_path, 'rb') as f:
                        audio_name = os.path.basename(media['audio'])
                        audio_material.audio_file.save(audio_name, File(f), save=True)
                    test.attached_audio = audio_material
                    test.save()
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Не удалось прикрепить аудио к тесту {test.title}: {e}')
                    )
        
        # Создаем изображение если есть
        if media['photo']:
            image_path = os.path.join(media_path, media['photo'])
            if os.path.exists(image_path):
                try:
                    image_material = ImageMaterial.objects.create(
                        title=f'Изображение для теста {test.title}'
                    )
                    with open(image_path, 'rb') as f:
                        image_name = os.path.basename(media['photo'])
                        image_material.image.save(image_name, File(f), save=True)
                    test.attached_image = image_material
                    test.save()
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Не удалось прикрепить изображение к тесту {test.title}: {e}')
                    )

    def create_mcq_options(self, cursor, testtype_id, test):
        # Получаем варианты ответов
        cursor.execute('''
            SELECT 
                a.id,
                a.is_correct,
                a.explanation,
                ac.choice_answer
            FROM kei_school_answer a
            JOIN kei_school_answerchoice ac ON ac.answer_id = a.id
            WHERE a.test_id = ?
        ''', (testtype_id,))
        
        choices = cursor.fetchall()
        correct_count = sum(1 for choice in choices if choice['is_correct'])
        
        # Если больше одного правильного ответа, меняем тип на множественный выбор
        if correct_count > 1:
            test.test_type = 'mcq-multi'
            test.save()
        
        for i, choice in enumerate(choices):
            MCQOption.objects.create(
                test=test,
                text=choice['choice_answer'] or f'Вариант {i+1}',
                is_correct=choice['is_correct'],
                explanation=choice['explanation'] or '',
                order=i + 1
            )

    def create_free_text_question(self, cursor, testtype_id, test):
        # Получаем текстовые ответы
        cursor.execute('''
            SELECT 
                a.explanation,
                at.text_answer
            FROM kei_school_answer a
            JOIN kei_school_answertext at ON at.answer_id = a.id
            WHERE a.test_id = ?
            LIMIT 1
        ''', (testtype_id,))
        
        text_answer = cursor.fetchone()
        if text_answer:
            FreeTextQuestion.objects.create(
                test=test,
                reference_answer=text_answer['text_answer'] or '',
                explanation=text_answer['explanation'] or ''
            )

    def create_word_order_question(self, cursor, testtype_id, test):
        # Получаем ответы для порядка слов
        cursor.execute('''
            SELECT 
                a.explanation,
                ao.order_answer
            FROM kei_school_answer a
            JOIN kei_school_answerorder ao ON ao.answer_id = a.id
            WHERE a.test_id = ?
        ''', (testtype_id,))
        
        order_answers = cursor.fetchall()
        
        # Собираем все слова из ответов в пул
        all_words = []
        correct_order = []
        
        for answer in order_answers:
            if answer['order_answer']:
                words = answer['order_answer'].split()
                all_words.extend(words)
                if not correct_order:  # Берем первый как правильный порядок
                    correct_order = words
        
        # Убираем дубликаты и создаем пул
        unique_words = list(set(all_words))
        
        test.draggable_options_pool = unique_words
        test.save()
        
        explanation = order_answers[0]['explanation'] if order_answers else ''
        WordOrderSentence.objects.create(
            test=test,
            correct_ordered_texts=correct_order,
            explanation=explanation
        )

    def create_matching_question(self, cursor, testtype_id, test):
        # Получаем ответы для соотнесения
        cursor.execute('''
            SELECT 
                a.id,
                a.explanation,
                ac.correlation_answer
            FROM kei_school_answer a
            JOIN kei_school_answercorrelation ac ON ac.answer_id = a.id
            WHERE a.test_id = ?
        ''', (testtype_id,))
        
        correlations = cursor.fetchall()
        
        # Собираем все варианты в пул
        all_options = []
        
        for i, correlation in enumerate(correlations):
            if correlation['correlation_answer']:
                # Предполагаем формат "левая_часть:правая_часть"
                parts = correlation['correlation_answer'].split(':')
                if len(parts) >= 2:
                    left_part = parts[0].strip()
                    right_part = parts[1].strip()
                    
                    all_options.extend([left_part, right_part])
                    
                    # Создаем пару соотнесения
                    MatchingPair.objects.create(
                        test=test,
                        prompt_text=left_part,
                        correct_answer_text=right_part,
                        order=i + 1,
                        explanation=correlation['explanation'] or ''
                    )
        
        # Убираем дубликаты и создаем пул
        unique_options = list(set(all_options))
        test.draggable_options_pool = unique_options
        test.save() 

    def migrate_standalone_materials(self, cursor, media_path):
        self.stdout.write('Мигрирую отдельные материалы...')
        
        # Мигрируем медиа файлы из тестов как отдельные материалы
        cursor.execute('''
            SELECT DISTINCT
                tm.audio,
                tm.photo,
                tm.video,
                tm.presentation,
                t.name as test_name,
                l.name as lesson_name,
                c.name as course_name,
                t.description,
                t.hint
            FROM kei_school_testmedia tm
            JOIN kei_school_test t ON t.id = tm.test_id
            JOIN kei_school_lesson l ON l.id = t.lesson_id
            JOIN kei_school_course c ON c.id = l.course_id
            WHERE tm.audio != '' OR tm.photo != '' OR tm.video != '' OR tm.presentation != ''
        ''')
        
        media_files = cursor.fetchall()
        
        for media in media_files:
            try:
                # Находим соответствующий урок и раздел
                course = Course.objects.get(title=media['course_name'])
                lesson = Lesson.objects.get(course=course, title=media['lesson_name'])
                
                # Ищем раздел "Теория" или создаем раздел "Материалы"
                section, created = Section.objects.get_or_create(
                    lesson=lesson,
                    title='Материалы',
                    defaults={'order': 999}  # В конце урока
                )
                
                # Создаем материалы для каждого типа медиа
                materials_created = []
                
                # Аудио материал
                if media['audio']:
                    audio_path = os.path.join(media_path, media['audio'])
                    if os.path.exists(audio_path):
                        try:
                            audio_material = AudioMaterial.objects.create(
                                title=f'Аудио: {media["test_name"]}',
                                transcript=media['description'] or media['hint'] or ''
                            )
                            with open(audio_path, 'rb') as f:
                                audio_name = os.path.basename(media['audio'])
                                audio_material.audio_file.save(audio_name, File(f), save=True)
                            materials_created.append(audio_material)
                            self.stdout.write(f'Создан аудио материал: {audio_material.title}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось создать аудио материал: {e}')
                            )
                
                # Изображение
                if media['photo']:
                    image_path = os.path.join(media_path, media['photo'])
                    if os.path.exists(image_path):
                        try:
                            image_material = ImageMaterial.objects.create(
                                title=f'Изображение: {media["test_name"]}',
                                alt_text=media['description'] or media['hint'] or ''
                            )
                            with open(image_path, 'rb') as f:
                                image_name = os.path.basename(media['photo'])
                                image_material.image.save(image_name, File(f), save=True)
                            materials_created.append(image_material)
                            self.stdout.write(f'Создан материал изображения: {image_material.title}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось создать материал изображения: {e}')
                            )
                
                # Видео материал
                if media['video']:
                    video_path = os.path.join(media_path, media['video'])
                    if os.path.exists(video_path):
                        try:
                            video_material = VideoMaterial.objects.create(
                                title=f'Видео: {media["test_name"]}',
                                source_type='file',
                                transcript=media['description'] or media['hint'] or ''
                            )
                            with open(video_path, 'rb') as f:
                                video_name = os.path.basename(media['video'])
                                video_material.video_file.save(video_name, File(f), save=True)
                            materials_created.append(video_material)
                            self.stdout.write(f'Создан видео материал: {video_material.title}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось создать видео материал: {e}')
                            )
                
                # Презентация как документ
                if media['presentation']:
                    presentation_path = os.path.join(media_path, media['presentation'])
                    if os.path.exists(presentation_path):
                        try:
                            doc_material = DocumentMaterial.objects.create(
                                title=f'Презентация: {media["test_name"]}'
                            )
                            with open(presentation_path, 'rb') as f:
                                doc_name = os.path.basename(media['presentation'])
                                doc_material.document_file.save(doc_name, File(f), save=True)
                            materials_created.append(doc_material)
                            self.stdout.write(f'Создан материал документа: {doc_material.title}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'Не удалось создать материал документа: {e}')
                            )
                
                # Создаем SectionItem для каждого материала
                for i, material in enumerate(materials_created):
                    content_type = ContentType.objects.get_for_model(material)
                    
                    # Находим максимальный order в разделе
                    max_order = SectionItem.objects.filter(section=section).aggregate(
                        max_order=models.Max('order')
                    )['max_order'] or 0
                    
                    section_item, created = SectionItem.objects.get_or_create(
                        section=section,
                        content_type=content_type,
                        object_id=material.id,
                        defaults={
                            'order': max_order + 1 + i,  # После всех существующих элементов
                            'item_type': 'material'
                        }
                    )
                    if created:
                        self.stdout.write(f'Создан элемент раздела для материала: {material.title}')
                
            except (Course.DoesNotExist, Lesson.DoesNotExist):
                continue
        
        # Создаем текстовые материалы из описаний тестов
        self.migrate_text_materials(cursor, media_path)
    
    def migrate_text_materials(self, cursor, media_path):
        self.stdout.write('Мигрирую текстовые материалы...')
        
        # Получаем тесты с описаниями/подсказками для создания текстовых материалов
        cursor.execute('''
            SELECT DISTINCT
                t.id,
                t.description,
                t.hint,
                t.name as test_name,
                l.name as lesson_name,
                c.name as course_name
            FROM kei_school_test t
            JOIN kei_school_lesson l ON l.id = t.lesson_id
            JOIN kei_school_course c ON c.id = l.course_id
            WHERE (t.description IS NOT NULL AND t.description != '')
               OR (t.hint IS NOT NULL AND t.hint != '')
        ''')
        
        text_materials = cursor.fetchall()
        
        for text_mat in text_materials:
            try:
                course = Course.objects.get(title=text_mat['course_name'])
                lesson = Lesson.objects.get(course=course, title=text_mat['lesson_name'])
                
                # Ищем раздел "Теория" или создаем
                section, created = Section.objects.get_or_create(
                    lesson=lesson,
                    title='Теория',
                    defaults={'order': 1}
                )
                
                # Создаем текстовый материал если есть содержимое
                content = text_mat['description'] or text_mat['hint']
                if content and len(content.strip()) > 10:  # Только если есть существенный контент
                    text_material = TextMaterial.objects.create(
                        title=f'Материал: {text_mat["test_name"]}',
                        content=content,
                        is_markdown=False
                    )
                    
                    # Создаем элемент раздела
                    content_type = ContentType.objects.get_for_model(text_material)
                    
                    # Проверяем, есть ли уже элементы в разделе
                    existing_items = SectionItem.objects.filter(section=section).count()
                    
                    section_item, created = SectionItem.objects.get_or_create(
                        section=section,
                        content_type=content_type,
                        object_id=text_material.id,
                        defaults={
                            'order': existing_items + 1,  # После всех существующих элементов
                            'item_type': 'material'
                        }
                    )
                    
                    if created:
                        self.stdout.write(f'Создан текстовый материал: {text_material.title}')
                
            except (Course.DoesNotExist, Lesson.DoesNotExist):
                continue