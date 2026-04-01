from rest_framework import permissions
from lesson_service.models import SectionItem
from course_service.models import CourseEnrollment


class IsAdminOrStaffWriteOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role in ['admin', 'teacher', 'assistant']

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        
        if request.user.role in ['admin', 'teacher']:
            return True
        
        if request.user.role == 'assistant':
            if hasattr(obj, 'created_by') and obj.created_by == request.user:
                return True
            
            from lesson_service.models import SectionItem
            from django.contrib.contenttypes.models import ContentType
            from course_service.models import CourseAssistant
            
            content_type = ContentType.objects.get_for_model(obj.__class__)
            assisting_course_ids = CourseAssistant.objects.filter(assistant=request.user).values_list('course_id', flat=True)
            
            is_used_in_assisting_course = SectionItem.objects.filter(
                content_type=content_type, 
                object_id=obj.id,
                section__lesson__course_id__in=assisting_course_ids
            ).exists()
            
            return is_used_in_assisting_course
            
        return False


class CanSubmitTest(permissions.BasePermission):
    message = "Вы не можете отправить ответ на этот тест. Убедитесь, что вы записаны на курс."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        section_item_id = request.data.get('section_item_id')
        challenge_id = request.data.get('challenge_id')

        if challenge_id:
            from challenge_service.models import ChallengeTest
            is_test_in_user_challenge = ChallengeTest.objects.filter(
                challenge_id=challenge_id,
                challenge__user=request.user,
                test=obj,
            ).exists()
            if not is_test_in_user_challenge:
                self.message = "Тест не найден в указанном испытании пользователя."
            return is_test_in_user_challenge

        if not section_item_id:
            self.message = "Не предоставлен ID элемента раздела (section_item_id) или challenge_id."
            return False

        try:
            section_item = SectionItem.objects.select_related('section__lesson__course').get(
                pk=section_item_id,
                content_type__model=obj._meta.model_name, 
                object_id=obj.pk
            )
        except SectionItem.DoesNotExist:
            self.message = "Не найден связанный элемент раздела или он не ссылается на этот тест."
            return False
        except Exception:
             self.message = "Ошибка при проверке связи с уроком."
             return False

        course = section_item.section.lesson.course

        is_enrolled = CourseEnrollment.objects.filter(
            course=course,
            student=request.user,
            status='active'
        ).exists()

        if not is_enrolled:
            self.message = f"Вы не записаны (или не активны) на курс '{course.title}', к которому относится этот тест."

        return is_enrolled