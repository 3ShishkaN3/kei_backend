from django.utils import timezone as dj_timezone
from rest_framework import serializers

from auth_service.models import User
from .models import Event, EventParticipant, DayNote


class EventParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventParticipant
        fields = ("user",)


class EventSerializer(serializers.ModelSerializer):
    participants = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )
    participant_ids = serializers.SerializerMethodField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "description",
            "start_at",
            "end_at",
            "timezone",
            "created_by",
            "status",
            "reminder_enabled",
            "recurrence_frequency",
            "recurrence_interval",
            "recurrence_by_weekday",
            "recurrence_until",
            "recurrence_count",
            "participants",
            "participant_ids",
            "created_at",
            "updated_at",
        )

    def get_participant_ids(self, obj: Event):
        return list(obj.participants.values_list("user_id", flat=True))

    def validate(self, attrs):
        start = attrs.get("start_at") or getattr(self.instance, "start_at", None)
        end = attrs.get("end_at") or getattr(self.instance, "end_at", None)
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "Конец должен быть позже начала."})

        freq = attrs.get("recurrence_frequency", getattr(self.instance, "recurrence_frequency", Event.RecurrenceFreq.NONE))
        interval = attrs.get("recurrence_interval", getattr(self.instance, "recurrence_interval", 1))
        byweekday = attrs.get("recurrence_by_weekday", getattr(self.instance, "recurrence_by_weekday", []))
        if freq == Event.RecurrenceFreq.WEEKLY and byweekday and not all(isinstance(x, str) for x in byweekday):
            raise serializers.ValidationError({"recurrence_by_weekday": "Должен быть список строк, например ['MO','WE']."})
        if interval < 1:
            raise serializers.ValidationError({"recurrence_interval": "Интервал должен быть >= 1."})
        return attrs

    def create(self, validated_data):
        participant_ids = validated_data.pop("participants", [])
        user: User = self.context["request"].user
        event = Event.objects.create(created_by=user, **validated_data)

        if user.role in ["student", "assistant"]:
            participant_ids = [user.id]

        users = User.objects.filter(id__in=set(participant_ids))
        EventParticipant.objects.bulk_create([
            EventParticipant(event=event, user=u) for u in users
        ], ignore_conflicts=True)
        if not event.participants.exists():
            EventParticipant.objects.create(event=event, user=user)
        return event

    def update(self, instance: Event, validated_data):
        participant_ids = validated_data.pop("participants", None)
        event = super().update(instance, validated_data)
        if participant_ids is not None:
            user: User = self.context["request"].user
            if user.role in ["student", "assistant"]:
                participant_ids = [user.id]
            users = User.objects.filter(id__in=set(participant_ids))
            event.participants.all().delete()
            EventParticipant.objects.bulk_create([
                EventParticipant(event=event, user=u) for u in users
            ], ignore_conflicts=True)
            if not event.participants.exists():
                EventParticipant.objects.create(event=event, user=user)
        return event


class DayNoteSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = DayNote
        fields = ("id", "user", "date", "timezone", "text", "reminder_enabled", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


