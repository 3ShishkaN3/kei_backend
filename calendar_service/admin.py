from django.contrib import admin
from .models import Event, EventParticipant, DayNote


class EventParticipantInline(admin.TabularInline):
    model = EventParticipant
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "start_at", "end_at", "status", "created_by")
    list_filter = ("status", "recurrence_frequency", "timezone")
    search_fields = ("title", "description")
    inlines = [EventParticipantInline]


@admin.register(DayNote)
class DayNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "date", "reminder_enabled")
    list_filter = ("reminder_enabled",)
    search_fields = ("text",)


