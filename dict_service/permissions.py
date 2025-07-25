from rest_framework import permissions
from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant, Course

class IsCourseStaffOrAdminForDict(permissions.BasePermission):
    message = "У вас нет прав на управление словарем этого курса."

    def _get_course_from_obj(self, obj):
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course):
            return obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course') and \
             isinstance(obj.section.course, Course):
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

    def _get_course_from_obj(self, obj):
        if isinstance(obj, Course):
            return obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): 
            return obj.course
        elif hasattr(obj, 'section') and hasattr(obj.section, 'course') and \
             isinstance(obj.section.course, Course):
            return obj.section.course
        return None

    def has_permission(self, request, view):
        course_pk = view.kwargs.get('course_pk')
        if course_pk:
            try:
                course = Course.objects.get(pk=course_pk)
                return self.has_object_permission(request, view, course)
            except Course.DoesNotExist:
                return False
        if request.user.is_staff or (hasattr(request.user, 'role') and request.user.role == 'admin'):
            return True
        return False

    def has_object_permission(self, request, view, obj):
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
        
        if hasattr(course, 'is_public') and course.is_public:
            return True

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
    message = "Вы не можете отметить этот элемент как изученный."

    def has_object_permission(self, request, view, obj):
        return CanViewDictionaryContent().has_object_permission(request, view, obj)