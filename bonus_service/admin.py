from django.contrib import admin
from .models import Bonus, UserBonus

@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'bonus_type', 'created_at')
    search_fields = ('title', 'description')
    list_filter = ('bonus_type',)

@admin.register(UserBonus)
class UserBonusAdmin(admin.ModelAdmin):
    list_display = ('user', 'bonus', 'purchased_at')
    search_fields = ('user__username', 'bonus__title')
    list_filter = ('purchased_at',)
