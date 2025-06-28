# dict_service/permissions.py
from rest_framework import permissions
from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant, Course
class IsCourseStaffOrAdminForDict(permissions.BasePermission):
    message = "У вас нет прав на управление словарем этого курса."

    def _get_course_from_obj(self, obj):
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): # Для DictionarySection
            return obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course') and \
             isinstance(obj.section.course, Course): # Для DictionaryEntry
            return obj.section.course
        return None
    

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"IsCourseStaffOrAdminForDict: Could not determine course from object: {type(obj)}")
            return False

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()
        return is_teacher or is_assistant

class CanViewDictionaryContent(permissions.BasePermission):
    message = "У вас нет доступа к просмотру словаря этого курса."

    def _get_course_from_obj(self, obj): # Тот же хелпер
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): 
            return obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course') and \
             isinstance(obj.section.course, Course):
            return obj.section.course
        return None

    def has_permission(self, request, view):
        # Эта проверка будет для 'list' действия, когда нет конкретного объекта
        # Если view.kwargs содержит course_pk, мы можем проверить доступ к этому курсу
        course_pk = view.kwargs.get('course_pk')
        if course_pk:
            try:
                course = Course.objects.get(pk=course_pk)
                # Переиспользуем has_object_permission для проверки доступа к этому курсу
                return self.has_object_permission(request, view, course)
            except Course.DoesNotExist:
                return False # Курс не найден, доступ запрещен
        # Если course_pk не указан (например, /api/dictionary_sections/ без фильтра по курсу),
        # то решение о доступе должно приниматься на основе других критериев
        # (например, показывать только разделы из курсов, на которые пользователь записан,
        # или для админа показывать все).
        # Если логика get_queryset фильтрует это, то здесь можно просто вернуть True.
        # Но для безопасности, если нет course_pk, и это не админ, можно запретить.
        if request.user.is_staff or (hasattr(request.user, 'role') and request.user.role == 'admin'):
            return True
        # Для обычных пользователей без course_pk - доступ к списку всех разделов словаря может быть нежелателен.
        # Можно вернуть False или реализовать фильтрацию в get_queryset.
        # Пока что, если не админ и нет course_pk, то запретим общий список.
        # get_queryset потом должен отфильтровать по доступным курсам.
        return False # Или True, если get_queryset всегда правильно фильтрует

    def has_object_permission(self, request, view, obj):
        # obj здесь может быть Course (из get_queryset или has_permission),
        # DictionarySection (из retrieve/update/delete DictionarySectionViewSet),
        # или DictionaryEntry (если этот пермишен используется для DictionaryEntryViewSet).

        # Базовые проверки
        if not request.user or not request.user.is_authenticated:
            course_for_public_check = self._get_course_from_obj(obj)
            if course_for_public_check and hasattr(course_for_public_check, 'is_public') and course_for_public_check.is_public:
                return True
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"CanViewDictionaryContent: Could not determine course from object: {type(obj)}")
            return False
        
        if hasattr(course, 'is_public') and course.is_public: # Если курс публичный
            return True

        # Проверка на персонал курса
        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()
        if is_teacher or is_assistant:
            return True

        # Проверка на зачисление студента
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