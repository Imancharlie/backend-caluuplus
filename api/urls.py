from django.urls import path
from . import views
from . import admin_views

urlpatterns = [
    # ==========================================================================
    # Admin Dashboard URLs (Template-based)
    # ==========================================================================
    path('dashboard/', admin_views.dashboard_home, name='dashboard-home'),
    path('dashboard/login/', admin_views.dashboard_login, name='dashboard-login'),
    path('dashboard/logout/', admin_views.dashboard_logout, name='dashboard-logout'),
    
    # Universities
    path('dashboard/universities/', admin_views.university_list, name='dashboard-universities'),
    path('dashboard/universities/create/', admin_views.university_create, name='dashboard-university-create'),
    path('dashboard/universities/<uuid:university_id>/edit/', admin_views.university_edit, name='dashboard-university-edit'),
    path('dashboard/universities/<uuid:university_id>/delete/', admin_views.university_delete, name='dashboard-university-delete'),
    
    # Colleges
    path('dashboard/colleges/', admin_views.college_list, name='dashboard-colleges'),
    path('dashboard/colleges/create/', admin_views.college_create, name='dashboard-college-create'),
    path('dashboard/colleges/<uuid:college_id>/edit/', admin_views.college_edit, name='dashboard-college-edit'),
    path('dashboard/colleges/<uuid:college_id>/delete/', admin_views.college_delete, name='dashboard-college-delete'),
    
    # Programs
    path('dashboard/programs/', admin_views.program_list, name='dashboard-programs'),
    path('dashboard/programs/create/', admin_views.program_create, name='dashboard-program-create'),
    path('dashboard/programs/<uuid:program_id>/edit/', admin_views.program_edit, name='dashboard-program-edit'),
    path('dashboard/programs/<uuid:program_id>/delete/', admin_views.program_delete, name='dashboard-program-delete'),
    
    # Courses
    path('dashboard/courses/', admin_views.course_list, name='dashboard-courses'),
    path('dashboard/courses/create/', admin_views.course_create, name='dashboard-course-create'),
    path('dashboard/courses/<uuid:course_id>/edit/', admin_views.course_edit, name='dashboard-course-edit'),
    path('dashboard/courses/<uuid:course_id>/delete/', admin_views.course_delete, name='dashboard-course-delete'),
    
    # Students
    path('dashboard/students/', admin_views.student_list, name='dashboard-students'),
    path('dashboard/students/<uuid:student_id>/', admin_views.student_detail, name='dashboard-student-detail'),
    
    # Import
    path('dashboard/import/', admin_views.import_data, name='dashboard-import'),
    path('dashboard/import/universities/', admin_views.import_universities, name='dashboard-import-universities'),
    path('dashboard/import/courses/', admin_views.import_courses, name='dashboard-import-courses'),
    
    # AJAX endpoints for dashboard
    path('dashboard/ajax/colleges/', admin_views.ajax_get_colleges, name='dashboard-ajax-colleges'),
    path('dashboard/ajax/programs/', admin_views.ajax_get_programs, name='dashboard-ajax-programs'),
    
    # ==========================================================================
    # API Endpoints (REST API)
    # ==========================================================================
    

    # Authentication endpoints
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('auth/firebase-login/', views.FirebaseLoginView.as_view(), name='firebase-login'),
    path('auth/change-password/', views.change_password, name='change-password'),
    path('auth/verify/', views.verify_token, name='verify-token'),
    path('auth/refresh/', views.refresh_token, name='refresh-token'),
    
    # University & Academic Structure endpoints
    path('universities/', views.UniversityListView.as_view(), name='university-list'),
    path('universities/<uuid:university_id>/colleges/', views.CollegeListView.as_view(), name='college-list'),
    path('colleges/<uuid:college_id>/programs/', views.ProgramListView.as_view(), name='program-list'),
    path('programs/<uuid:program_id>/courses/', views.CourseListView.as_view(), name='course-list'),
    
    # Student Management endpoints
    path('students/profile/', views.student_profile, name='student-profile'),
    path('students/profile/create/', views.student_profile_create, name='student-profile-create'),
    path('students/data/', views.student_data, name='student-data'),
    path('students/profile/options/', views.student_profile_options, name='student-profile-options'),
    
    # Course Management endpoints
    path('students/courses/', views.student_courses, name='student-courses'),
    path('students/courses/batch/', views.save_courses_batch, name='save-courses-batch'),
    path('students/courses/semester/<int:semester>/year/<int:year>/', views.get_student_courses_by_semester, name='get-courses-by-semester'),
    path('students/courses/filter/', views.get_student_courses_filtered, name='get-courses-filtered'),
    path('students/courses/<uuid:course_id>/', views.remove_course, name='remove-course'),
    
    # GPA Calculation endpoints
    path('students/gpa/', views.calculate_gpa, name='calculate-gpa'),
    path('students/gpa/target/', views.generate_target_gpa, name='generate-target-gpa'),
    path('students/gpa/reset/', views.reset_grades, name='reset-grades'),
    path('gpa/calculations/', views.gpa_calculation_create, name='gpa-calculation-create'),
    
    # User endpoints
    path('user/basic-details/', views.user_basic_details, name='user-basic-details'),
    path('user/update/', views.user_update, name='user-update'),
    path('user/hobbies/', views.user_hobbies, name='user-hobbies'),
    
    # User search for notifications
    path('users/search/', views.user_search, name='user-search'),

    # Notification endpoints
    path('notifications/unread-count/', views.notification_unread_count, name='notification-unread-count'),
    path('notifications/', views.notification_list, name='notification-list'),
    path('notifications/create/', views.notification_create, name='notification-create'),
    path('notifications/bulk/', views.notification_bulk, name='notification-bulk'),
    path('notifications/stream/', views.notification_stream, name='notification-stream'),
    path('notifications/<uuid:notification_id>/read/', views.notification_mark_read, name='notification-mark-read'),
    path('notifications/mark-all-read/', views.notification_mark_all_read, name='notification-mark-all-read'),
    path('notifications/<uuid:notification_id>/', views.notification_delete, name='notification-delete'),
    
    # Timetable endpoints
    path('timetable/my/', views.timetable_my, name='timetable-my'),
    path('timetable-slots/', views.timetable_slots, name='timetable-slots'),
    path('timetable-slots/<uuid:slot_id>/', views.timetable_slot_detail, name='timetable-slot-detail'),
    path('timetable-slots/bulk-create/', views.timetable_bulk_create, name='timetable-bulk-create'),
    path('timetable-slots/bulk-delete/', views.timetable_bulk_delete, name='timetable-bulk-delete'),
    path('timetable-slots/debug-request/', views.timetable_debug_request, name='timetable-debug-request'),
    path('timetable-slots/debug-validation/', views.timetable_debug_validation, name='timetable-debug-validation'),
    path('students/<uuid:student_id>/timetable/', views.timetable_my, name='student-timetable'),
    
    # Article endpoints
    path('articles/', views.article_list, name='article-list'),
    path('articles/<uuid:article_id>/', views.article_detail, name='article-detail'),
    path('articles/<uuid:article_id>/view/', views.article_view, name='article-view'),
    path('articles/categories/', views.article_categories, name='article-categories'),
    path('articles/<uuid:article_id>/like/', views.article_like, name='article-like'),
    path('articles/<uuid:article_id>/save/', views.article_save, name='article-save'),
    path('articles/<uuid:article_id>/share/', views.article_share, name='article-share'),
    path('articles/saved/', views.article_saved, name='article-saved'),
    
    # Slide endpoints
    path('slides/', views.slide_list, name='slide-list'),
    path('slides/<uuid:slide_id>/', views.slide_detail, name='slide-detail'),
    
    # Help Center endpoints
    path('help-center/messages/', views.submit_help_message, name='submit-help-message'),
    path('help-center/messages/list/', views.help_message_list, name='help-message-list'),
    path('help-center/messages/<uuid:message_id>/', views.help_message_detail, name='help-message-detail'),
    path('help-center/subjects/', views.help_message_subjects, name='help-message-subjects'),
    
    # Quote endpoints
    path('quotes/random/', views.quote_random, name='quote-random'),
    path('quotes/', views.quote_list, name='quote-list'),
    path('quotes/create/', views.quote_create, name='quote-create'),
    path('quotes/<uuid:quote_id>/', views.quote_detail, name='quote-detail'),

    # University Links endpoints
    path('university-links/', views.get_university_links, name='university-links'),
    
    # Dashboard & Statistics
    path('statistics/dashboard/', views.statistics_dashboard, name='statistics-dashboard'),

    # Staff & RBAC
    path('staff/me/roles/', views.staff_me_roles, name='staff-me-roles'),
    path('staff/ambassadors/', views.list_ambassadors, name='list-ambassadors'),
    path('staff/ambassadors/assign/', views.staff_ambassador_assign, name='staff-ambassador-assign'),
    path('staff/ambassadors/revoke/', views.staff_ambassador_revoke, name='staff-ambassador-revoke'),
    path('staff/ambassadors/<uuid:ambassador_id>/', views.update_ambassador, name='update-ambassador'),
    path('staff/ambassadors/<uuid:ambassador_id>/delete/', views.delete_ambassador, name='delete-ambassador'),
    path('staff/ambassadors/<uuid:ambassador_id>/activities/', views.ambassador_activities, name='ambassador-activities'),
    path('staff/messages/', views.get_ambassador_messages, name='get-ambassador-messages'),
    path('staff/messages/send/', views.send_ambassador_message, name='send-ambassador-message'),
    path('staff/messages/<uuid:message_id>/', views.mark_ambassador_message, name='mark-ambassador-message'),
    path('admin/search/', views.admin_search, name='admin-search'),
    path('admin/list/universities/', views.admin_list_universities, name='admin-list-universities'),
    path('admin/list/colleges/', views.admin_list_colleges, name='admin-list-colleges'),
    path('admin/list/programs/', views.admin_list_programs, name='admin-list-programs'),
    path('admin/list/courses/', views.admin_list_courses, name='admin-list-courses'),
    path('admin/list/students/', views.admin_list_students, name='admin-list-students'),
    path('admin/list/articles/', views.admin_list_articles, name='admin-list-articles'),
    path('admin/list/quotes/', views.admin_list_quotes, name='admin-list-quotes'),
    path('admin/list/notifications/', views.admin_list_notifications, name='admin-list-notifications'),
    path('admin/list/slides/', views.admin_list_slides, name='admin-list-slides'),

    # Admin endpoints for academic structure management
    path('admin/universities/', views.admin_create_university, name='admin-create-university'),
    path('admin/universities/<uuid:university_id>/', views.admin_delete_university, name='admin-delete-university'),
    path('admin/colleges/', views.admin_create_college, name='admin-create-college'),
    path('admin/colleges/<uuid:college_id>/', views.admin_delete_college, name='admin-delete-college'),
    path('admin/programs/', views.admin_create_program, name='admin-create-program'),
    path('admin/programs/<uuid:program_id>/', views.admin_delete_program, name='admin-delete-program'),
    path('admin/courses/', views.admin_create_course, name='admin-create-course'),
]
