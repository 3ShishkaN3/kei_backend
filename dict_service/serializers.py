from rest_framework import serializers
from .models import DictionarySection, DictionaryEntry, UserLearnedEntry
from auth_service.serializers import UserSerializer

def get_user_show_learned_setting(user):
    if not user or not user.is_authenticated:
        return True 
    try:
        if hasattr(user, 'settings') and user.settings:
            return user.settings.show_learned_items
        else:
             return True
    except Exception:
        return True

class DictionarySectionSerializer(serializers.ModelSerializer):
    course_id = serializers.IntegerField(source='course.id', read_only=True)
    course = serializers.SerializerMethodField()
    created_by_details = UserSerializer(source='created_by', read_only=True)
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = DictionarySection
        fields = [
            'id', 'course_id', 'course', 'title', 'banner_image', 'is_primary',
            'created_by', 'created_by_details', 'created_at', 'updated_at', 'entry_count'
        ]
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'created_by_details', 'entry_count', 'course')

    def get_course(self, obj):
        """Возвращает информацию о курсе"""
        if obj.course:
            return {
                'id': obj.course.id,
                'title': obj.course.title
            }
        return None

    def get_entry_count(self, obj):
        return obj.entries.count()

class DictionaryEntrySerializer(serializers.ModelSerializer):
    section_id = serializers.IntegerField(source='section.id', read_only=True)
    lesson_id = serializers.IntegerField(source='lesson.id', read_only=True, allow_null=True)
    created_by_details = UserSerializer(source='created_by', read_only=True)
    pronunciation_audio_url = serializers.SerializerMethodField()
    is_learned = serializers.SerializerMethodField()

    class Meta:
        model = DictionaryEntry
        fields = [
            'id', 'section_id', 'lesson_id', 'term', 'reading', 'translation',
            'pronunciation_audio', 'pronunciation_audio_url',
            'created_by', 'created_by_details', 'created_at', 'updated_at',
            'is_learned'
        ]
        read_only_fields = (
            'section', 'created_by', 'created_at', 'updated_at',
            'created_by_details', 'pronunciation_audio_url', 'is_learned'
        )

    def get_pronunciation_audio_url(self, obj):
        request = self.context.get('request')
        if request and obj.pronunciation_audio:
            try:
                return request.build_absolute_uri(obj.pronunciation_audio.url)
            except ValueError:
                return None
        return None

    def get_is_learned(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return getattr(obj, 'user_has_learned', False)
        return False

class UserLearnedEntrySerializer(serializers.ModelSerializer):
    entry_id = serializers.IntegerField(source='entry.id')
    user_id = serializers.IntegerField(source='user.id')
    term = serializers.CharField(source='entry.term', read_only=True)
    class Meta:
        model = UserLearnedEntry
        fields = ['id', 'user_id', 'entry_id', 'term', 'learned_at']