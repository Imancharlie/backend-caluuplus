from django.contrib import admin
from .models import MrCaluuMessage, MrCaluuSettings


@admin.register(MrCaluuMessage)
class MrCaluuMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'text_preview', 'display_order', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['text']
    list_editable = ['display_order', 'is_active']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(MrCaluuSettings)
class MrCaluuSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ['updated_at']
