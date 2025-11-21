from django.db import models
from django.conf import settings
from .compiler import GraphCompiler

class Achievement(models.Model):
    """
    Модель достижения с поддержкой гибких правил.
    """
    title = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(verbose_name="Описание")
    icon = models.ImageField(upload_to='achievements/icons/', verbose_name="Иконка", blank=True, null=True)
    xp_reward = models.PositiveIntegerField(default=0, verbose_name="Награда (XP)")
    
    # Структура графа для визуального редактора на фронтенде (Svelte Flow)
    rule_graph = models.JSONField(default=dict, blank=True, verbose_name="Граф правил (Frontend)")
    
    # Оптимизированная структура правил для выполнения на бекенде (Json Logic)
    compiled_rules = models.JSONField(default=dict, blank=True, verbose_name="Скомпилированные правила (Backend)")
    
    # Триггеры для быстрой фильтрации (какие события вызывают проверку этого достижения)
    triggers = models.JSONField(default=list, blank=True, verbose_name="Триггеры")
    
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Достижение"
        verbose_name_plural = "Достижения"

    def save(self, *args, **kwargs):
        # Compile graph before saving
        if self.rule_graph:
            try:
                self.triggers, self.compiled_rules = GraphCompiler.compile(self.rule_graph)
            except Exception as e:
                print(f"Error compiling achievement {self.title}: {e}")
                # Fallback or error handling? For now, just log.
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class UserAchievement(models.Model):
    """
    Связь пользователя с полученным достижением.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='achievements',
        verbose_name="Пользователь"
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='user_achievements',
        verbose_name="Достижение"
    )
    awarded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата получения")

    class Meta:
        verbose_name = "Достижение пользователя"
        verbose_name_plural = "Достижения пользователей"
        unique_together = ('user', 'achievement')

    def __str__(self):
        return f"{self.user} - {self.achievement}"
