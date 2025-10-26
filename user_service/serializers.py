from rest_framework import serializers
from .models import UserProfile, UserSettings

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["phone_number", "vk_link", "telegram_link", "bio", "avatar"]
        

class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["theme", "show_test_answers"]
        
class UserAvatarSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["avatar"]