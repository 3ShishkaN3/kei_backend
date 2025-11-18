from rest_framework import serializers
from .models import Course, CourseTeacher, CourseAssistant, CourseEnrollment
from auth_service.serializers import UserSerializer


class CourseTeacherSerializer(serializers.ModelSerializer):
    teacher_details = UserSerializer(source='teacher', read_only=True)
    
    class Meta:
        model = CourseTeacher
        fields = ['id', 'teacher', 'teacher_details', 'is_primary', 'added_at']
        extra_kwargs = {
            'teacher': {'write_only': True},
        }


class CourseAssistantSerializer(serializers.ModelSerializer):
    assistant_details = UserSerializer(source='assistant', read_only=True)
    
    class Meta:
        model = CourseAssistant
        fields = ['id', 'assistant', 'assistant_details', 'added_at']
        extra_kwargs = {
            'assistant': {'write_only': True},
        }


class CourseListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.username')
    teacher_count = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'subtitle', 'description', 'status',
            'cover_image', 'created_by', 'created_by_name',
            'created_at', 'updated_at', 'teacher_count', 'student_count'
        ]
    
    def get_teacher_count(self, obj):
        return obj.teachers.count()
    
    def get_student_count(self, obj):
        return obj.enrollments.filter(status='active').count()


class CourseDetailSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    teachers = CourseTeacherSerializer(many=True, read_only=True)
    assistants = CourseAssistantSerializer(many=True, read_only=True)
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'subtitle', 'description', 'status',
            'cover_image', 'created_by', 'created_at',
            'updated_at', 'teachers', 'assistants'
        ]


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    student_details = UserSerializer(source='student', read_only=True)
    course_details = CourseListSerializer(source='course', read_only=True)
    
    class Meta:
        model = CourseEnrollment
        fields = [
            'id', 'course', 'course_details', 'student', 'student_details',
            'status', 'enrolled_at', 'completed_at'
        ]
        extra_kwargs = {
            'course': {'write_only': True},
            'student': {'write_only': True},
        }


class BulkEnrollmentSerializer(serializers.Serializer):
    """
    Сериализатор для массовой записи учеников на курс.
    """
    
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="Список ID учеников для записи на курс"
    )


class BulkLeaveSerializer(serializers.Serializer):
    """
    Сериализатор для массового отчисления учеников с курса.
    """
    
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="Список ID учеников для отчисления с курса"
    )