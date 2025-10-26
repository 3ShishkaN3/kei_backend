from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    vk_link = models.URLField(blank=True, null=True)
    telegram_link = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    def clear_fields(self):
        self.phone_number = ""
        self.vk_link = ""
        self.telegram_link = ""
        self.bio = ""
        self.avatar = None
        self.save()
        
class UserSettings(models.Model):
    THEME_CHOICES = [
        ("light", "Светлая"),
        ("dark", "Тёмная"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    show_test_answers = models.BooleanField(default=True)
    show_learned_items = models.BooleanField(default=True)