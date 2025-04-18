# material_service/permissions.py
from rest_framework import permissions
from lesson_service.models import SectionItem
from course_service.models import CourseEnrollment


class IsAdminOrStaffWriteOrReadOnly(permissions.BasePermission):
    """
    Разрешение: Чтение для всех аутентифицированных.
    Запись (POST, PUT, PATCH, DELETE) для Админов, Учителей, Ассистентов.
    ВАЖНО: Не проверяет привязку к КОНКРЕТНОМУ курсу здесь!
           Эта проверка должна быть на уровне API Gateway или в lesson_service при линковке.
           Или требует добавления прямой связи материала/теста с курсом.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role in ['admin', 'teacher', 'assistant']

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class CanSubmitTest(permissions.BasePermission):
    """
    Проверяет, может ли студент отправить ответ на тест.
    Требует, чтобы студент был активно записан на курс,
    к которому относится SectionItem, связанный с тестом.
    """
    message = "Вы не можете отправить ответ на этот тест. Убедитесь, что вы записаны на курс."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        section_item_id = request.data.get('section_item_id')
        if not section_item_id:
            self.message = "Не предоставлен ID элемента раздела (section_item_id)."
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