from django.contrib import admin
from .models import Resource, Opportunity

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'university', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    list_filter = ('university', 'created_at')


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'university', 'created_by', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('category', 'university', 'created_at')
