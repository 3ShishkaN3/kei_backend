from rest_framework import serializers
from .models import Bonus, UserBonus
from material_service.serializers import VideoMaterialSerializer

class BonusSerializer(serializers.ModelSerializer):
    video_file = serializers.FileField(write_only=True, required=False)
    is_purchased = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Bonus
        fields = ['id', 'title', 'description', 'price', 'bonus_type', 'video_material', 'is_purchased', 'video_url', 'video_file']
        read_only_fields = ['video_material']

    def get_is_purchased(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return False
        return UserBonus.objects.filter(user=user, bonus=obj).exists()

    def get_video_url(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
            
        if UserBonus.objects.filter(user=request.user, bonus=obj).exists() or request.user.is_staff:
            if obj.video_material and obj.video_material.video_file:
                return request.build_absolute_uri(obj.video_material.video_file.url)
        return None

    def create(self, validated_data):
        video_file = validated_data.pop('video_file', None)
        bonus = Bonus.objects.create(**validated_data)
        
        if video_file:
            from material_service.models import VideoMaterial
            video_material = VideoMaterial.objects.create(
                title=f"Video for bonus: {bonus.title}",
                source_type='file',
                video_file=video_file,
                created_by=self.context['request'].user
            )
            bonus.video_material = video_material
            bonus.save()
            
        return bonus

    def update(self, instance, validated_data):
        video_file = validated_data.pop('video_file', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if video_file:
            from material_service.models import VideoMaterial
            if instance.video_material:
                instance.video_material.video_file = video_file
                instance.video_material.save()
            else:
                video_material = VideoMaterial.objects.create(
                    title=f"Video for bonus: {instance.title}",
                    source_type='file',
                    video_file=video_file,
                    created_by=self.context['request'].user
                )
                instance.video_material = video_material
                instance.save()
                
        return instance

class BuyBonusSerializer(serializers.Serializer):
    bonus_id = serializers.IntegerField()
