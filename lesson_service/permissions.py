from rest_framework import permissions

from course_service.models import CourseEnrollment, CourseTeacher, CourseAssistant, Course

class IsCourseStaffOrAdmin(permissions.BasePermission):
    message = "У вас нет прав на управление этим ресурсом курса."

    def _get_course_from_obj(self, obj):
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
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True
        
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"IsCourseStaffOrAdmin: Could not determine course from object: {type(obj)}")
            return False

        is_teacher = CourseTeacher.objects.filter(course=course, teacher=request.user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=request.user).exists()

        return is_teacher or is_assistant


class CanViewLessonOrSectionContent(permissions.BasePermission):
    message = "У вас нет доступа к просмотру этого контента."

    def _get_course_from_obj(self, obj):
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
            course_for_public_check = self._get_course_from_obj(obj)
            if course_for_public_check and course_for_public_check.status in ['free', 'published']:
                return True
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == 'admin':
            return True

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"CanViewLessonOrSectionContent: Could not determine course from object: {type(obj)}")
            return False
        
        if course.status in ['free', 'published']:
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


class CanCompleteItems(permissions.BasePermission):
    message = "Вы не можете отметить этот элемент как завершенный, так как не записаны на курс."

    def _get_course_from_obj(self, obj):
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
            return False

        course = self._get_course_from_obj(obj)
        if not course:
            print(f"CanCompleteItems: Could not determine course from object: {type(obj)}")
            return False

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()
        return is_enrolled


class LessonPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)

class SectionPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return CanViewLessonOrSectionContent().has_object_permission(request, view, obj)
        return IsCourseStaffOrAdmin().has_object_permission(request, view, obj)