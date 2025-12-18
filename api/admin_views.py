"""
Admin Dashboard Views for Caluu+ Multi-University Management System

This module provides Django template-based views for managing:
- Universities
- Colleges
- Programs
- Courses
- Students
- Data Import (Excel/CSV)

All views support both Django session authentication and JWT authentication.
"""

import os
import uuid
import logging
import pandas as pd
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.conf import settings
from django.views.decorators.http import require_http_methods

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import (
    University,
    College,
    Program,
    Course,
    Student,
    User,
    GPACalculation,
    LoginActivity,
)
from .permissions import user_is_admin
from datetime import timedelta
from django.db.models import Avg
from django.db.models.functions import TruncDate, TruncMonth

logger = logging.getLogger(__name__)


# =============================================================================
# Authentication Decorator (supports both session and JWT)
# =============================================================================

def admin_required(view_func):
    """
    Decorator that checks for either Django session auth or JWT token.
    Ensures user is admin (is_staff or is_superuser).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = None
        
        # First check Django session auth
        if request.user.is_authenticated:
            user = request.user
        else:
            # Try JWT authentication
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    jwt_auth = JWTAuthentication()
                    validated_token = jwt_auth.get_validated_token(auth_header.split(' ')[1])
                    user = jwt_auth.get_user(validated_token)
                    request.user = user
                except (InvalidToken, TokenError):
                    pass
        
        if not user:
            return redirect('dashboard-login')
        
        if not (user.is_staff or user.is_superuser):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard-login')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# =============================================================================
# Authentication Views
# =============================================================================

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def record_login_activity(user, request, login_type='email', success=True):
    """Record a login activity for analytics"""
    try:
        LoginActivity.objects.create(
            user=user,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            login_type=login_type,
            success=success
        )
    except Exception as e:
        logger.error(f"Failed to record login activity: {e}")


def dashboard_login(request):
    """Login view for admin dashboard"""
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard-home')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            if user.is_staff or user.is_superuser:
                login(request, user)
                # Record login activity
                record_login_activity(user, request, login_type='admin', success=True)
                messages.success(request, f'Welcome back, {user.display_name}!')
                return redirect('dashboard-home')
            else:
                return render(request, 'dashboard/login.html', {
                    'error': 'You do not have admin privileges.'
                })
        else:
            return render(request, 'dashboard/login.html', {
                'error': 'Invalid email or password.'
            })
    
    return render(request, 'dashboard/login.html')


def dashboard_logout(request):
    """Logout view for admin dashboard"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('dashboard-login')


# =============================================================================
# Dashboard Home View
# =============================================================================

@admin_required
def dashboard_home(request):
    """Main dashboard with comprehensive statistics and analytics"""
    now = timezone.now()
    today = now.date()
    
    # Date ranges
    last_30_days = now - timedelta(days=30)
    last_7_days = now - timedelta(days=7)
    last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # =========================================================================
    # Basic Statistics
    # =========================================================================
    stats = {
        'universities': University.objects.count(),
        'colleges': College.objects.count(),
        'programs': Program.objects.count(),
        'courses': Course.objects.count(),
        'students': Student.objects.count(),
        'users': User.objects.count(),
        'gpa_calculations': GPACalculation.objects.count(),
        'logins_today': LoginActivity.objects.filter(login_time__date=today).count(),
    }
    
    # =========================================================================
    # User Growth Analytics (Last 30 days)
    # =========================================================================
    user_growth_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        count = User.objects.filter(date_joined__date=date).count()
        user_growth_data.append({
            'date': date.strftime('%b %d'),
            'count': count
        })
    
    # Calculate growth percentage
    users_this_month = User.objects.filter(date_joined__gte=this_month_start).count()
    users_last_month = User.objects.filter(
        date_joined__gte=last_month_start,
        date_joined__lt=this_month_start
    ).count()
    user_growth_percent = 0
    if users_last_month > 0:
        user_growth_percent = round(((users_this_month - users_last_month) / users_last_month) * 100, 1)
    
    # =========================================================================
    # GPA Calculator Usage Analytics
    # =========================================================================
    gpa_usage_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        count = GPACalculation.objects.filter(created_at__date=date).count()
        gpa_usage_data.append({
            'date': date.strftime('%b %d'),
            'count': count
        })
    
    # GPA calculations by program (top 7)
    gpa_by_program = []
    programs_with_students = Program.objects.annotate(
        student_count=Count('students')
    ).filter(student_count__gt=0)[:7]
    
    for program in programs_with_students:
        # Get GPA calculations for students in this program
        student_ids = program.students.values_list('user_id', flat=True)
        gpa_count = GPACalculation.objects.filter(user_id__in=student_ids).count()
        
        gpa_by_program.append({
            'name': program.name[:30] + ('...' if len(program.name) > 30 else ''),
            'count': gpa_count,
        })
    
    # Sort by count
    gpa_by_program.sort(key=lambda x: x['count'], reverse=True)
    
    # GPA calculations by academic year (1, 2, 3, 4)
    gpa_by_year = []
    for year in range(1, 5):  # Years 1-4
        # Get students in this academic year
        student_ids = Student.objects.filter(year=year).values_list('user_id', flat=True)
        gpa_count = GPACalculation.objects.filter(user_id__in=student_ids).count()
        gpa_by_year.append({
            'year': year,
            'count': gpa_count,
        })
    
    # =========================================================================
    # Students by College Distribution
    # =========================================================================
    students_by_college = College.objects.annotate(
        student_count=Count('students')
    ).filter(student_count__gt=0).values('name', 'student_count').order_by('-student_count')[:10]
    
    # =========================================================================
    # Students by Program (Top 7)
    # =========================================================================
    students_by_program = Program.objects.annotate(
        student_count=Count('students')
    ).filter(student_count__gt=0).values('name', 'student_count').order_by('-student_count')[:7]
    
    # =========================================================================
    # Login Activity Analytics (Last 30 days)
    # =========================================================================
    login_activity_data = []
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        # Unique users who logged in
        unique_logins = LoginActivity.objects.filter(
            login_time__date=date
        ).values('user').distinct().count()
        total_logins = LoginActivity.objects.filter(login_time__date=date).count()
        login_activity_data.append({
            'date': date.strftime('%b %d'),
            'unique_users': unique_logins,
            'total_logins': total_logins
        })
    
    
    # =========================================================================
    # Recent Activity Feed
    # =========================================================================
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_gpa_calculations = GPACalculation.objects.select_related('user').order_by('-created_at')[:5]
    recent_logins = LoginActivity.objects.select_related('user').order_by('-login_time')[:5]
    recent_students = Student.objects.select_related('user', 'university', 'program').order_by('-created_at')[:5]
    
    # =========================================================================
    # Trend Calculations
    # =========================================================================
    # Students trend
    students_this_month = Student.objects.filter(created_at__gte=this_month_start).count()
    students_last_month = Student.objects.filter(
        created_at__gte=last_month_start,
        created_at__lt=this_month_start
    ).count()
    student_growth_percent = 0
    if students_last_month > 0:
        student_growth_percent = round(((students_this_month - students_last_month) / students_last_month) * 100, 1)
    
    # GPA usage trend
    gpa_this_month = GPACalculation.objects.filter(created_at__gte=this_month_start).count()
    gpa_last_month = GPACalculation.objects.filter(
        created_at__gte=last_month_start,
        created_at__lt=this_month_start
    ).count()
    gpa_growth_percent = 0
    if gpa_last_month > 0:
        gpa_growth_percent = round(((gpa_this_month - gpa_last_month) / gpa_last_month) * 100, 1)
    
    # Logins trend
    logins_this_week = LoginActivity.objects.filter(login_time__gte=last_7_days).count()
    logins_last_week = LoginActivity.objects.filter(
        login_time__gte=last_7_days - timedelta(days=7),
        login_time__lt=last_7_days
    ).count()
    login_growth_percent = 0
    if logins_last_week > 0:
        login_growth_percent = round(((logins_this_week - logins_last_week) / logins_last_week) * 100, 1)
    
    context = {
        'active_page': 'dashboard',
        'stats': stats,
        
        # Growth and trends
        'user_growth_percent': user_growth_percent,
        'student_growth_percent': student_growth_percent,
        'gpa_growth_percent': gpa_growth_percent,
        'login_growth_percent': login_growth_percent,
        
        # Chart data (JSON)
        'user_growth_data': user_growth_data,
        'gpa_usage_data': gpa_usage_data,
        'gpa_by_program': gpa_by_program,
        'gpa_by_year': gpa_by_year,
        'students_by_college': list(students_by_college),
        'students_by_program': list(students_by_program),
        'login_activity_data': login_activity_data,
        
        # Recent activity
        'recent_users': recent_users,
        'recent_gpa_calculations': recent_gpa_calculations,
        'recent_logins': recent_logins,
        'recent_students': recent_students,
    }
    
    return render(request, 'dashboard/dashboard.html', context)


# =============================================================================
# University Views
# =============================================================================

@admin_required
def university_list(request):
    """List all universities with search and pagination"""
    search = request.GET.get('search', '').strip()
    
    universities = University.objects.annotate(
        college_count=Count('colleges'),
        program_count=Count('colleges__programs'),
        student_count=Count('students')
    ).order_by('-created_at')
    
    if search:
        universities = universities.filter(
            Q(name__icontains=search) | Q(country__icontains=search)
        )
    
    paginator = Paginator(universities, 15)
    page = request.GET.get('page', 1)
    universities = paginator.get_page(page)
    
    context = {
        'active_page': 'universities',
        'universities': universities,
        'search': search,
    }
    
    return render(request, 'dashboard/universities/list.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def university_create(request):
    """Create a new university"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        country = request.POST.get('country', '').strip()
        
        if not name:
            messages.error(request, 'University name is required.')
            return render(request, 'dashboard/universities/form.html', {
                'active_page': 'universities',
                'form_title': 'Add University',
                'name': name,
                'country': country,
            })
        
        # Check for duplicate
        if University.objects.filter(name__iexact=name).exists():
            messages.error(request, f'University "{name}" already exists.')
            return render(request, 'dashboard/universities/form.html', {
                'active_page': 'universities',
                'form_title': 'Add University',
                'name': name,
                'country': country,
            })
        
        university = University.objects.create(
            name=name,
            country=country or 'Tanzania'
        )
        
        messages.success(request, f'University "{name}" created successfully.')
        return redirect('dashboard-universities')
    
    context = {
        'active_page': 'universities',
        'form_title': 'Add University',
    }
    return render(request, 'dashboard/universities/form.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def university_edit(request, university_id):
    """Edit an existing university"""
    university = get_object_or_404(University, id=university_id)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        country = request.POST.get('country', '').strip()
        
        if not name:
            messages.error(request, 'University name is required.')
            return render(request, 'dashboard/universities/form.html', {
                'active_page': 'universities',
                'form_title': 'Edit University',
                'university': university,
                'name': name,
                'country': country,
            })
        
        # Check for duplicate (excluding current)
        if University.objects.filter(name__iexact=name).exclude(id=university_id).exists():
            messages.error(request, f'University "{name}" already exists.')
            return render(request, 'dashboard/universities/form.html', {
                'active_page': 'universities',
                'form_title': 'Edit University',
                'university': university,
                'name': name,
                'country': country,
            })
        
        university.name = name
        university.country = country or 'Tanzania'
        university.save()
        
        messages.success(request, f'University "{name}" updated successfully.')
        return redirect('dashboard-universities')
    
    context = {
        'active_page': 'universities',
        'form_title': 'Edit University',
        'university': university,
        'name': university.name,
        'country': university.country,
    }
    return render(request, 'dashboard/universities/form.html', context)


@admin_required
@require_http_methods(["POST"])
def university_delete(request, university_id):
    """Delete a university"""
    university = get_object_or_404(University, id=university_id)
    name = university.name
    university.delete()
    messages.success(request, f'University "{name}" deleted successfully.')
    return redirect('dashboard-universities')


# =============================================================================
# College Views
# =============================================================================

@admin_required
def college_list(request):
    """List all colleges with search and pagination"""
    search = request.GET.get('search', '').strip()
    university_filter = request.GET.get('university', '')
    
    colleges = College.objects.select_related('university').annotate(
        program_count=Count('programs'),
        student_count=Count('students')
    ).order_by('university__name', 'name')
    
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) | Q(university__name__icontains=search)
        )
    
    if university_filter:
        colleges = colleges.filter(university_id=university_filter)
    
    paginator = Paginator(colleges, 15)
    page = request.GET.get('page', 1)
    colleges = paginator.get_page(page)
    
    universities = University.objects.all().order_by('name')
    
    context = {
        'active_page': 'colleges',
        'colleges': colleges,
        'universities': universities,
        'search': search,
        'university_filter': university_filter,
    }
    
    return render(request, 'dashboard/colleges/list.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def college_create(request):
    """Create a new college"""
    universities = University.objects.all().order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        university_id = request.POST.get('university', '')
        
        if not name or not university_id:
            messages.error(request, 'College name and university are required.')
            return render(request, 'dashboard/colleges/form.html', {
                'active_page': 'colleges',
                'form_title': 'Add College',
                'universities': universities,
                'name': name,
                'university_id': university_id,
            })
        
        university = get_object_or_404(University, id=university_id)
        
        # Check for duplicate within university
        if College.objects.filter(name__iexact=name, university=university).exists():
            messages.error(request, f'College "{name}" already exists in {university.name}.')
            return render(request, 'dashboard/colleges/form.html', {
                'active_page': 'colleges',
                'form_title': 'Add College',
                'universities': universities,
                'name': name,
                'university_id': university_id,
            })
        
        college = College.objects.create(name=name, university=university)
        
        messages.success(request, f'College "{name}" created successfully.')
        return redirect('dashboard-colleges')
    
    context = {
        'active_page': 'colleges',
        'form_title': 'Add College',
        'universities': universities,
    }
    return render(request, 'dashboard/colleges/form.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def college_edit(request, college_id):
    """Edit an existing college"""
    college = get_object_or_404(College, id=college_id)
    universities = University.objects.all().order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        university_id = request.POST.get('university', '')
        
        if not name or not university_id:
            messages.error(request, 'College name and university are required.')
            return render(request, 'dashboard/colleges/form.html', {
                'active_page': 'colleges',
                'form_title': 'Edit College',
                'college': college,
                'universities': universities,
                'name': name,
                'university_id': university_id,
            })
        
        university = get_object_or_404(University, id=university_id)
        
        # Check for duplicate (excluding current)
        if College.objects.filter(name__iexact=name, university=university).exclude(id=college_id).exists():
            messages.error(request, f'College "{name}" already exists in {university.name}.')
            return render(request, 'dashboard/colleges/form.html', {
                'active_page': 'colleges',
                'form_title': 'Edit College',
                'college': college,
                'universities': universities,
                'name': name,
                'university_id': university_id,
            })
        
        college.name = name
        college.university = university
        college.save()
        
        messages.success(request, f'College "{name}" updated successfully.')
        return redirect('dashboard-colleges')
    
    context = {
        'active_page': 'colleges',
        'form_title': 'Edit College',
        'college': college,
        'universities': universities,
        'name': college.name,
        'university_id': str(college.university_id),
    }
    return render(request, 'dashboard/colleges/form.html', context)


@admin_required
@require_http_methods(["POST"])
def college_delete(request, college_id):
    """Delete a college"""
    college = get_object_or_404(College, id=college_id)
    name = college.name
    college.delete()
    messages.success(request, f'College "{name}" deleted successfully.')
    return redirect('dashboard-colleges')


# =============================================================================
# Program Views
# =============================================================================

@admin_required
def program_list(request):
    """List all programs with search and pagination"""
    search = request.GET.get('search', '').strip()
    university_filter = request.GET.get('university', '')
    college_filter = request.GET.get('college', '')
    
    programs = Program.objects.select_related('college__university').annotate(
        course_count=Count('courses'),
        student_count=Count('students')
    ).order_by('college__university__name', 'college__name', 'name')
    
    if search:
        programs = programs.filter(
            Q(name__icontains=search) | 
            Q(college__name__icontains=search) |
            Q(college__university__name__icontains=search)
        )
    
    if university_filter:
        programs = programs.filter(college__university_id=university_filter)
    
    if college_filter:
        programs = programs.filter(college_id=college_filter)
    
    paginator = Paginator(programs, 15)
    page = request.GET.get('page', 1)
    programs = paginator.get_page(page)
    
    universities = University.objects.all().order_by('name')
    colleges = College.objects.all().order_by('name')
    
    context = {
        'active_page': 'programs',
        'programs': programs,
        'universities': universities,
        'colleges': colleges,
        'search': search,
        'university_filter': university_filter,
        'college_filter': college_filter,
    }
    
    return render(request, 'dashboard/programs/list.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def program_create(request):
    """Create a new program"""
    universities = University.objects.all().order_by('name')
    colleges = College.objects.select_related('university').all().order_by('university__name', 'name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        college_id = request.POST.get('college', '')
        duration = request.POST.get('duration', '')
        
        if not name or not college_id or not duration:
            messages.error(request, 'Program name, college, and duration are required.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Add Program',
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        try:
            duration = int(duration)
            if duration < 1 or duration > 10:
                raise ValueError("Duration must be between 1 and 10 years")
        except ValueError:
            messages.error(request, 'Duration must be a valid number between 1 and 10.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Add Program',
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        college = get_object_or_404(College, id=college_id)
        
        # Check for duplicate within college
        if Program.objects.filter(name__iexact=name, college=college).exists():
            messages.error(request, f'Program "{name}" already exists in {college.name}.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Add Program',
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        program = Program.objects.create(name=name, college=college, duration=duration)
        
        messages.success(request, f'Program "{name}" created successfully.')
        return redirect('dashboard-programs')
    
    context = {
        'active_page': 'programs',
        'form_title': 'Add Program',
        'universities': universities,
        'colleges': colleges,
    }
    return render(request, 'dashboard/programs/form.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def program_edit(request, program_id):
    """Edit an existing program"""
    program = get_object_or_404(Program, id=program_id)
    universities = University.objects.all().order_by('name')
    colleges = College.objects.select_related('university').all().order_by('university__name', 'name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        college_id = request.POST.get('college', '')
        duration = request.POST.get('duration', '')
        
        if not name or not college_id or not duration:
            messages.error(request, 'Program name, college, and duration are required.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Edit Program',
                'program': program,
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        try:
            duration = int(duration)
            if duration < 1 or duration > 10:
                raise ValueError("Duration must be between 1 and 10 years")
        except ValueError:
            messages.error(request, 'Duration must be a valid number between 1 and 10.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Edit Program',
                'program': program,
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        college = get_object_or_404(College, id=college_id)
        
        # Check for duplicate (excluding current)
        if Program.objects.filter(name__iexact=name, college=college).exclude(id=program_id).exists():
            messages.error(request, f'Program "{name}" already exists in {college.name}.')
            return render(request, 'dashboard/programs/form.html', {
                'active_page': 'programs',
                'form_title': 'Edit Program',
                'program': program,
                'universities': universities,
                'colleges': colleges,
                'name': name,
                'college_id': college_id,
                'duration': duration,
            })
        
        program.name = name
        program.college = college
        program.duration = duration
        program.save()
        
        messages.success(request, f'Program "{name}" updated successfully.')
        return redirect('dashboard-programs')
    
    context = {
        'active_page': 'programs',
        'form_title': 'Edit Program',
        'program': program,
        'universities': universities,
        'colleges': colleges,
        'name': program.name,
        'college_id': str(program.college_id),
        'duration': program.duration,
    }
    return render(request, 'dashboard/programs/form.html', context)


@admin_required
@require_http_methods(["POST"])
def program_delete(request, program_id):
    """Delete a program"""
    program = get_object_or_404(Program, id=program_id)
    name = program.name
    program.delete()
    messages.success(request, f'Program "{name}" deleted successfully.')
    return redirect('dashboard-programs')


# =============================================================================
# Course Views
# =============================================================================

@admin_required
def course_list(request):
    """List all courses with search and pagination"""
    search = request.GET.get('search', '').strip()
    program_filter = request.GET.get('program', '')
    year_filter = request.GET.get('year', '')
    semester_filter = request.GET.get('semester', '')
    type_filter = request.GET.get('type', '')
    
    courses = Course.objects.select_related('program__college__university').order_by(
        'program__college__university__name', 'program__name', 'year', 'semester', 'code'
    )
    
    if search:
        courses = courses.filter(
            Q(name__icontains=search) | 
            Q(code__icontains=search) |
            Q(program__name__icontains=search)
        )
    
    if program_filter:
        courses = courses.filter(program_id=program_filter)
    
    if year_filter:
        courses = courses.filter(year=year_filter)
    
    if semester_filter:
        courses = courses.filter(semester=semester_filter)
    
    if type_filter:
        courses = courses.filter(type=type_filter)
    
    paginator = Paginator(courses, 20)
    page = request.GET.get('page', 1)
    courses = paginator.get_page(page)
    
    programs = Program.objects.select_related('college__university').all().order_by(
        'college__university__name', 'name'
    )
    
    context = {
        'active_page': 'courses',
        'courses': courses,
        'programs': programs,
        'search': search,
        'program_filter': program_filter,
        'year_filter': year_filter,
        'semester_filter': semester_filter,
        'type_filter': type_filter,
    }
    
    return render(request, 'dashboard/courses/list.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def course_create(request):
    """Create a new course"""
    programs = Program.objects.select_related('college__university').all().order_by(
        'college__university__name', 'name'
    )
    
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        credits = request.POST.get('credits', '')
        course_type = request.POST.get('type', '')
        semester = request.POST.get('semester', '')
        year = request.POST.get('year', '')
        program_id = request.POST.get('program', '')
        
        if not all([code, name, credits, course_type, semester, year, program_id]):
            messages.error(request, 'All fields are required.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Add Course',
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        try:
            credits = int(credits)
            semester = int(semester)
            year = int(year)
        except ValueError:
            messages.error(request, 'Credits, semester, and year must be valid numbers.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Add Course',
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        program = get_object_or_404(Program, id=program_id)
        
        # Check for duplicate code within program
        if Course.objects.filter(code=code, program=program).exists():
            messages.error(request, f'Course with code "{code}" already exists in {program.name}.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Add Course',
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        course = Course.objects.create(
            code=code,
            name=name,
            credits=credits,
            type=course_type,
            semester=semester,
            year=year,
            program=program
        )
        
        messages.success(request, f'Course "{code} - {name}" created successfully.')
        return redirect('dashboard-courses')
    
    context = {
        'active_page': 'courses',
        'form_title': 'Add Course',
        'programs': programs,
    }
    return render(request, 'dashboard/courses/form.html', context)


@admin_required
@require_http_methods(["GET", "POST"])
def course_edit(request, course_id):
    """Edit an existing course"""
    course = get_object_or_404(Course, id=course_id)
    programs = Program.objects.select_related('college__university').all().order_by(
        'college__university__name', 'name'
    )
    
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        credits = request.POST.get('credits', '')
        course_type = request.POST.get('type', '')
        semester = request.POST.get('semester', '')
        year = request.POST.get('year', '')
        program_id = request.POST.get('program', '')
        
        if not all([code, name, credits, course_type, semester, year, program_id]):
            messages.error(request, 'All fields are required.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Edit Course',
                'course': course,
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        try:
            credits = int(credits)
            semester = int(semester)
            year = int(year)
        except ValueError:
            messages.error(request, 'Credits, semester, and year must be valid numbers.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Edit Course',
                'course': course,
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        program = get_object_or_404(Program, id=program_id)
        
        # Check for duplicate code (excluding current)
        if Course.objects.filter(code=code, program=program).exclude(id=course_id).exists():
            messages.error(request, f'Course with code "{code}" already exists in {program.name}.')
            return render(request, 'dashboard/courses/form.html', {
                'active_page': 'courses',
                'form_title': 'Edit Course',
                'course': course,
                'programs': programs,
                'code': code,
                'name': name,
                'credits': credits,
                'type': course_type,
                'semester': semester,
                'year': year,
                'program_id': program_id,
            })
        
        course.code = code
        course.name = name
        course.credits = credits
        course.type = course_type
        course.semester = semester
        course.year = year
        course.program = program
        course.save()
        
        messages.success(request, f'Course "{code} - {name}" updated successfully.')
        return redirect('dashboard-courses')
    
    context = {
        'active_page': 'courses',
        'form_title': 'Edit Course',
        'course': course,
        'programs': programs,
        'code': course.code,
        'name': course.name,
        'credits': course.credits,
        'type': course.type,
        'semester': course.semester,
        'year': course.year,
        'program_id': str(course.program_id),
    }
    return render(request, 'dashboard/courses/form.html', context)


@admin_required
@require_http_methods(["POST"])
def course_delete(request, course_id):
    """Delete a course"""
    course = get_object_or_404(Course, id=course_id)
    code = course.code
    course.delete()
    messages.success(request, f'Course "{code}" deleted successfully.')
    return redirect('dashboard-courses')


# =============================================================================
# Student Views
# =============================================================================

@admin_required
def student_list(request):
    """List all students with search and pagination"""
    search = request.GET.get('search', '').strip()
    university_filter = request.GET.get('university', '')
    program_filter = request.GET.get('program', '')
    year_filter = request.GET.get('year', '')
    
    students = Student.objects.select_related(
        'user', 'university', 'college', 'program'
    ).order_by('-created_at')
    
    if search:
        students = students.filter(
            Q(user__display_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(program__name__icontains=search) |
            Q(university__name__icontains=search)
        )
    
    if university_filter:
        students = students.filter(university_id=university_filter)
    
    if program_filter:
        students = students.filter(program_id=program_filter)
    
    if year_filter:
        students = students.filter(year=year_filter)
    
    paginator = Paginator(students, 20)
    page = request.GET.get('page', 1)
    students = paginator.get_page(page)
    
    universities = University.objects.all().order_by('name')
    programs = Program.objects.select_related('college__university').all().order_by('name')
    
    context = {
        'active_page': 'students',
        'students': students,
        'universities': universities,
        'programs': programs,
        'search': search,
        'university_filter': university_filter,
        'program_filter': program_filter,
        'year_filter': year_filter,
    }
    
    return render(request, 'dashboard/students/list.html', context)


@admin_required
def student_detail(request, student_id):
    """View student details"""
    student = get_object_or_404(
        Student.objects.select_related('user', 'university', 'college', 'program'),
        id=student_id
    )
    
    context = {
        'active_page': 'students',
        'student': student,
    }
    
    return render(request, 'dashboard/students/detail.html', context)


# =============================================================================
# Data Import Views
# =============================================================================

@admin_required
def import_data(request):
    """Import data from Excel/CSV files"""
    from data_import.models import ImportJob
    
    # Get recent import jobs
    import_jobs = ImportJob.objects.order_by('-created_at')[:10]
    
    context = {
        'active_page': 'import',
        'import_jobs': import_jobs,
    }
    
    return render(request, 'dashboard/import.html', context)


@admin_required
@require_http_methods(["POST"])
def import_universities(request):
    """Handle university/program Excel/CSV import"""
    if 'file' not in request.FILES:
        messages.error(request, 'Please select a file to upload.')
        return redirect('dashboard-import')
    
    file = request.FILES['file']
    
    if not file.name.endswith(('.csv', '.xlsx', '.xls')):
        messages.error(request, 'Please upload a CSV or Excel file.')
        return redirect('dashboard-import')
    
    try:
        # Save file temporarily
        filename = f"import_{uuid.uuid4()}_{file.name}"
        file_path = os.path.join(settings.MEDIA_ROOT, 'imports', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        # Read file
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()
        
        # Validate required columns
        required_columns = ['university', 'college', 'program', 'duration']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
            os.remove(file_path)
            return redirect('dashboard-import')
        
        # Process rows
        success_count = 0
        error_count = 0
        
        for _, row in df.iterrows():
            try:
                university_name = str(row['university']).strip()
                college_name = str(row['college']).strip()
                program_name = str(row['program']).strip()
                duration = int(row['duration'])
                country = str(row.get('country', 'Tanzania')).strip()
                
                if not all([university_name, college_name, program_name]):
                    error_count += 1
                    continue
                
                # Get or create university
                university, _ = University.objects.get_or_create(
                    name=university_name,
                    defaults={'country': country}
                )
                
                # Get or create college
                college, _ = College.objects.get_or_create(
                    name=college_name,
                    university=university
                )
                
                # Get or create program
                program, created = Program.objects.get_or_create(
                    name=program_name,
                    college=college,
                    defaults={'duration': duration}
                )
                
                if not created and program.duration != duration:
                    program.duration = duration
                    program.save()
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Error importing row: {e}")
                error_count += 1
        
        # Cleanup
        os.remove(file_path)
        
        if error_count == 0:
            messages.success(request, f'Successfully imported {success_count} programs.')
        else:
            messages.warning(request, f'Imported {success_count} programs with {error_count} errors.')
        
    except Exception as e:
        logger.error(f"Import error: {e}")
        messages.error(request, f'Error processing file: {str(e)}')
    
    return redirect('dashboard-import')


@admin_required
@require_http_methods(["POST"])
def import_courses(request):
    """Handle course Excel/CSV import"""
    if 'file' not in request.FILES:
        messages.error(request, 'Please select a file to upload.')
        return redirect('dashboard-import')
    
    file = request.FILES['file']
    
    if not file.name.endswith(('.csv', '.xlsx', '.xls')):
        messages.error(request, 'Please upload a CSV or Excel file.')
        return redirect('dashboard-import')
    
    try:
        # Save file temporarily
        filename = f"import_{uuid.uuid4()}_{file.name}"
        file_path = os.path.join(settings.MEDIA_ROOT, 'imports', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        # Read file
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()
        
        # Validate required columns
        required_columns = ['program', 'year', 'semester', 'name', 'code', 'credit', 'is_elective']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
            os.remove(file_path)
            return redirect('dashboard-import')
        
        # Process rows
        success_count = 0
        error_count = 0
        
        for _, row in df.iterrows():
            try:
                program_name = str(row['program']).strip()
                year = int(row['year'])
                semester = int(row['semester'])
                course_name = str(row['name']).strip()
                code = str(row['code']).strip()
                credits = int(row['credit'])
                is_elective = str(row['is_elective']).strip().lower() in ['true', '1', 'yes']
                
                if not all([program_name, course_name, code]):
                    error_count += 1
                    continue
                
                # Find program
                try:
                    program = Program.objects.get(name__iexact=program_name)
                except Program.DoesNotExist:
                    error_count += 1
                    continue
                
                # Get or create course
                course, created = Course.objects.update_or_create(
                    code=code,
                    program=program,
                    defaults={
                        'name': course_name,
                        'credits': credits,
                        'type': 'elective' if is_elective else 'core',
                        'semester': semester,
                        'year': year,
                    }
                )
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Error importing course row: {e}")
                error_count += 1
        
        # Cleanup
        os.remove(file_path)
        
        if error_count == 0:
            messages.success(request, f'Successfully imported {success_count} courses.')
        else:
            messages.warning(request, f'Imported {success_count} courses with {error_count} errors.')
        
    except Exception as e:
        logger.error(f"Import error: {e}")
        messages.error(request, f'Error processing file: {str(e)}')
    
    return redirect('dashboard-import')


# =============================================================================
# AJAX Endpoints for Dynamic Dropdowns
# =============================================================================

@admin_required
def ajax_get_colleges(request):
    """Get colleges for a university (AJAX)"""
    university_id = request.GET.get('university_id')
    
    if not university_id:
        return JsonResponse({'colleges': []})
    
    colleges = College.objects.filter(university_id=university_id).values('id', 'name')
    return JsonResponse({'colleges': list(colleges)})


@admin_required
def ajax_get_programs(request):
    """Get programs for a college (AJAX)"""
    college_id = request.GET.get('college_id')
    
    if not college_id:
        return JsonResponse({'programs': []})
    
    programs = Program.objects.filter(college_id=college_id).values('id', 'name', 'duration')
    return JsonResponse({'programs': list(programs)})

