from rest_framework import serializers
from .models import UserProfile, UserSettings
from bonus_service.models import Bonus


class UserProfileSerializer(serializers.ModelSerializer):
    active_avatar_frame_id = serializers.PrimaryKeyRelatedField(
        source="active_avatar_frame",
        queryset=Bonus.objects.filter(bonus_type="avatar_frame"),
        required=False,
        allow_null=True,
    )
    active_avatar_frame_url = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            "phone_number",
            "vk_link",
            "telegram_link",
            "bio",
            "avatar",
            "active_avatar_frame_id",
            "active_avatar_frame_url",
        ]

    def get_active_avatar_frame_url(self, obj):
        if not obj.active_avatar_frame or not obj.active_avatar_frame.frame_image:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.active_avatar_frame.frame_image.url)
        return obj.active_avatar_frame.frame_image.url

    def validate_active_avatar_frame_id(self, value):
        if value is None:
            return value
        if value.bonus_type != "avatar_frame":
            raise serializers.ValidationError("Bonus is not an avatar frame.")
        user = self.context.get("request").user
        # Admin/teacher can wear any frame for free
        if getattr(user, "role", None) in ("admin", "teacher") or user.is_staff:
            return value
        from bonus_service.models import UserBonus
        if not UserBonus.objects.filter(user=user, bonus=value).exists():
            raise serializers.ValidationError(
                "You can only set an avatar frame that you have purchased."
            )
        return value
        

class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["theme", "show_test_answers"]
        
class UserAvatarSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["avatar"]