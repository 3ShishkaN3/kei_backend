from rest_framework import permissions
from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant,  Course


class IsCourseStaffOrAdmin(permissions.BasePermission):
    """
    Разрешение для администраторов или преподавателей/ассистентов курса.
    """
    def has_object_permission(self, request, view, obj):
        # Если obj уже является курсом
        if isinstance(obj, Course):
            course = obj
        else:
            # obj может быть Lesson или Section
            course = obj.course if hasattr(obj, 'course') else obj.lesson.course

        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()

        return is_teacher or is_assistant

class CanComplete(permissions.BasePermission):
    """
    Разрешение на отметку о завершении (для студентов).
    Проверяет, что пользователь записан на курс.
    """
    def has_object_permission(self, request, view, obj):
        # Если obj уже является курсом
        if isinstance(obj, Course):
            course = obj
        else:
            # obj может быть Lesson или Section
            course = obj.course if hasattr(obj, 'course') else obj.lesson.course

        if not request.user or not request.user.is_authenticated:
            return False

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()
        return is_enrolled


class CanViewLessonOrSectionContent(permissions.BasePermission):
    """
    Разрешение на просмотр:
    - Администраторы
    - Преподаватели/ассистенты курса
    - Записанные на курс студенты
    """
    def has_object_permission(self, request, view, obj):
        # Если obj уже является курсом
        if isinstance(obj, Course):
            course = obj
        else:
            # obj может быть Lesson или Section
            course = obj.course if hasattr(obj, 'course') else obj.lesson.course

        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()
        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()

        return is_teacher or is_assistant or is_enrolled


class SectionPermission(permissions.BasePermission):
    """
    Общие разрешения для Разделов (Section).
    - SAFE_METHODS (GET, HEAD, OPTIONS): Доступны для персонала курса или записанных студентов.
    - POST, PUT, PATCH, DELETE: Доступны только для персонала курса или админов.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)


class CanComplete(permissions.BasePermission):
    """
    Разрешение на отметку о завершении (для студентов).
    Проверяет, что пользователь записан на курс.
    """
    def has_object_permission(self, request, view, obj):
        course = obj.course if hasattr(obj, 'course') else obj.lesson.course

        if not request.user or not request.user.is_authenticated:
            return False

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()
        return is_enrolled
    

class LessonPermission(permissions.BasePermission):
    """
    Общие разрешения для Уроков (Lesson).
    - SAFE_METHODS (GET, HEAD, OPTIONS): Доступны для персонала курса или записанных студентов.
    - POST, PUT, PATCH, DELETE: Доступны только для персонала курса или админов.
    """
    def has_permission(self, request, view):
        # Разрешение на создание (POST) требует проверки курса в ViewSet
        # Разрешение на список (GET list) требует проверки в ViewSet.get_queryset
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj это Lesson
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        # Для небезопасных методов - только персонал или админ
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)
    
    