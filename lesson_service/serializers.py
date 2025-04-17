from rest_framework import serializers
from .models import Lesson, Section, SectionCompletion, LessonCompletion
from auth_service.serializers import UserSerializer


class SectionSerializer(serializers.ModelSerializer):
    """Сериализатор для разделов урока."""
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            'id', 'lesson', 'title', 'order',
            'created_at', 'updated_at', 'is_completed'
        ]
        read_only_fields = ['lesson', 'created_at', 'updated_at', 'is_completed']

    def get_is_completed(self, obj):
        """Проверяет, завершил ли текущий пользователь этот раздел."""
        user = self.context['request'].user
        if user and user.is_authenticated:
            return SectionCompletion.objects.filter(section=obj, student=user).exists()
        return False

    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Порядок не может быть отрицательным.")
        return value


class LessonListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка уроков."""
    created_by_name = serializers.ReadOnlyField(source='created_by.username')
    section_count = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id') # Добавим ID курса

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'cover_image', 'course_id',
            'created_by_name', 'created_at', 'updated_at', 'section_count'
        ]

    def get_section_count(self, obj):
        """Возвращает количество разделов в уроке."""
        return obj.sections.count()


class LessonDetailSerializer(serializers.ModelSerializer):
    """Сериализатор для детальной информации об уроке."""
    created_by = UserSerializer(read_only=True)
    sections = SectionSerializer(many=True, read_only=True) 
    is_completed = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id')

    class Meta:
        model = Lesson
        fields = [
            'id', 'course_id', 'title', 'cover_image',
            'created_by', 'created_at', 'updated_at', 'sections', 'is_completed'
        ]
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'sections', 'is_completed', 'course_id')


    def get_is_completed(self, obj):
        """Проверяет, завершил ли текущий пользователь этот урок."""
        user = self.context['request'].user
        if user and user.is_authenticated:
            return LessonCompletion.objects.filter(lesson=obj, student=user).exists()
        return False

class SectionCompletionSerializer(serializers.ModelSerializer):
    """Сериализатор для отметки о завершении раздела."""
    student_details = UserSerializer(source='student', read_only=True)
    section_details = SectionSerializer(source='section', read_only=True)

    class Meta:
        model = SectionCompletion
        fields = ['id', 'section', 'section_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'section_details', 'completed_at']

class LessonCompletionSerializer(serializers.ModelSerializer):
    """Сериализатор для отметки о завершении урока."""
    student_details = UserSerializer(source='student', read_only=True)
    lesson_details = LessonListSerializer(source='lesson', read_only=True) # Используем ListSerializer для краткости

    class Meta:
        model = LessonCompletion
        fields = ['id', 'lesson', 'lesson_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'lesson_details', 'completed_at']