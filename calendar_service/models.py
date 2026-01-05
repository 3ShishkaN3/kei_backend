from django.conf import settings
from django.db import models


class Event(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "запланировано"
        IN_PROGRESS = "in_progress", "в процессе"
        COMPLETED = "completed", "проведено"
        CANCELLED = "cancelled", "отменено"

    class RecurrenceFreq(models.TextChoices):
        NONE = "none", "без повторения"
        DAILY = "daily", "ежедневно"
        WEEKLY = "weekly", "еженедельно"
        MONTHLY = "monthly", "ежемесячно"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, default="UTC")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_events")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    reminder_enabled = models.BooleanField(default=False)

    recurrence_frequency = models.CharField(max_length=16, choices=RecurrenceFreq.choices, default=RecurrenceFreq.NONE)
    recurrence_interval = models.PositiveSmallIntegerField(default=1)
    recurrence_by_weekday = models.JSONField(default=list, blank=True)  # ["MO", "WE"]
    recurrence_until = models.DateField(null=True, blank=True)
    recurrence_count = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.start_at} - {self.end_at})"


class EventParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_events")

    class Meta:
        unique_together = ("event", "user")

    def __str__(self):
        return f"{self.user_id} -> {self.event_id}"


class DayNote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="day_notes")
    date = models.DateField()
    timezone = models.CharField(max_length=64, default="UTC")
    text = models.TextField(blank=True, default="")
    reminder_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Note {self.user_id} {self.date}"


