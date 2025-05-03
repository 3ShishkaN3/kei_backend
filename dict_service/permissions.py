# dict_service/permissions.py
from rest_framework import permissions
from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant

class IsCourseStaffOrAdminForDict(permissions.BasePermission):
    """
    Разрешение на запись для Админов или Персонала курса (Учитель/Ассистент),
    к которому относится раздел словаря или запись в нем.
    """
    message = "У вас нет прав на управление словарем этого курса."

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        course = None
        if hasattr(obj, 'course'): 
            course = obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course'):
            course = obj.section.course
        else:
            return False

        if not course: return False 

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()

        return is_teacher or is_assistant

class CanViewDictionaryContent(permissions.BasePermission):
    """
    Разрешение на чтение: Админы, Персонал курса или Студенты,
    записанные на курс, к которому относится раздел/запись.
    """
    message = "У вас нет доступа к просмотру словаря этого курса."

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        course = None
        if hasattr(obj, 'course'): 
            course = obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course'):
            course = obj.section.course
        else:
            return False

        if not course: return False

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()
        if is_teacher or is_assistant:
            return True

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()

        return is_enrolled

class CanMarkLearned(permissions.BasePermission):
    """
    Разрешение на отметку "изучено".
    Доступно аутентифицированным пользователям, имеющим доступ к записи.
    """
    message = "Вы не можете отметить этот элемент как изученный."

    def has_object_permission(self, request, view, obj):
        # Достаточно проверить, что пользователь может видеть запись
        return CanViewDictionaryContent().has_object_permission(request, view, obj)