from rest_framework import serializers
from .models import DailyChallenge, ChallengeTest


class ChallengeTestSerializer(serializers.ModelSerializer):
    """Сериализатор связь Challenge ↔ Test — включает полные данные теста."""
    test_data = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeTest
        fields = ['id', 'order', 'test_data']

    def get_test_data(self, obj):
        """Возвращает полные данные теста через material_service.TestSerializer."""
        from material_service.serializers import TestSerializer
        from material_service.models import TestSubmission

        test_data = TestSerializer(obj.test, context=self.context).data
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return test_data

        # Это нужно, чтобы при повторном входе UI видел, что тест уже отправлен.
        latest_submission = (
            TestSubmission.objects
            .filter(
                student=user,
                test=obj.test,
                section_item__isnull=True,
            )
            .order_by('-submitted_at')
            .first()
        )

        if latest_submission:
            from material_service.serializers import TestSubmissionDetailSerializer
            test_data['student_submission_details'] = TestSubmissionDetailSerializer(
                latest_submission,
                context=self.context
            ).data

        return test_data


class DailyChallengeListSerializer(serializers.ModelSerializer):
    """Краткий сериализатор для списка/истории."""

    class Meta:
        model = DailyChallenge
        fields = [
            'id', 'date', 'generation_status', 'completion_status',
            'score', 'total_items', 'correct_items', 'coins_awarded',
            'completed_at',
        ]


class DailyChallengeDetailSerializer(serializers.ModelSerializer):
    """Полный сериализатор с тестами."""
    tests = serializers.SerializerMethodField()

    class Meta:
        model = DailyChallenge
        fields = [
            'id', 'date', 'generation_status', 'completion_status',
            'score', 'total_items', 'correct_items', 'coins_awarded',
            'blitz_quizzes', 'completed_at', 'tests',
        ]

    def get_tests(self, obj):
        """Возвращает тесты через ChallengeTest → TestSerializer."""
        challenge_tests = obj.challenge_tests.select_related(
            'test'
        ).prefetch_related(
            'test__mcq_options',
            'test__drag_drop_slots',
            'test__kanji_tracing_items',
        ).order_by('order')
        return ChallengeTestSerializer(
            challenge_tests, many=True, context=self.context
        ).data


class ChallengeStatusSerializer(serializers.ModelSerializer):
    """Сериализатор статуса (для кнопки на странице курса)."""
    progress = serializers.SerializerMethodField()

    class Meta:
        model = DailyChallenge
        fields = [
            'id', 'date', 'generation_status', 'completion_status',
            'score', 'total_items', 'correct_items', 'coins_awarded',
            'blitz_quizzes', 'progress',
        ]

    def get_progress(self, obj):
        """Прогресс генерации из Redis."""
        if obj.generation_status == 'generating':
            from .tasks import get_challenge_progress
            return get_challenge_progress(obj.id)
        return None
