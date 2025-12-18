from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
import csv
import json
from .models import (
    Conversation, Message, ChatHistory, KnowledgeDocument,
    SiteNavigation, Feedback, ConversationAnalytics
)
from api.models import University


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'is_active', 'created_at', 'updated_at', 'message_count']
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['user__display_name', 'user__email', 'title']
    readonly_fields = ['id', 'created_at', 'updated_at', 'message_count']
    ordering = ['-updated_at']
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'role', 'content_preview', 'topic', 'tokens_used', 'cost_tsh', 'timestamp']
    list_filter = ['role', 'topic', 'timestamp']
    search_fields = ['conversation__user__display_name', 'conversation__user__email', 'content', 'topic']
    readonly_fields = ['id', 'timestamp']
    ordering = ['-timestamp']
    
    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content Preview'


@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'total_conversations', 'total_messages', 'total_tokens', 'total_cost_tsh', 'last_updated']
    list_filter = ['last_updated', 'created_at']
    search_fields = ['user__display_name', 'user__email']
    readonly_fields = ['id', 'created_at', 'last_updated']
    ordering = ['-last_updated']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Personalization', {
            'fields': ('personality_notes', 'instructions'),
            'classes': ('wide',)
        }),
        ('Statistics', {
            'fields': ('total_conversations', 'total_messages', 'total_tokens', 'total_cost_tsh')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_updated'),
            'classes': ('collapse',)
        })
    )


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'category', 'university', 'priority', 'usage_count', 'is_active', 'created_at']
    list_filter = ['category', 'university', 'is_active', 'priority', 'created_at']
    search_fields = ['title', 'content', 'category', 'tags']
    readonly_fields = ['id', 'created_at', 'updated_at', 'usage_count']
    ordering = ['-priority', '-usage_count', '-created_at']
    actions = ['export_selected', 'deactivate_selected', 'activate_selected']
    
    fieldsets = (
        ('Document Information', {
            'fields': ('title', 'content', 'category', 'tags')
        }),
        ('Scope & Priority', {
            'fields': ('university', 'priority', 'is_active')
        }),
        ('Usage Statistics', {
            'fields': ('usage_count',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('university')
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-import/', self.admin_site.admin_view(self.bulk_import_view), name='chatbot_knowledgedocument_bulk_import'),
        ]
        return custom_urls + urls
    
    def bulk_import_view(self, request):
        """Bulk import knowledge documents from CSV or JSON"""
        if request.method == 'POST':
            file = request.FILES.get('file')
            file_type = request.POST.get('file_type', 'csv')
            university_id = request.POST.get('university')
            university = None
            
            if university_id:
                try:
                    university = University.objects.get(id=university_id)
                except University.DoesNotExist:
                    messages.error(request, 'University not found')
                    return redirect('admin:chatbot_knowledgedocument_bulk_import')
            
            if not file:
                messages.error(request, 'Please select a file')
                return redirect('admin:chatbot_knowledgedocument_bulk_import')
            
            try:
                imported = 0
                errors = []
                
                if file_type == 'csv':
                    # CSV format: title,content,category,tags,priority
                    decoded_file = file.read().decode('utf-8')
                    csv_reader = csv.DictReader(decoded_file.splitlines())
                    
                    for row_num, row in enumerate(csv_reader, start=2):
                        try:
                            KnowledgeDocument.objects.create(
                                title=row.get('title', '').strip(),
                                content=row.get('content', '').strip(),
                                category=row.get('category', 'faq').strip(),
                                tags=row.get('tags', '').strip(),
                                priority=int(row.get('priority', 5)),
                                university=university,
                                is_active=True
                            )
                            imported += 1
                        except Exception as e:
                            errors.append(f"Row {row_num}: {str(e)}")
                
                elif file_type == 'json':
                    # JSON format: [{"title": "...", "content": "...", ...}, ...]
                    data = json.loads(file.read().decode('utf-8'))
                    
                    if not isinstance(data, list):
                        messages.error(request, 'JSON file must contain an array of documents')
                        return redirect('admin:chatbot_knowledgedocument_bulk_import')
                    
                    for item_num, item in enumerate(data, start=1):
                        try:
                            KnowledgeDocument.objects.create(
                                title=item.get('title', '').strip(),
                                content=item.get('content', '').strip(),
                                category=item.get('category', 'faq').strip(),
                                tags=item.get('tags', '').strip(),
                                priority=int(item.get('priority', 5)),
                                university=university,
                                is_active=True
                            )
                            imported += 1
                        except Exception as e:
                            errors.append(f"Item {item_num}: {str(e)}")
                
                if imported > 0:
                    messages.success(request, f'Successfully imported {imported} knowledge documents')
                if errors:
                    messages.warning(request, f'{len(errors)} errors occurred. Check logs for details.')
                    for error in errors[:10]:  # Show first 10 errors
                        messages.error(request, error)
                
            except Exception as e:
                messages.error(request, f'Error importing file: {str(e)}')
            
            return redirect('admin:chatbot_knowledgedocument_changelist')
        
        # GET request - show upload form
        universities = University.objects.all().order_by('name')
        context = {
            'title': 'Bulk Import Knowledge Documents',
            'universities': universities,
        }
        return render(request, 'admin/chatbot/knowledgedocument/bulk_import.html', context)
    
    def export_selected(self, request, queryset):
        """Export selected knowledge documents to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="knowledge_documents.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['title', 'content', 'category', 'tags', 'priority', 'university', 'is_active'])
        
        for doc in queryset:
            writer.writerow([
                doc.title,
                doc.content,
                doc.category,
                doc.tags or '',
                doc.priority,
                doc.university.name if doc.university else '',
                doc.is_active
            ])
        
        return response
    export_selected.short_description = 'Export selected documents to CSV'
    
    def deactivate_selected(self, request, queryset):
        """Deactivate selected knowledge documents"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} documents deactivated')
    deactivate_selected.short_description = 'Deactivate selected documents'
    
    def activate_selected(self, request, queryset):
        """Activate selected knowledge documents"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} documents activated')
    activate_selected.short_description = 'Activate selected documents'


@admin.register(SiteNavigation)
class SiteNavigationAdmin(admin.ModelAdmin):
    list_display = ['name', 'route', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'route', 'description', 'keywords']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['name']
    
    fieldsets = (
        ('Navigation Information', {
            'fields': ('name', 'route', 'description', 'icon')
        }),
        ('Search & Discovery', {
            'fields': ('keywords',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'rating', 'query_preview', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['user__display_name', 'user__email', 'query', 'response', 'comment']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
    filter_horizontal = ['knowledge_documents_used']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'conversation', 'message')
        }),
        ('Feedback', {
            'fields': ('rating', 'comment')
        }),
        ('Context', {
            'fields': ('query', 'response', 'knowledge_documents_used'),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def query_preview(self, obj):
        return obj.query[:100] + '...' if len(obj.query) > 100 else obj.query
    query_preview.short_description = 'Query Preview'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'conversation', 'message')


@admin.register(ConversationAnalytics)
class ConversationAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'query_intent', 'avg_rating', 'feedback_count', 'total_api_calls', 'total_cache_hits', 'updated_at']
    list_filter = ['query_intent', 'updated_at']
    search_fields = ['conversation__title', 'conversation__user__display_name', 'query_intent']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-updated_at']
    
    fieldsets = (
        ('Conversation', {
            'fields': ('conversation',)
        }),
        ('Query Analysis', {
            'fields': ('query_intent', 'common_topics', 'knowledge_gaps'),
            'classes': ('wide',)
        }),
        ('Performance Metrics', {
            'fields': ('avg_response_time', 'total_api_calls', 'total_cache_hits')
        }),
        ('User Satisfaction', {
            'fields': ('avg_rating', 'feedback_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('conversation', 'conversation__user')
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        # Add link to bulk import
        extra_context['bulk_import_url'] = 'bulk-import/'
        return super().changelist_view(request, extra_context=extra_context)