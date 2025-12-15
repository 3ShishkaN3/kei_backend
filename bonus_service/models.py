from django.db import models
from django.conf import settings
from material_service.models import VideoMaterial

class Bonus(models.Model):
    """Bonus model."""
    BONUS_TYPE_CHOICES = (
        ('video', 'Video'),
        ('copybook', 'Copybook'),
        ('avatar_frame', 'Avatar Frame'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price = models.PositiveIntegerField(default=100)
    bonus_type = models.CharField(max_length=20, choices=BONUS_TYPE_CHOICES, default='video')
    
    # For video bonuses
    video_material = models.ForeignKey(VideoMaterial, on_delete=models.SET_NULL, null=True, blank=True, related_name='bonuses')
    
    # For other types, we might add more fields later
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.price} coins)"

class UserBonus(models.Model):
    """User purchased bonuses."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchased_bonuses')
    bonus = models.ForeignKey(Bonus, on_delete=models.CASCADE, related_name='purchases')
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'bonus')

    def __str__(self):
        return f"{self.user.username} - {self.bonus.title}"
