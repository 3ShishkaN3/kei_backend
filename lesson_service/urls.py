from django.urls import include, path
from rest_framework_nested import routers
from .views import (
    LessonViewSet,
    SectionViewSet,
    SectionItemViewSet,
)
from dict_service.views import PrimaryLessonEntriesViewSet

# Базовый роутер для уроков
router = routers.SimpleRouter()
router.register(r'', LessonViewSet, basename='lesson')

# 1) разделы внутри урока
sections_router = routers.NestedSimpleRouter(router, r'', lookup='lesson')
sections_router.register(r'sections', SectionViewSet, basename='lesson-sections')

# 2) элементы раздела внутри раздела
items_router = routers.NestedSimpleRouter(sections_router, r'sections', lookup='section')
items_router.register(r'items', SectionItemViewSet, basename='section-items')

# 3) primary_dictionary_entries внутри урока
primary_router = routers.NestedSimpleRouter(router, r'', lookup='lesson')
primary_router.register(
    r'primary_dictionary_entries',
    PrimaryLessonEntriesViewSet,
    basename='lesson-primary-entries'
)

urlpatterns = [
    path('', include(router.urls)),
    path('', include(sections_router.urls)),
    path('', include(items_router.urls)),     
    path('', include(primary_router.urls)), 
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