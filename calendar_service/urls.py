from rest_framework.routers import DefaultRouter
from .views import EventViewSet, DayNoteViewSet

router = DefaultRouter()
router.register(r'events', EventViewSet, basename='calendar-events')
router.register(r'notes', DayNoteViewSet, basename='calendar-day-notes')

urlpatterns = router.urls


