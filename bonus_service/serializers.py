from rest_framework import serializers
from .models import Bonus, UserBonus
from material_service.serializers import VideoMaterialSerializer

class BonusSerializer(serializers.ModelSerializer):
    is_purchased = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Bonus
        fields = ['id', 'title', 'description', 'price', 'bonus_type', 'video_material', 'is_purchased', 'video_url']

    def get_is_purchased(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return UserBonus.objects.filter(user=user, bonus=obj).exists()
        return False

    def get_video_url(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return None
            
        # Check if purchased or if user is staff (teachers should see it?)
        # For now, strictly check purchase for students.
        # We can optimize this by checking the context or prefetching, but for now simple query.
        if UserBonus.objects.filter(user=user, bonus=obj).exists() or user.is_staff:
            if obj.video_material and obj.video_material.video_file:
                return obj.video_material.video_file.url
        return None

class BuyBonusSerializer(serializers.Serializer):
    bonus_id = serializers.IntegerField()
