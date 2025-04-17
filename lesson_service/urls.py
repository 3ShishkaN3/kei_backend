# lesson_service/urls.py
from django.urls import path, include
from rest_framework_nested import routers
from .views import LessonViewSet, SectionViewSet

lesson_router = routers.SimpleRouter()
lesson_router.register(r'', LessonViewSet, basename='') 

sections_router = routers.NestedSimpleRouter(lesson_router, r'', lookup='lesson')
sections_router.register(r'sections', SectionViewSet, basename='lesson-sections')

urlpatterns = [
    path('', include(sections_router.urls)), 
]



# GET /lessons/ - Список уроков (с фильтрацией по course_id=X или по правам пользователя)
# POST /lessons/ - Создать урок (нужно передать course_id в теле)
# GET /lessons/{lesson_pk}/ - Детали урока
# PUT /lessons/{lesson_pk}/ - Обновить урок
# DELETE /lessons/{lesson_pk}/ - Удалить урок
# POST /lessons/{lesson_pk}/complete/ - Завершить урок (если все разделы пройдены)
# GET /lessons/{lesson_pk}/completion_status/ - Статус завершения урока

# GET /lessons/{lesson_pk}/sections/ - Список разделов урока
# POST /lessons/{lesson_pk}/sections/ - Создать раздел для урока
# GET /lessons/{lesson_pk}/sections/{section_pk}/ - Детали раздела
# PUT /lessons/{lesson_pk}/sections/{section_pk}/ - Обновить раздел
# DELETE /lessons/{lesson_pk}/sections/{section_pk}/ - Удалить раздел
# POST /lessons/{lesson_pk}/sections/{section_pk}/complete/ - Завершить раздел
# GET /lessons/{lesson_pk}/sections/{section_pk}/completion_status/ - Статус завершения раздела