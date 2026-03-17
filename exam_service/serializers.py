from rest_framework import serializers
from .models import Exam, ExamSection, ExamSectionItem, ExamAttempt, ExamAnswer
from material_service.models import Test
from material_service.serializers import TestSerializer
from auth_service.serializers import UserSerializer


class ExamSectionItemSerializer(serializers.ModelSerializer):
    test_detail = TestSerializer(source='test', read_only=True)

    class Meta:
        model = ExamSectionItem
        fields = ['id', 'test', 'order', 'test_detail']


class ExamSectionSerializer(serializers.ModelSerializer):
    items = ExamSectionItemSerializer(many=True, read_only=True)

    class Meta:
        model = ExamSection
        fields = ['id', 'title', 'order', 'items']


class ExamListSerializer(serializers.ModelSerializer):
    sections_count = serializers.SerializerMethodField()
    has_attempt = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'description', 'duration_minutes',
            'is_published', 'require_camera', 'sections_count',
            'has_attempt', 'created_at'
        ]

    def get_sections_count(self, obj):
        return obj.sections.count()

    def get_has_attempt(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ExamAttempt.objects.filter(exam=obj, student=request.user).exists()
        return False


class ExamDetailSerializer(serializers.ModelSerializer):
    sections = ExamSectionSerializer(many=True, read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'description', 'duration_minutes',
            'is_published', 'require_camera', 'course', 'course_title',
            'sections', 'created_at'
        ]


class ExamSectionItemCreateSerializer(serializers.Serializer):
    test_id = serializers.IntegerField()
    order = serializers.IntegerField()


class ExamSectionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    order = serializers.IntegerField()
    items = ExamSectionItemCreateSerializer(many=True, required=False)


class ExamCreateSerializer(serializers.ModelSerializer):
    sections = ExamSectionCreateSerializer(many=True, required=False)

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'description', 'duration_minutes',
            'is_published', 'require_camera', 'course', 'sections'
        ]

    def create(self, validated_data):
        sections_data = validated_data.pop('sections', [])
        exam = Exam.objects.create(**validated_data)

        for section_data in sections_data:
            items_data = section_data.pop('items', [])
            section = ExamSection.objects.create(exam=exam, **section_data)
            for item_data in items_data:
                ExamSectionItem.objects.create(
                    section=section,
                    test_id=item_data['test_id'],
                    order=item_data['order']
                )
        return exam

    def update(self, instance, validated_data):
        sections_data = validated_data.pop('sections', None)
        
        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.duration_minutes = validated_data.get('duration_minutes', instance.duration_minutes)
        instance.is_published = validated_data.get('is_published', instance.is_published)
        instance.require_camera = validated_data.get('require_camera', instance.require_camera)
        instance.save()

        if sections_data is not None:
            instance.sections.all().delete()
            for section_data in sections_data:
                items_data = section_data.pop('items', [])
                section = ExamSection.objects.create(exam=instance, **section_data)
                for item_data in items_data:
                    ExamSectionItem.objects.create(
                        section=section,
                        test_id=item_data['test_id'],
                        order=item_data['order']
                    )
        return instance


class ExamAnswerInputSerializer(serializers.Serializer):
    exam_section_item_id = serializers.IntegerField()
    answer_data = serializers.DictField()
    submitted_file = serializers.FileField(required=False, allow_null=True)


class ExamSectionSubmitSerializer(serializers.Serializer):
    section_order = serializers.IntegerField()
    answers = ExamAnswerInputSerializer(many=True)


class ExamAnswerSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='exam_section_item.test.title', read_only=True)
    test_type = serializers.CharField(source='exam_section_item.test.test_type', read_only=True)

    class Meta:
        model = ExamAnswer
        fields = [
            'id', 'exam_section_item', 'test_title', 'test_type',
            'answer_data', 'submitted_file', 'score', 'is_correct', 'submitted_at'
        ]


class ExamAttemptSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    deadline = serializers.DateTimeField(read_only=True)
    answers = ExamAnswerSerializer(many=True, read_only=True)
    student_details = UserSerializer(source='student', read_only=True)

    class Meta:
        model = ExamAttempt
        fields = [
            'id', 'exam', 'exam_title', 'student', 'student_details', 'status',
            'current_section_order', 'started_at', 'finished_at',
            'deadline', 'total_score', 'max_possible_score',
            'camera_violation_seconds', 'answers'
        ]
        read_only_fields = ['student', 'started_at', 'finished_at', 'total_score']


class GradeAnswerSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_correct = serializers.BooleanField(required=False, default=True)


class ExamSectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamSection
        fields = ['id', 'title', 'order']
        extra_kwargs = {'order': {'required': False}}


class ExamSectionItemWriteSerializer(serializers.ModelSerializer):
    test_data = TestSerializer(write_only=True, required=False, allow_null=True)
    test = serializers.PrimaryKeyRelatedField(
        queryset=Test.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = ExamSectionItem
        fields = ['id', 'test', 'order', 'test_data']
        extra_kwargs = {'order': {'required': False}}

    def create(self, validated_data):
        test_data = validated_data.pop('test_data', None)
        test_id = validated_data.get('test')

        if test_data and not test_id:
            test_serializer = TestSerializer(data=test_data, context=self.context)
            test_serializer.is_valid(raise_exception=True)
            test = test_serializer.save()
            validated_data['test'] = test
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        test_data = validated_data.pop('test_data', None)
        test_id = validated_data.get('test')

        if test_data:
            test_serializer = TestSerializer(
                instance.test, data=test_data, partial=True, context=self.context
            )
            test_serializer.is_valid(raise_exception=True)
            test_serializer.save()
        
        if test_id:
            instance.test = test_id

        return super().update(instance, validated_data)

