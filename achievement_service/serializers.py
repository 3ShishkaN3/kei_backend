from rest_framework import serializers
from .models import Achievement, UserAchievement

class AchievementSerializer(serializers.ModelSerializer):
    is_unlocked = serializers.SerializerMethodField()
    awarded_at = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = [
            'id', 'title', 'description', 'icon', 'xp_reward', 
            'is_unlocked', 'awarded_at', 'rule_graph'
        ]
        read_only_fields = fields

    def get_is_unlocked(self, obj):
        user = self.context['request'].user
        if user.is_anonymous:
            return False
        return UserAchievement.objects.filter(user=user, achievement=obj).exists()

    def get_awarded_at(self, obj):
        user = self.context['request'].user
        if user.is_anonymous:
            return None
        try:
            ua = UserAchievement.objects.get(user=user, achievement=obj)
            return ua.awarded_at
        except UserAchievement.DoesNotExist:
            return None

class AdminAchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = '__all__'
