from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, University, College, Program, Course, Student, StudentCourse, TimetableSlot, Article, Notification, Slide, HelpMessage, Quote, UniversityAmbassador, UniversityLink, GPACalculation


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'display_name', 'gender', 'phone_number', 'hobbies_display', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'gender', 'date_joined')
    search_fields = ('email', 'display_name', 'phone_number')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('display_name', 'first_name', 'last_name', 'gender', 'phone_number', 'hobbies')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'display_name', 'gender', 'phone_number', 'password1', 'password2'),
        }),
    )
    
    def hobbies_display(self, obj):
        """Display hobbies as a comma-separated list"""
        if obj.hobbies and isinstance(obj.hobbies, list):
            return ', '.join(obj.hobbies) if obj.hobbies else '-'
        return '-'
    hobbies_display.short_description = 'Hobbies'


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'created_at')
    list_filter = ('country', 'created_at')
    search_fields = ('name', 'country')


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'university', 'created_at')
    list_filter = ('university', 'created_at')
    search_fields = ('name', 'university__name')


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'duration', 'created_at')
    list_filter = ('college', 'duration', 'created_at')
    search_fields = ('name', 'college__name')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'credits', 'type', 'semester', 'year', 'program')
    list_filter = ('type', 'semester', 'year', 'program')
    search_fields = ('code', 'name', 'program__name')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'university', 'college', 'program', 'year', 'semester')
    list_filter = ('university', 'college', 'program', 'year', 'semester')
    search_fields = ('user__display_name', 'user__email', 'program__name')


@admin.register(StudentCourse)
class StudentCourseAdmin(admin.ModelAdmin):
    list_display = ('student', 'courses_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('student__user__display_name',)
    readonly_fields = ('courses',)
    
    def courses_count(self, obj):
        return len(obj.courses) if obj.courses else 0
    courses_count.short_description = 'Number of Courses'


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display = ('course_code', 'course_name', 'student', 'day_of_week', 'time_slot', 'venue', 'instructor', 'class_type', 'semester', 'academic_year')
    list_filter = ('day_of_week', 'semester', 'academic_year', 'class_type', 'created_at')
    search_fields = ('course_code', 'course_name', 'student__user__display_name', 'venue', 'instructor')
    ordering = ('day_of_week', 'time_slot')
    
    fieldsets = (
        ('Course Information', {
            'fields': ('course', 'course_code', 'course_name')
        }),
        ('Schedule', {
            'fields': ('day_of_week', 'time_slot', 'class_type', 'venue', 'instructor', 'description')
        }),
        ('Academic Info', {
            'fields': ('student', 'semester', 'academic_year')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'is_published', 'is_featured', 'views', 'likes', 'read_time', 'created_at')
    list_filter = ('category', 'status', 'is_published', 'is_featured', 'created_at')
    search_fields = ('title', 'content', 'author__display_name', 'tags')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Article Information', {
            'fields': ('title', 'content', 'excerpt', 'author', 'cover_image')
        }),
        ('Categorization', {
            'fields': ('category', 'tags', 'status')
        }),
        ('Status', {
            'fields': ('is_published', 'is_featured')
        }),
        ('Statistics', {
            'fields': ('views', 'likes', 'read_time', 'share_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('views', 'likes', 'share_count', 'created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'body', 'user__display_name', 'user__email')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Notification Content', {
            'fields': ('title', 'body', 'notification_type', 'link')
        }),
        ('User & Status', {
            'fields': ('user', 'is_read', 'read_at')
        }),
        ('Related Content', {
            'fields': ('slide',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at',)


@admin.register(Slide)
class SlideAdmin(admin.ModelAdmin):
    list_display = ('title', 'slide_type', 'is_active', 'order', 'start_date', 'end_date', 'created_at')
    list_filter = ('slide_type', 'is_active', 'created_at')
    search_fields = ('title', 'description')
    ordering = ('order', '-created_at')
    
    fieldsets = (
        ('Slide Content', {
            'fields': ('title', 'description', 'slide_type')
        }),
        ('Media', {
            'fields': ('image', 'image_url', 'link_url', 'button_text', 'background_gradient')
        }),
        ('Display Settings', {
            'fields': ('is_active', 'order')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(HelpMessage)
class HelpMessageAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'subject', 'user_name', 'user_email', 'status', 'created_at']
    list_filter = ['status', 'subject', 'created_at']
    search_fields = ['ticket_number', 'user_name', 'user_email', 'subject', 'message']
    readonly_fields = ['id', 'ticket_number', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Message Information', {
            'fields': ('subject', 'message', 'status')
        }),
        ('User Information', {
            'fields': ('user_name', 'user_email', 'user')
        }),
        ('Admin Response', {
            'fields': ('admin_response', 'admin_responded_at'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('id', 'ticket_number', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ['author', 'text_preview', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['author', 'text']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Quote Information', {
            'fields': ('text', 'author', 'is_active')
        }),
        ('System Information', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        })
    )
    
    def text_preview(self, obj):
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Text Preview'


@admin.register(UniversityAmbassador)
class UniversityAmbassadorAdmin(admin.ModelAdmin):
    list_display = ('user', 'university', 'created_at')
    list_filter = ('university', 'created_at')
    search_fields = ('user__email', 'user__display_name', 'university__name')


@admin.register(UniversityLink)
class UniversityLinkAdmin(admin.ModelAdmin):
    list_display = ('name', 'university', 'url', 'is_active', 'created_at')
    list_filter = ('university', 'is_active', 'created_at')
    search_fields = ('name', 'url', 'description', 'university__name')
    ordering = ('name',)

    fieldsets = (
        ('Link Information', {
            'fields': ('name', 'url', 'description')
        }),
        ('University Association', {
            'fields': ('university', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(GPACalculation)
class GPACalculationAdmin(admin.ModelAdmin):
    list_display = ('user', 'gpa', 'semester', 'academic_year', 'is_target', 'created_at')
    list_filter = ('is_target', 'semester', 'academic_year', 'created_at')
    search_fields = ('user__email', 'user__display_name')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('GPA Information', {
            'fields': ('user', 'gpa', 'semester', 'academic_year', 'is_target')
        }),
        ('System Information', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
