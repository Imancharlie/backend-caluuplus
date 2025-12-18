from django.urls import path
from . import views

urlpatterns = [
    # University/College/Program import
    path('university-programs/', views.upload_and_import_university_data, name='import-university-programs'),

    # Courses import
    path('courses/', views.upload_and_import_courses_data, name='import-courses'),

    # Import job management
    path('jobs/', views.get_import_jobs, name='import-jobs'),
    path('jobs/<uuid:job_id>/', views.get_import_job_detail, name='import-job-detail'),
]
