# lesson_service/permissions.py
from rest_framework import permissions
# Убедись, что все модели, которые ты используешь, импортированы
from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant, Course

class IsCourseStaffOrAdmin(permissions.BasePermission):
    """
    Разрешение для администраторов или преподавателей/ассистентов курса.
    Применяется к объектам Course, Lesson, Section, SectionItem.
    """
    message = "У вас нет прав на управление этим ресурсом курса."

    def _get_course_from_obj(self, obj):
        """Вспомогательный метод для получения курса из разных типов объектов."""
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): # Для Lesson
            return obj.course
        elif hasattr(obj, 'lesson') and hasattr(obj.lesson, 'course') and isinstance(obj.lesson.course, Course): # Для Section
            return obj.lesson.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'lesson') and \
             hasattr(obj.section.lesson, 'course') and isinstance(obj.section.lesson.course, Course): # Для SectionItem
            return obj.section.lesson.course
        return None

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Администраторы Django имеют полный доступ
        if request.user.is_staff or request.user.is_superuser: # Добавил is_superuser для Django админов
            return True
        
        # Пользователи с ролью 'admin' в твоей системе
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            # Если не удалось определить курс из объекта, возможно, это ошибка конфигурации
            # или пермишен применяется к объекту, для которого он не предназначен.
            # В таких случаях лучше логировать и возвращать False.
            print(f"IsCourseStaffOrAdmin: Could not determine course from object: {type(obj)}")
            return False

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()

        return is_teacher or is_assistant


class CanViewLessonOrSectionContent(permissions.BasePermission):
    """
    Разрешение на просмотр контента урока/раздела:
    - Администраторы Django и пользователи с ролью 'admin'
    - Персонал курса (учителя, ассистенты)
    - Студенты, зачисленные на курс и активные
    - Если курс публичный (если есть такое поле)
    Применяется к объектам Course, Lesson, Section, SectionItem.
    """
    message = "У вас нет доступа к просмотру этого контента."

    def _get_course_from_obj(self, obj): # Используем тот же хелпер
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course):
            return obj.course
        elif hasattr(obj, 'lesson') and hasattr(obj.lesson, 'course') and isinstance(obj.lesson.course, Course):
            return obj.lesson.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'lesson') and \
             hasattr(obj.section.lesson, 'course') and isinstance(obj.section.lesson.course, Course):
            return obj.section.lesson.course
        return None

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            # Для публичных курсов можно разрешить анонимный доступ, если такая логика есть
            course_for_public_check = self._get_course_from_obj(obj)
            if course_for_public_check and hasattr(course_for_public_check, 'is_public') and course_for_public_check.is_public:
                return True
            return False # Если не публичный, то неаутентифицированным нельзя

        if request.user.is_staff or request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"CanViewLessonOrSectionContent: Could not determine course from object: {type(obj)}")
            return False
        
        # Проверка на публичность курса (если аутентифицирован, но не персонал/студент)
        if hasattr(course, 'is_public') and course.is_public:
            return True

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()
        if is_teacher or is_assistant:
            return True

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active' # Убедись, что статус 'active' правильный для активной записи
        ).exists()

        return is_enrolled


class CanCompleteItems(permissions.BasePermission): # Переименовал для ясности, что это для элементов урока/раздела
    """
    Разрешение на отметку о завершении (для студентов).
    Проверяет, что пользователь записан на курс.
    Применяется к объектам Lesson, Section (или SectionItem, если завершение на уровне элемента).
    """
    message = "Вы не можете отметить этот элемент как завершенный, так как не записаны на курс."

    def _get_course_from_obj(self, obj): # Используем тот же хелпер
        if isinstance(obj, Course): # Хотя обычно к курсу не применяется "завершение"
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): 
            return obj.course
        elif hasattr(obj, 'lesson') and hasattr(obj.lesson, 'course') and isinstance(obj.lesson.course, Course):
            return obj.lesson.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'lesson') and \
             hasattr(obj.section.lesson, 'course') and isinstance(obj.section.lesson.course, Course):
            return obj.section.lesson.course
        return None

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"CanCompleteItems: Could not determine course from object: {type(obj)}")
            return False

        # Только студенты могут отмечать завершение
        # (Админы/персонал обычно не отмечают прогресс для себя таким образом)
        # if hasattr(request.user, 'role') and request.user.role in ['admin', 'teacher', 'assistant']:
        # return False # Или True, если они тоже могут для себя

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()
        return is_enrolled


# LessonPermission и SectionPermission выглядят хорошо, если они используют обновленные
# CanViewLessonOrSectionContent и IsCourseStaffOrAdmin.
# Убедись, что obj, передаваемый в них, корректно обрабатывается _get_course_from_obj.
# Например, для LessonPermission, obj будет Lesson.
# Для SectionPermission, obj будет Section.

class LessonPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj): # obj здесь это Lesson
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)

class SectionPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj): # obj здесь это Section
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)