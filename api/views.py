from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from django.db import models
import re
import time
from .gpa_privacy import encrypt_gpa_for_user
from .models import User, University, College, Program, Course, Student, StudentCourse, TimetableSlot, Article, ArticleComment, Notification, Slide, HelpMessage, Quote, UniversityAmbassador, AmbassadorActivity, AmbassadorMessage, UniversityLink, GPACalculation
from .serializers import ArticleSerializer
from .serializers import ArticleCommentSerializer, ArticleCommentCreateSerializer
from .utils import restrict_queryset_to_user_universities, assert_user_can_modify_related_university
from .permissions import user_is_admin, user_is_ambassador
from .serializers import (
    PasswordChangeSerializer, UserUpdateSerializer, UserSearchSerializer,
    UniversityAmbassadorSerializer, AmbassadorActivitySerializer,
    AmbassadorMessageSerializer, AmbassadorMessageCreateSerializer, UniversityLinkSerializer,
    GPACalculationSerializer
)

def notify_admin_users(title, body, notification_type='info', link=None):
    """Helper function to notify all admin/superuser accounts"""
    try:
        admin_users = User.objects.filter(
            models.Q(is_superuser=True) | models.Q(is_staff=True)
        ).distinct()
        
        notifications = []
        for admin in admin_users:
            notification = Notification.objects.create(
                user=admin,
                title=title,
                body=body,
                notification_type=notification_type,
                link=link
            )
            notifications.append(notification)
        
        return len(notifications)
    except Exception as e:
        # Log error but don't fail the main operation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to notify admin users: {str(e)}")
        return 0


def _all_student_courses(student_course):
    """
    Return a flat list of every normalized course dict across all periods.
    Works for the canonical {"_v":.., "periods":{...}} shape as well as any
    legacy shapes, never raises on malformed data.
    """
    if not student_course:
        return []
    periods = student_course.get_periods()
    out = []
    for key, items in periods.items():
        parts = str(key).split('_')
        year = parts[0] if parts else None
        sem = parts[1] if len(parts) > 1 else None
        for d in items:
            cd = dict(d)
            if cd.get('year') is None and year is not None:
                try:
                    cd['year'] = int(year)
                except (TypeError, ValueError):
                    pass
            if cd.get('semester') is None and sem is not None:
                try:
                    cd['semester'] = int(sem)
                except (TypeError, ValueError):
                    pass
            out.append(cd)
    return out


def _catalog_for_period(program, year, semester):
    """Return (list of catalog Course for program+period, bool had_any_catalog)."""
    qs = Course.objects.filter(program=program, semester=int(semester), year=int(year))
    return list(qs), qs.exists()


def _ensure_catalog_contribution(student, year, semester, courses, reward=True):
    """
    For a student's saved courses in a given (year, semester), auto-create any
    course in the shared catalog (Course) that is missing for their program +
    period, notify admins, and (when reward=True) credit COURSE_CONTRIBUTION
    tokens to the student (once per newly created course, idempotent).

    Returns a dict describing the outcome, or None if there is nothing to do.
    """
    if not student or not student.program_id:
        return None
    program = student.program
    existing, has_catalog = _catalog_for_period(program, year, semester)
    existing_by_code = {c.code.strip().upper().replace(' ', ''): c for c in existing}

    new_courses = []
    for d in (courses or []):
        if not isinstance(d, dict):
            continue
        code = (d.get('code') or d.get('course_code') or '').strip()
        if not code:
            continue
        norm = code.strip().upper().replace(' ', '')
        if norm in existing_by_code:
            continue
        name = d.get('name') or d.get('course_name') or code
        credits = d.get('credits')
        if credits is None:
            credits = d.get('credit_hour', 0)
        try:
            credits = int(credits or 0)
        except (TypeError, ValueError):
            credits = 0
        t = (d.get('type') or '').strip().lower()
        ctype = 'elective' if t in ('elective', 'optional') else 'core'
        try:
            course, created = Course.objects.get_or_create(
                code=code,
                program=program,
                defaults={
                    'name': name,
                    'credits': credits,
                    'type': ctype,
                    'semester': int(semester),
                    'year': int(year),
                },
            )
        except Exception:
            course, created = None, False
        if course is not None:
            existing_by_code[norm] = course
            if created:
                new_courses.append(course)

    if not new_courses:
        return None

    # Notify admins about newly contributed courses.
    try:
        program_name = getattr(program, 'name', 'Unknown Program')
        college_name = 'Unknown College'
        university_name = 'Unknown University'
        try:
            if program.college_id:
                college_name = program.college.name
                if program.college.university_id:
                    university_name = program.college.university.name
        except Exception:
            pass
        student_name = getattr(student.user, 'display_name', 'Unknown Student')
        lines = "\n".join(
            f"- {c.code}: {c.name} (Semester {semester}, Year {year})" for c in new_courses
        )
        notify_admin_users(
            title="New Courses Contributed to Catalog",
            body=(
                f"Student {student_name} contributed {len(new_courses)} new course(s) "
                f"to the shared catalog for {program_name} ({college_name}, {university_name}), "
                f"Semester {semester} Year {year}:\n\n{lines}"
            ),
            notification_type='info',
            link=None,
        )
    except Exception:
        pass

    # Reward the contributor, once per course, idempotently.
    rewarded = 0
    if reward:
        try:
            from tokens.services import token_service as ts
        except Exception:
            ts = None
        for course in new_courses:
            try:
                if ts is None:
                    from tokens.services import reward as _reward
                    _reward(
                        student.user,
                        'COURSE_CONTRIBUTION',
                        reference_key=f"course_contribution:{student.user_id}:{course.id}",
                        description=f"Contributed catalog course {course.code} ({course.name})",
                        content_object=course,
                        initiated_by='system',
                    )
                else:
                    ts.reward(
                        student.user,
                        'COURSE_CONTRIBUTION',
                        reference_key=f"course_contribution:{student.user_id}:{course.id}",
                        description=f"Contributed catalog course {course.code} ({course.name})",
                        content_object=course,
                        initiated_by='system',
                    )
                rewarded += 1
            except Exception:
                # Duplicate reward or wallet issue should not block the save.
                continue

    return {
        'contributed': len(new_courses),
        'rewarded': rewarded,
        'courses': [{'code': c.code, 'name': c.name, 'id': str(c.id)} for c in new_courses],
        'catalog_missing_for_period': (not has_catalog),
    }


def get_course_info_from_slot(slot):
    """Helper function to get course information from a timetable slot, prioritizing StudentCourse data"""
    course_name = slot.course_name
    course_code = slot.course_code
    
    # If we have a student_course reference, try to get the most up-to-date info
    if slot.student_course and slot.student_course.courses:
        # Look for the course in the student's courses (works for periods store)
        for course_data in _all_student_courses(slot.student_course):
            # Match by course_code or course_name
            if (course_data.get('code') == slot.course_code or 
                course_data.get('name') == slot.course_name or
                course_data.get('id') == str(slot.course.id) if slot.course else False):
                course_name = course_data.get('name', course_name)
                course_code = course_data.get('code', course_code)
                break
    
    # Fallback to Course model if available
    if slot.course:
        course_name = slot.course.name
        course_code = slot.course.code
    
    return {
        'course_name': course_name or 'Unknown Course',
        'course_code': course_code or 'Unknown Code'
    }

def rate_limit(max_calls=10, time_window=60):
    """Rate limiting decorator to prevent excessive API calls"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # Create a unique key for this user and endpoint
            user_id = getattr(request.user, 'id', 'anonymous')
            endpoint = request.path
            cache_key = f"rate_limit_{user_id}_{endpoint}"
            
            # Get current call count
            current_calls = cache.get(cache_key, 0)
            
            if current_calls >= max_calls:
                return Response({
                    'error': 'Rate limit exceeded. Please wait before making more requests.',
                    'retry_after': time_window,
                    'current_calls': current_calls,
                    'max_calls': max_calls,
                    'time_window': time_window,
                    'message': 'Please reduce the frequency of your API calls.'
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
            
            # Increment call count
            cache.set(cache_key, current_calls + 1, time_window)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserSerializer,
    UniversitySerializer, CollegeSerializer, ProgramSerializer, CourseSerializer,
    StudentSerializer, StudentCreateUpdateSerializer, StudentCourseSerializer,
    GPABreakdownSerializer, TargetGPASerializer, CourseAddSerializer, StudentCourseUpdateSerializer,
    QuoteSerializer
)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


# Authentication Views
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """
    User registration with seamless account linking.
    If user previously logged in with Google (has firebase_uid but no password),
    this will set their password and link the accounts.
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        # Check if this was linking a password to an existing Google account
        was_linking = user.firebase_uid and not user.has_usable_password()
        if was_linking:
            # User already had Google login, now setting password
            user.set_password(serializer.validated_data['password'])
            user.save()
        
        # Generate JWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        user_data = UserSerializer(user).data
        user_data['firebase_uid'] = user.firebase_uid if hasattr(user, 'firebase_uid') else None
        user_data['has_google_linked'] = bool(user.firebase_uid)
        user_data['account_linked'] = was_linking
        
        return Response({
            'user': user_data,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'token_type': 'Bearer',  # Match login format
            'message': (
                'Account created successfully! You can now login with email/password or Google.' if not was_linking else
                'Password set successfully! Your account is now linked. You can login with email/password or Google.'
            )
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        from .models import LoginActivity
        LoginActivity.objects.create(
            user=user,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            login_type=login_type,
            success=success
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to record login activity: {e}")


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login(request):
    """
    Email/Password login with seamless account linking.
    If user has previously logged in with Google (has firebase_uid), they can still login with email/password.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Generate JWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        # Record login activity for analytics
        record_login_activity(user, request, login_type='email', success=True)
        
        # Log token generation for debugging
        logger.info(f"✅ Login successful for user {user.id} ({user.email})")
        logger.info(f"🔑 Access token generated (length: {len(access_token)})")
        logger.info(f"🔑 Access token preview: {access_token[:50]}...")
        logger.info(f"🔑 Refresh token generated (length: {len(refresh_token)})")
        
        # Verify token can be decoded (sanity check)
        try:
            import jwt
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            logger.info(f"✅ Token decode test successful - user_id: {decoded.get('user_id')}")
        except Exception as e:
            logger.error(f"❌ Token decode test failed: {str(e)}")
        
        # Return user data with Firebase UID if available (for account linking status)
        user_data = UserSerializer(user).data
        user_data['firebase_uid'] = user.firebase_uid if hasattr(user, 'firebase_uid') else None
        user_data['has_google_linked'] = bool(user.firebase_uid)
        
        response_data = {
            'user': user_data,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',  # Explicitly specify token type
            'message': 'Successfully logged in'
        }
        
        logger.info(f"Returning login response with tokens for user {user.id}")
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    logger.warning(f"Login failed: {serializer.errors}")
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FirebaseLoginView(APIView):
    """Firebase Authentication View"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        id_token = request.data.get("token")

        if not id_token:
            return Response(
                {"error": "Authentication failed", "message": "Firebase ID token is required. Please sign in with Google first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Import Firebase modules
            import firebase_admin
            from firebase_admin import auth as firebase_auth

            # Check if Firebase is properly initialized
            try:
                firebase_admin.get_app()
            except ValueError:
                return Response(
                    {"error": "Authentication temporarily unavailable", "message": "Please try again later or contact support if the issue persists."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # Verify the Firebase ID token
            decoded_token = firebase_auth.verify_id_token(id_token)

            # Extract user information from the token
            uid = decoded_token['uid']
            email = decoded_token.get('email', '')
            name = decoded_token.get('name', '')
            picture = decoded_token.get('picture', '')

            # Try to find existing user in multiple ways
            user = None
            created = False

            # 1. First, try to find by Firebase UID (user has logged in with Firebase before)
            if uid:
                try:
                    user = User.objects.get(firebase_uid=uid)
                except User.DoesNotExist:
                    pass

            # 2. If not found by Firebase UID, try to find by email (link existing account)
            # This handles: User first logged in with email/password, now logging in with Google
            if not user and email:
                try:
                    user = User.objects.get(email=email)
                    # Link this user to Firebase (seamless account linking)
                    was_linking = not user.firebase_uid
                    user.firebase_uid = uid
                    user.save(update_fields=['firebase_uid'])
                    # Update profile picture and name from Google if available
                    if picture and not user.profile_picture:
                        user.profile_picture = picture
                    if name and (not user.display_name or user.display_name == user.email.split('@')[0]):
                        user.display_name = name
                    if picture or name:
                        user.save(update_fields=['profile_picture', 'display_name'])
                except User.DoesNotExist:
                    pass
                except User.MultipleObjectsReturned:
                    # Handle edge case of duplicate emails (shouldn't happen with unique constraint)
                    user = User.objects.filter(email=email).first()
                    if user:
                        user.firebase_uid = uid
                        user.save(update_fields=['firebase_uid'])

            # 3. If still not found, create a new user
            if not user:
                # Generate a unique username based on Firebase UID
                base_username = uid
                username = base_username
                counter = 1

                # Ensure username is unique
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                user = User.objects.create(
                    username=username,
                    email=email,
                    display_name=name or email.split('@')[0] if email else uid,
                    firebase_uid=uid,
                    profile_picture=picture
                )
                created = True

            # Update user information (whether found or created)
            updated = False
            if email and user.email != email:
                user.email = email
                # Also update username to match Firebase UID if email changed
                if user.firebase_uid == uid:
                    user.username = uid
                updated = True

            if name and user.display_name != name:
                user.display_name = name
                updated = True

            if picture and user.profile_picture != picture:
                user.profile_picture = picture
                updated = True

            if updated:
                user.save(update_fields=['email', 'username', 'display_name', 'profile_picture'])

            # Generate JWT tokens for the user
            refresh = RefreshToken.for_user(user)

            # Record login activity for analytics
            record_login_activity(user, request, login_type='firebase', success=True)

            # Determine if this was an account link or new user creation
            # Account is linked if: user existed before (not created) AND firebase_uid was just set
            was_linked = not created and user.firebase_uid == uid
            # Check if user had password set (indicates they used email/password before)
            has_password = user.has_usable_password() if hasattr(user, 'has_usable_password') else False

            return Response({
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "is_student": user.is_student,
                    "profile_picture": user.profile_picture,
                    "firebase_uid": user.firebase_uid,
                    "is_new_user": created,
                    "account_linked": was_linked,
                    "has_password": has_password,
                    "can_login_with_password": has_password
                },
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "token_type": "Bearer",  # Match email/password login format
                "message": (
                    "Welcome! Successfully authenticated with Google." if created else
                    "Welcome back! Your Google account has been linked to your existing account." if was_linked else
                    "Welcome back! Successfully authenticated with Google."
                )
            })

        except Exception as e:
            # Handle all Firebase-related exceptions with user-friendly messages
            error_message = str(e).lower()
            if "expired" in error_message:
                return Response(
                    {"error": "Session expired", "message": "Your Google sign-in session has expired. Please sign in again."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            elif "invalid" in error_message or "token" in error_message:
                return Response(
                    {"error": "Authentication failed", "message": "Invalid authentication token. Please try signing in with Google again."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            else:
                return Response(
                    {"error": "Authentication failed", "message": "Unable to authenticate with Google. Please try again or contact support."},
                    status=status.HTTP_400_BAD_REQUEST
                )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def verify_token(request):
    """
    Verify that the current access token is valid.
    Returns user information if token is valid.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Token verification request from user {request.user.id}")
    
    user_data = UserSerializer(request.user).data
    user_data['firebase_uid'] = request.user.firebase_uid if hasattr(request.user, 'firebase_uid') else None
    user_data['has_google_linked'] = bool(request.user.firebase_uid)
    
    return Response({
        'user': user_data,
        'authenticated': True,
        'message': 'Token is valid'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token(request):
    """
    Refresh access token ufsing refresh token.
    Expected payload: {"reresh": "<refresh_token>"}
    """
    import logging
    logger = logging.getLogger(__name__)
    
    refresh_token_str = request.data.get('refresh')
    
    if not refresh_token_str:
        return Response({
            'error': 'Refresh token is required',
            'message': 'Please provide a refresh token'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken(refresh_token_str)
        
        # Generate new access token
        new_access_token = str(refresh.access_token)
        
        logger.info(f"Token refreshed successfully")
        
        return Response({
            'access_token': new_access_token,
            'token_type': 'Bearer',
            'message': 'Token refreshed successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.warning(f"Token refresh failed: {str(e)}")
        return Response({
            'error': 'Invalid refresh token',
            'message': 'The refresh token is invalid or expired. Please login again.'
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """Change password for the authenticated user."""
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def user_update(request):
    """Update authenticated user's basic details: email, display_name, is_student, phone_number."""
    serializer = UserUpdateSerializer(instance=request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        user = request.user
        updated = False
        new_email = serializer.validated_data.get('email')
        new_name = serializer.validated_data.get('display_name')
        new_is_student = serializer.validated_data.get('is_student')
        new_phone = serializer.validated_data.get('phone_number')
        if new_email is not None and new_email != user.email:
            user.email = new_email
            # keep username in sync with email for compatibility
            user.username = new_email
            updated = True
        if new_name is not None and new_name != user.display_name:
            user.display_name = new_name
            updated = True
        if new_is_student is not None and new_is_student != user.is_student:
            user.is_student = new_is_student
            updated = True
        if new_phone is not None and new_phone != user.phone_number:
            user.phone_number = new_phone
            updated = True
        if updated:
            user.save(update_fields=['email', 'username', 'display_name', 'is_student', 'phone_number'])
        return Response({
            'message': 'Profile updated successfully',
            'data': {
                'id': str(user.id), 
                'email': user.email,
                'display_name': user.display_name,
                'is_student': user.is_student,
                'phone_number': user.phone_number
            }
        }, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_search(request):
    """Unified search across universities, colleges, programs, courses. Admin: global, Ambassador: scoped."""
    term = request.GET.get('q', '').strip()
    if not term:
        return Response({'error': 'Missing q parameter'}, status=status.HTTP_400_BAD_REQUEST)
    # base querysets
    uni_qs = University.objects.all()
    col_qs = College.objects.select_related('university').all()
    prog_qs = Program.objects.select_related('college__university').all()
    course_qs = Course.objects.select_related('program__college__university').all()
    # scope for ambassadors
    if not user_is_admin(request.user):
        allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
        uni_qs = uni_qs.filter(id__in=allowed_ids)
        col_qs = col_qs.filter(university_id__in=allowed_ids)
        prog_qs = prog_qs.filter(college__university_id__in=allowed_ids)
        course_qs = course_qs.filter(program__college__university_id__in=allowed_ids)
    # apply search
    uni_qs = uni_qs.filter(models.Q(name__icontains=term) | models.Q(country__icontains=term))[:20]
    col_qs = col_qs.filter(name__icontains=term)[:20]
    prog_qs = prog_qs.filter(name__icontains=term)[:20]
    course_qs = course_qs.filter(models.Q(name__icontains=term) | models.Q(code__icontains=term))[:20]
    # build response
    return Response({
        'universities': [{'id': str(u.id), 'name': u.name, 'country': u.country} for u in uni_qs],
        'colleges': [{'id': str(c.id), 'name': c.name, 'university': str(c.university_id), 'university_name': c.university.name} for c in col_qs],
        'programs': [{'id': str(p.id), 'name': p.name, 'college': str(p.college_id), 'college_name': p.college.name, 'university_name': p.college.university.name, 'duration': p.duration} for p in prog_qs],
        'courses': [{'id': str(cr.id), 'code': cr.code, 'name': cr.name, 'credits': cr.credits, 'type': cr.type, 'semester': cr.semester, 'year': cr.year, 'program': str(cr.program_id), 'program_name': cr.program.name} for cr in course_qs],
        'query': term
    }, status=status.HTTP_200_OK)


# Admin/staff wide list endpoints (admin: full, ambassador: scoped)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_universities(request):
    term = request.GET.get('search', '').strip()
    qs = University.objects.all()
    if not user_is_admin(request.user):
        # For ambassadors, restrict to their universities
        # For regular authenticated users, return all universities (needed for student profile selection)
        if user_is_ambassador(request.user):
            # Ambassador: only show their assigned universities
            allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
            if allowed_ids:
                qs = qs.filter(id__in=allowed_ids)
            else:
                # Ambassador with no universities assigned - return empty
                qs = qs.none()
        # else: regular authenticated user gets all universities (no filtering)
    if term:
        qs = qs.filter(models.Q(name__icontains=term) | models.Q(country__icontains=term))
    data = [{'id': str(u.id), 'name': u.name, 'country': u.country} for u in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_colleges(request):
    term = request.GET.get('search', '').strip()
    qs = College.objects.select_related('university').all()
    if not user_is_admin(request.user):
        allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
        qs = qs.filter(university_id__in=allowed_ids)
    if term:
        qs = qs.filter(name__icontains=term)
    data = [{'id': str(c.id), 'name': c.name, 'university': str(c.university_id), 'university_name': c.university.name} for c in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_programs(request):
    term = request.GET.get('search', '').strip()
    qs = Program.objects.select_related('college__university').all()
    if not user_is_admin(request.user):
        allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
        qs = qs.filter(college__university_id__in=allowed_ids)
    if term:
        qs = qs.filter(name__icontains=term)
    data = [{'id': str(p.id), 'name': p.name, 'college': str(p.college_id), 'college_name': p.college.name, 'university_name': p.college.university.name, 'duration': p.duration} for p in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_courses(request):
    term = request.GET.get('search', '').strip()
    qs = Course.objects.select_related('program__college__university').all()
    if not user_is_admin(request.user):
        allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
        qs = qs.filter(program__college__university_id__in=allowed_ids)
    if term:
        qs = qs.filter(models.Q(name__icontains=term) | models.Q(code__icontains=term))
    data = [{'id': str(cr.id), 'code': cr.code, 'name': cr.name, 'credits': cr.credits, 'type': cr.type, 'semester': cr.semester, 'year': cr.year, 'program': str(cr.program_id), 'program_name': cr.program.name} for cr in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_students(request):
    term = request.GET.get('search', '').strip()
    qs = Student.objects.select_related('user', 'university', 'college', 'program').all()
    if not user_is_admin(request.user):
        allowed_ids = list(restrict_queryset_to_user_universities(University.objects.all(), request.user).values_list('id', flat=True))
        qs = qs.filter(university_id__in=allowed_ids)
    if term:
        qs = qs.filter(models.Q(user__display_name__icontains=term) | models.Q(user__email__icontains=term))
    data = [{
        'id': str(s.id), 'user': str(s.user_id), 'user_name': s.user.display_name, 'user_email': s.user.email,
        'university': str(s.university_id), 'university_name': s.university.name,
        'college': str(s.college_id), 'college_name': s.college.name,
        'program': str(s.program_id), 'program_name': s.program.name,
        'year': s.year, 'semester': s.semester
    } for s in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_articles(request):
    term = request.GET.get('search', '').strip()
    qs = Article.objects.select_related('author').all()
    if term:
        qs = qs.filter(models.Q(title__icontains=term) | models.Q(content__icontains=term) | models.Q(author__display_name__icontains=term))
    data = [{'id': str(a.id), 'title': a.title, 'author': a.author.display_name, 'category': a.category, 'status': a.status, 'is_published': a.is_published, 'created_at': a.created_at.isoformat()} for a in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_quotes(request):
    term = request.GET.get('search', '').strip()
    qs = Quote.objects.all()
    if term:
        qs = qs.filter(models.Q(text__icontains=term) | models.Q(author__icontains=term))
    data = [{'id': str(q.id), 'text': q.text, 'author': q.author, 'is_active': q.is_active, 'created_at': q.created_at.isoformat()} for q in qs]
    return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def statistics_dashboard(request):
    """Get dashboard statistics including counts and recent users"""
    from django.db.models import Count

    # Get counts
    user_count = User.objects.count()
    article_count = Article.objects.count()
    university_count = University.objects.count()

    # Get recent users (last 5 who created accounts)
    recent_users = User.objects.order_by('-date_joined')[:5].values(
        'id', 'email', 'display_name', 'date_joined'
    )

    # Format recent users data
    recent_users_data = []
    for user in recent_users:
        recent_users_data.append({
            'id': str(user['id']),
            'email': user['email'],
            'display_name': user['display_name'],
            'date_joined': user['date_joined'].isoformat() if user['date_joined'] else None
        })

    # Additional statistics that might be useful
    published_articles = Article.objects.filter(status='published').count()
    active_universities = University.objects.count()  # All universities are active

    stats = {
        'counts': {
            'users': user_count,
            'articles': article_count,
            'universities': university_count,
            'published_articles': published_articles,
            'active_universities': active_universities
        },
        'recent_users': recent_users_data,
        'summary': {
            'total_users': user_count,
            'total_articles': article_count,
            'total_universities': university_count,
            'recent_registrations': len(recent_users_data)
        }
    }

    return Response(stats, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_notifications(request):
    """Admin list notifications with pagination and filtering"""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    include_read = request.GET.get('include_read', 'false').lower() == 'true'
    user_id = request.GET.get('user_id')  # Filter by specific user if provided

    # Build queryset
    notifications = Notification.objects.all()

    # Filter by user if specified
    if user_id:
        try:
            target_user = User.objects.get(id=user_id)
            notifications = notifications.filter(user=target_user)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    # Apply read status filter
    if not include_read:
        notifications = notifications.filter(is_read=False)

    # Order by creation date (newest first)
    notifications = notifications.order_by('-created_at')

    # Calculate pagination
    total_count = notifications.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Get paginated notifications
    paginated_notifications = notifications[start_index:end_index]

    # Format response
    notification_data = []
    for notification in paginated_notifications:
        # Build slide data if exists
        slide_data = None
        if notification.slide:
            slide_data = {
                'id': str(notification.slide.id),
                'title': notification.slide.title,
                'description': notification.slide.description,
                'image_url': notification.slide.image.url if notification.slide.image else notification.slide.image_url,
                'link_url': notification.slide.link_url
            }

        notification_data.append({
            'id': str(notification.id),
            'user': str(notification.user.id),
            'user_name': notification.user.display_name,
            'title': notification.title,
            'body': notification.body,
            'created_at': notification.created_at.isoformat(),
            'is_read': notification.is_read,
            'type': notification.notification_type,
            'link': notification.link,
            'slide': slide_data,
            'read_at': notification.read_at.isoformat() if notification.read_at else None
        })

    return Response({
        'notifications': notification_data,
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'has_next': end_index < total_count,
        'has_previous': page > 1
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_list_slides(request):
    """Admin list slides with pagination and filtering"""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    slide_type = request.GET.get('type')
    include_inactive = request.GET.get('include_inactive', 'false').lower() == 'true'

    # Build queryset
    slides = Slide.objects.all()

    # Apply filters
    if slide_type:
        slides = slides.filter(slide_type=slide_type)

    if not include_inactive:
        slides = slides.filter(is_active=True)

    # Order by creation date (newest first)
    slides = slides.order_by('-created_at')

    # Calculate pagination
    total_count = slides.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Get paginated slides
    paginated_slides = slides[start_index:end_index]

    # Format response
    slide_data = []
    for slide in paginated_slides:
        # Build image URLs
        image_url = None
        if slide.image:
            image_url = request.build_absolute_uri(slide.image.url)
        elif slide.image_url:
            image_url = slide.image_url

        slide_data.append({
            'id': str(slide.id),
            'title': slide.title,
            'description': slide.description,
            'image': slide.image.url if slide.image else None,
            'image_url': image_url,
            'link_url': slide.link_url,
            'button_text': slide.button_text,
            'background_gradient': slide.background_gradient,
            'slide_type': slide.slide_type,
            'is_active': slide.is_active,
            'order': slide.order,
            'created_at': slide.created_at.isoformat(),
            'updated_at': slide.updated_at.isoformat()
        })

    return Response({
        'slides': slide_data,
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'has_next': end_index < total_count,
        'has_previous': page > 1
    }, status=status.HTTP_200_OK)


# University & Academic Structure Views
class UniversityListView(generics.ListAPIView):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [permissions.AllowAny]
    def get_queryset(self):
        qs = super().get_queryset()
        term = self.request.query_params.get('search')
        if term:
            qs = qs.filter(name__icontains=term) | qs.filter(country__icontains=term)
        return qs


class CollegeListView(generics.ListAPIView):
    serializer_class = CollegeSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        university_id = self.kwargs['university_id']
        qs = College.objects.filter(university_id=university_id)
        term = self.request.query_params.get('search')
        if term:
            qs = qs.filter(name__icontains=term)
        return qs


class ProgramListView(generics.ListAPIView):
    serializer_class = ProgramSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        college_id = self.kwargs['college_id']
        qs = Program.objects.filter(college_id=college_id)
        term = self.request.query_params.get('search')
        if term:
            qs = qs.filter(name__icontains=term)
        return qs


class CourseListView(generics.ListAPIView):
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        program_id = self.kwargs['program_id']
        year = self.request.query_params.get('year')
        semester = self.request.query_params.get('semester')
        term = self.request.query_params.get('search')
        
        queryset = Course.objects.filter(program_id=program_id)
        
        if year:
            queryset = queryset.filter(year=int(year))
        if semester:
            queryset = queryset.filter(semester=int(semester))
        if term:
            queryset = queryset.filter(name__icontains=term) | queryset.filter(code__icontains=term)
        
        return queryset


# Student Management Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_data(request):
    """
    Get student data directly (without wrapper)
    Returns: university, college, program, year, semester, courses
    """
    try:
        student = Student.objects.get(user=request.user)
        serializer = StudentSerializer(student)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def student_profile_create(request):
    """
    Create student profile (POST-only)
    - Creates a new profile for the authenticated user if one does not exist
    - Returns 400 if profile already exists
    - Response payload matches StudentSerializer (includes courses array)
    """
    try:
        existing = Student.objects.get(user=request.user)
        return Response({
            'error': 'Student profile already exists',
            'has_profile': True,
            'profile': StudentSerializer(existing).data
        }, status=status.HTTP_400_BAD_REQUEST)
    except Student.DoesNotExist:
        pass

    serializer = StudentCreateUpdateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        student = serializer.save()
        # Profile-completion reward, granted only after registration + phone
        # verification + profile setup. Idempotent per user via the service.
        if getattr(request.user, 'phone_verified', False):
            try:
                from tokens import services as token_service
                token_service.reward(
                    request.user,
                    "PROFILE_COMPLETION",
                    reference_key=f"profile_completion:{request.user.pk}",
                    description="Profile completion reward",
                    initiated_by="api",
                )
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).warning(f"Profile completion reward skipped: {str(e)}")
        return Response({
            'message': 'Student profile created successfully',
            'has_profile': True,
            'profile': StudentSerializer(student).data
        }, status=status.HTTP_201_CREATED)

    return Response({
        'error': 'Validation failed',
        'details': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET', 'POST', 'PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def student_profile(request):
    """
    Student Profile Management
    
    GET: Retrieve student profile
    POST: Create new student profile (only if doesn't exist)
    PUT: Update entire student profile (replace all fields)
    PATCH: Partial update student profile (update only provided fields)
    """
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        student = None
    
    if request.method == 'GET':
        if not student:
            return Response({
                'error': 'Student profile not found',
                'message': 'Please create your student profile first',
                'has_profile': False
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StudentSerializer(student)
        return Response({
            'has_profile': True,
            'profile': serializer.data
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        if student:
            return Response({
                'error': 'Student profile already exists',
                'message': 'Use PUT or PATCH to update your existing profile',
                'has_profile': True,
                'profile': StudentSerializer(student).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = StudentCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            student = serializer.save()
            return Response({
                'message': 'Student profile created successfully',
                'has_profile': True,
                'profile': StudentSerializer(student).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'error': 'Validation failed',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'PUT':
        if not student:
            return Response({
                'error': 'Student profile not found',
                'message': 'Please create your student profile first using POST',
                'has_profile': False
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StudentCreateUpdateSerializer(student, data=request.data, context={'request': request})
        if serializer.is_valid():
            student = serializer.save()
            return Response({
                'message': 'Student profile updated successfully',
                'has_profile': True,
                'profile': StudentSerializer(student).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'error': 'Validation failed',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'PATCH':
        if not student:
            return Response({
                'error': 'Student profile not found',
                'message': 'Please create your student profile first using POST',
                'has_profile': False
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = StudentCreateUpdateSerializer(student, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            student = serializer.save()
            return Response({
                'message': 'Student profile updated successfully',
                'has_profile': True,
                'profile': StudentSerializer(student).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'error': 'Validation failed',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_profile_options(request):
    """Get available options for creating/updating student profile"""
    try:
        universities = University.objects.all()
        colleges = College.objects.all()
        programs = Program.objects.all()
        
        return Response({
            'universities': UniversitySerializer(universities, many=True).data,
            'colleges': CollegeSerializer(colleges, many=True).data,
            'programs': ProgramSerializer(programs, many=True).data,
            'year_choices': [1, 2, 3, 4, 5],  # Common academic years
            'semester_choices': [1, 2]  # Common semesters
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch profile options',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Course Management Views

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_student_courses_by_semester(request, semester, year):
    """Get courses for the authenticated student for a specific (year, semester)."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course = StudentCourse.objects.filter(student=student).first()
    courses = student_course.get_period(year, semester) if student_course else []

    # Report catalog availability so the frontend knows whether to offer
    # "configure from catalog" vs "contribute your own".
    catalog_courses, has_catalog = [], False
    if student.program_id:
        catalog_courses, has_catalog = _catalog_for_period(student.program, year, semester)

    return Response({
        'semester': semester,
        'year': year,
        'courses': courses,
        'total_courses': len(courses),
        'catalog': {
            'has_courses': has_catalog,
            'total': len(catalog_courses),
            'courses': [
                {'id': str(c.id), 'code': c.code, 'name': c.name,
                 'credits': c.credits, 'type': c.type} for c in catalog_courses
            ],
        },
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_student_courses_filtered(request):
    """Get courses for the authenticated student with optional semester/year/type filtering."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course = StudentCourse.objects.filter(student=student).first()
    courses = _all_student_courses(student_course)

    semester = request.query_params.get('semester')
    year = request.query_params.get('year')
    course_type = request.query_params.get('type', request.query_params.get('course_type'))

    filtered_courses = courses
    if semester is not None:
        try:
            semester = int(semester)
            filtered_courses = [c for c in filtered_courses if c.get('semester') == semester]
        except (TypeError, ValueError):
            pass
    if year is not None:
        try:
            year = int(year)
            filtered_courses = [c for c in filtered_courses if c.get('year') == year]
        except (TypeError, ValueError):
            pass
    if course_type:
        filtered_courses = [c for c in filtered_courses if c.get('type') == course_type]

    return Response({
        'filters': {'semester': semester, 'year': year, 'type': course_type},
        'courses': filtered_courses,
        'total_courses': len(filtered_courses),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def save_courses_batch(request):
    """
    Save a batch of courses for the authenticated student.

    Courses are grouped by (year, semester) and written into their own
    period within the canonical periods store, so saving one period never
    overwrites or loses any other period. Courses contributing new entries to
    the shared catalog are auto-created, admins are notified, and the student
    is rewarded tokens.
    """
    try:
        courses_data = request.data.get('courses', [])

        if not courses_data:
            return Response(
                {'error': 'No courses provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        student = Student.objects.get(user=request.user)
        student_course, _ = StudentCourse.objects.get_or_create(student=student)

        # Group by (year, semester); courses without those go to the student's
        # current year/semester so they are never dropped.
        grouped = {}
        for course_data in courses_data:
            if not isinstance(course_data, dict):
                continue
            semester = course_data.get('semester') or course_data.get('course_semester')
            year = course_data.get('year') or course_data.get('course_year')
            if semester is None or year is None:
                semester = student.semester or 1
                year = student.year or 1
            try:
                key = (int(year), int(semester))
            except (TypeError, ValueError):
                key = (int(student.year or 1), int(student.semester or 1))
            grouped.setdefault(key, []).append(course_data)

        total_saved = 0
        contribution = None
        for (year, semester), period_courses in grouped.items():
            cleaned = student_course.set_period(year, semester, period_courses, save=False)
            total_saved += len(cleaned)
            # Auto-create missing catalog entries for this period (contribution).
            result = _ensure_catalog_contribution(student, year, semester, cleaned, reward=True)
            if result and contribution is None:
                contribution = result

        student_course.save()

        response_data = {
            'message': f'Successfully saved {total_saved} courses',
            'total_courses': total_saved,
            'courses': _all_student_courses(student_course),
        }
        if contribution:
            response_data['contributed_courses'] = contribution['contributed']
            response_data['rewarded_tokens'] = contribution['rewarded']
            response_data['message'] += (
                f" ({contribution['rewarded']} new catalogs contributed, "
                f"{contribution['rewarded']} tokens rewarded)"
            )
        return Response(response_data, status=status.HTTP_201_CREATED)

    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def remove_course(request, course_id):
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        student_course = StudentCourse.objects.get(student=student)
        if student_course.remove_course(course_id):
            return Response({'message': 'Course removed successfully'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
    except StudentCourse.DoesNotExist:
        return Response({'error': 'No courses found'}, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET', 'POST', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
def student_courses(request):
    """
    Manage the authenticated student's courses (canonical periods store).

    GET  -> returns the full store: {"_v": 2, "periods": {"1_1": [ ... ], ...}}.
    POST -> adds a single course into its (year, semester) period.
    PUT  -> bulk save; accepts either {"periods": {"year_sem": [...]}} to replace
            selected periods (preserving all others), or a flat {"courses": [...]}
            grouped by each course's own year/semester so nothing is lost.
    """
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course, _ = StudentCourse.objects.get_or_create(student=student)

    if request.method == 'GET':
        store = student_course.ensure_periods()
        store['total_courses'] = student_course.period_count()
        return Response(store, status=status.HTTP_200_OK)

    if request.method == 'POST':
        try:
            semester = int(request.data.get('semester') or student.semester or 1)
            year = int(request.data.get('year') or student.year or 1)
        except (TypeError, ValueError):
            semester = int(student.semester or 1)
            year = int(student.year or 1)
        cd, added = student_course.add_course_to_period(year, semester, request.data)
        if not cd:
            return Response({'error': 'Invalid course data: code/name required'},
                            status=status.HTTP_400_BAD_REQUEST)
        _ensure_catalog_contribution(student, year, semester, [cd], reward=True)
        if not added:
            return Response({'error': 'Course already exists in this period'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': 'Course added successfully',
            'course': cd,
            'period': StudentCourse.period_key(year, semester),
        }, status=status.HTTP_201_CREATED)

    # PUT: bulk save preserving other periods.
    payload = request.data
    periods_payload = payload.get('periods') if isinstance(payload, dict) else None
    flat_courses = payload.get('courses') if isinstance(payload, dict) else None

    total_saved = 0
    contributed = 0
    rewarded = 0
    processed_periods = []

    if isinstance(periods_payload, dict):
        for key, items in periods_payload.items():
            parts = str(key).split('_')
            try:
                p_year = int(parts[0])
                p_sem = int(parts[1]) if len(parts) > 1 else 1
            except (TypeError, ValueError, IndexError):
                continue
            cleaned = student_course.set_period(p_year, p_sem, items or [], save=False)
            total_saved += len(cleaned)
            processed_periods.append((p_year, p_sem))
            res = _ensure_catalog_contribution(student, p_year, p_sem, cleaned, reward=True)
            if res:
                contributed += res['contributed']
                rewarded += res['rewarded']
    elif isinstance(flat_courses, list):
        grouped = {}
        for c in flat_courses:
            if not isinstance(c, dict):
                continue
            try:
                y = int(c.get('year') or student.year or 1)
                s = int(c.get('semester') or student.semester or 1)
            except (TypeError, ValueError):
                y = int(student.year or 1)
                s = int(student.semester or 1)
            grouped.setdefault((y, s), []).append(c)
        for (p_year, p_sem), items in grouped.items():
            cleaned = student_course.set_period(p_year, p_sem, items, save=False)
            total_saved += len(cleaned)
            processed_periods.append((p_year, p_sem))
            res = _ensure_catalog_contribution(student, p_year, p_sem, cleaned, reward=True)
            if res:
                contributed += res['contributed']
                rewarded += res['rewarded']
    else:
        return Response({'error': 'Invalid payload: expected {"periods": {...}} or {"courses": [...]}'},
                        status=status.HTTP_400_BAD_REQUEST)

    student_course.save()
    message = f'Successfully saved {total_saved} courses across {len(processed_periods)} period(s)'
    if contributed:
        message += f' ({contributed} catalog(s) contributed, {rewarded} tokens rewarded)'
    response = {
        'message': message,
        'total_saved': total_saved,
        'periods': student_course.get_periods(),
        'contributed_courses': contributed,
        'rewarded_tokens': rewarded,
    }
    return Response(response, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_student_course_period(request, year, semester):
    """Get a single (year, semester) period's saved courses plus catalog availability."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course = StudentCourse.objects.filter(student=student).first()
    saved = student_course.get_period(year, semester) if student_course else []

    catalog_courses, has_catalog = [], False
    if student.program_id:
        catalog_courses, has_catalog = _catalog_for_period(student.program, year, semester)

    next_year, next_sem = (int(year), int(semester))
    if int(semester) == 1:
        nxt = (int(year), 2)
    else:
        nxt = (int(year) + 1, 1)

    return Response({
        'year': int(year),
        'semester': int(semester),
        'period': StudentCourse.period_key(year, semester),
        'courses': saved,
        'total_courses': len(saved),
        'catalog_missing': (not has_catalog),
        'catalog': {
            'has_courses': has_catalog,
            'total': len(catalog_courses),
            'courses': [
                {'id': str(c.id), 'code': c.code, 'name': c.name,
                 'credits': c.credits, 'type': c.type} for c in catalog_courses
            ],
        },
        'next_period': f'{nxt[0]}_{nxt[1]}',
    }, status=status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def save_student_course_period(request, year, semester):
    """Replace the courses for one (year, semester) period only, preserving all others.

    Body: {"courses": [ {...course dicts...} ]}
    Missing catalog entries are auto-created, admins notified, and the student
    rewarded tokens (idempotently).
    """
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    courses = request.data.get('courses', [])
    if not isinstance(courses, list):
        return Response({'error': 'Expected {"courses": [...]}'}, status=status.HTTP_400_BAD_REQUEST)

    student_course, _ = StudentCourse.objects.get_or_create(student=student)
    cleaned = student_course.set_period(int(year), int(semester), courses)

    contribution = _ensure_catalog_contribution(student, int(year), int(semester), cleaned, reward=True)

    message = f'Successfully saved {len(cleaned)} courses for semester {semester} year {year}'
    response_data = {
        'message': message,
        'year': int(year),
        'semester': int(semester),
        'courses': cleaned,
        'total_courses': len(cleaned),
    }
    if contribution:
        response_data['contributed_courses'] = contribution['contributed']
        response_data['rewarded_tokens'] = contribution['rewarded']
        response_data['message'] += (
            f" ({contribution['rewarded']} catalog(s) contributed, "
            f"{contribution['rewarded']} tokens rewarded)"
        )
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def remove_student_course_from_period(request, year, semester, course_id):
    """Remove a single course from a specific (year, semester) period."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course, _ = StudentCourse.objects.get_or_create(student=student)
    if student_course.remove_course_from_period(int(year), int(semester), course_id):
        return Response({'message': 'Course removed successfully'}, status=status.HTTP_200_OK)
    return Response({'error': 'Course not found in this period'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def remove_student_course_period(request, year, semester):
    """Remove an entire (year, semester) period."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course, _ = StudentCourse.objects.get_or_create(student=student)
    if student_course.remove_period(int(year), int(semester)):
        return Response({'message': f'Removed all courses for semester {semester} year {year}'},
                        status=status.HTTP_200_OK)
    return Response({'error': 'Period not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def advance_student_period(request):
    """
    Advance the student to the next academic period (semester 1 -> 2 -> next year 1).

    Body (optional): {"year": int, "semester": int} = the CURRENT period to advance
    from. If omitted, the student's profile year/semester (or the latest saved
    period) is used.

    The new period is initialized with the program catalog's core + elective
    courses for that (year, semester) so the student can configure/save their
    own. The student profile's year/semester is also bumped.
    """
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    student_course, _ = StudentCourse.objects.get_or_create(student=student)

    req_year = request.data.get('year')
    req_sem = request.data.get('semester')
    if req_year is not None and req_sem is not None:
        try:
            cur_year = int(req_year)
            cur_sem = int(req_sem)
        except (TypeError, ValueError):
            return Response({'error': 'Invalid year/semester'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        # Prefer the maximum saved period; fall back to the profile period.
        periods = student_course.get_periods()
        cur_year = int(student.year or 1)
        cur_sem = int(student.semester or 1)
        if periods:
            last_key = max(periods, key=lambda k: tuple(int(x) for x in str(k).split('_') if x.isdigit()))
            parts = [int(x) for x in str(last_key).split('_') if x.isdigit()]
            if len(parts) >= 2:
                cur_year, cur_sem = parts[0], parts[1]

    if cur_sem == 1:
        new_year, new_sem = cur_year, 2
    else:
        new_year, new_sem = cur_year + 1, 1

    # Initialize the new period from the catalog (core + elective) if available.
    catalog_courses, has_catalog = _catalog_for_period(student.program, new_year, new_sem) if student.program_id else ([], False)
    if has_catalog and not student_course.get_period(new_year, new_sem):
        seeded = [
            {
                'id': str(c.id),
                'code': c.code,
                'name': c.name,
                'credits': c.credits,
                'type': c.type,
                'semester': new_sem,
                'year': new_year,
                'added_at': None,
            } for c in catalog_courses
        ]
        student_course.set_period(new_year, new_sem, seeded)

    # Bump the student's profile period so the next default advance is correct.
    student.year = new_year
    student.semester = new_sem
    # update_fields is filtered to model fields below.
    try:
        student.save(update_fields=['year', 'semester', 'updated_at'])
    except TypeError:
        student.save()

    return Response({
        'message': f'Advanced to Semester {new_sem} Year {new_year}',
        'year': new_year,
        'semester': new_sem,
        'period': StudentCourse.period_key(new_year, new_sem),
        'courses': student_course.get_period(new_year, new_sem),
        'catalog_missing': (not has_catalog),
        'periods': student_course.get_periods(),
    }, status=status.HTTP_200_OK)


# GPA Calculation Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def calculate_gpa(request):
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    gpa_data = student.get_gpa_breakdown()
    return Response(gpa_data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_target_gpa(request):
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = TargetGPASerializer(data=request.data)
    if serializer.is_valid():
        target_gpa = serializer.validated_data['target_gpa']
        
        # Get current GPA
        current_gpa = student.get_gpa()
        
        # Simple target GPA calculation - set all ungraded courses to required grade
        student_courses = StudentCourse.objects.filter(student=student)
        grades = []
        
        for student_course in student_courses:
            if not student_course.grade:
                # Calculate required grade for target GPA
                # This is a simplified calculation
                required_grade = 'A' if target_gpa >= 4.5 else 'B+' if target_gpa >= 4.0 else 'B'
                required_points = StudentCourse.GRADE_POINTS[required_grade]
                
                grades.append({
                    'course_id': str(student_course.course.id),
                    'course_code': student_course.course.code,
                    'course_name': student_course.course.name,
                    'credits': student_course.course.credits,
                    'required_grade': required_grade,
                    'required_points': required_points
                })
        
        # Calculate accuracy
        accuracy = "excellent" if abs(current_gpa - target_gpa) < 0.1 else "good" if abs(current_gpa - target_gpa) < 0.3 else "needs_improvement"
        
        return Response({
            'message': 'Target grades generated successfully',
            'target_gpa': target_gpa,
            'actual_gpa': current_gpa,
            'accuracy': accuracy,
            'grades': grades
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reset_grades(request):
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Reset all grades to A
    student_courses = StudentCourse.objects.filter(student=student)
    updated_count = 0
    
    for student_course in student_courses:
        student_course.grade = 'A'
        student_course.save()
        updated_count += 1
    
    return Response({
        'message': 'All grades reset to A',
        'courses_updated': updated_count
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def gpa_calculation_create(request):
    """Create an encrypted GPA calculation event record."""
    serializer = GPACalculationSerializer(data=request.data)
    if serializer.is_valid():
        if serializer.validated_data.get('gpa') is not None:
            encrypted = encrypt_gpa_for_user(request.user, str(serializer.validated_data['gpa']))
        else:
            encrypted = {
                'gpa_ciphertext': serializer.validated_data['gpa_ciphertext'],
                'gpa_iv': serializer.validated_data['gpa_iv'],
                'gpa_salt': serializer.validated_data['gpa_salt'],
                'gpa_alg': serializer.validated_data.get('gpa_alg', 'AES-GCM-PBKDF2'),
            }

        gpa_calculation = GPACalculation.objects.create(
            user=request.user,
            gpa_ciphertext=encrypted['gpa_ciphertext'],
            gpa_iv=encrypted['gpa_iv'],
            gpa_salt=encrypted['gpa_salt'],
            gpa_alg=encrypted.get('gpa_alg', 'AES-GCM-PBKDF2'),
            semester=serializer.validated_data['semester'],
            academic_year=serializer.validated_data['academic_year'],
            is_target=serializer.validated_data['is_target']
        )

        # Consumption routed through the central token service
        # (purchased tokens first, then earned). Best-effort so a low balance
        # does not block saving the encrypted GPA record.
        try:
            from tokens import services as token_service
            token_service.consume(
                request.user,
                "GPA_CALCULATION",
                reference_key=f"gpa:{gpa_calculation.id}",
                description="GPA calculation",
                content_object=gpa_calculation,
                initiated_by="api",
            )
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(f"GPA token consumption skipped: {str(e)}")
        
        return Response({
            'message': 'Encrypted GPA calculation event saved successfully',
            'id': str(gpa_calculation.id),
            'semester': gpa_calculation.semester,
            'academic_year': gpa_calculation.academic_year,
            'is_target': gpa_calculation.is_target,
            'gpa_alg': gpa_calculation.gpa_alg,
            'created_at': gpa_calculation.created_at
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# User Management Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@rate_limit(max_calls=20, time_window=60)  # Max 20 calls per 60 seconds
def user_basic_details(request):
    """Get basic user details with caching"""
    from django.core.cache import cache
    
    # Cache user details for 60 seconds to reduce database load
    cache_key = f"user_details_{request.user.id}"
    cached_data = cache.get(cache_key)
    
    if cached_data is not None:
        return Response(cached_data, status=status.HTTP_200_OK)
    
    try:
        user = request.user
        student = Student.objects.get(user=user)
        
        data = {
            'id': str(user.id),
            'email': user.email,
            'display_name': user.display_name,
            'username': user.username,
            'is_student': user.is_student,
            'student_profile': {
                'id': str(student.id),
                'university': student.university.name,
                'college': student.college.name,
                'program': student.program.name,
                'year': student.year,
                'semester': student.semester,
                'has_courses': student.has_courses
            }
        }
    except Student.DoesNotExist:
        data = {
            'id': str(user.id),
            'email': user.email,
            'display_name': user.display_name,
            'username': user.username,
            'is_student': user.is_student,
            'student_profile': None
        }
    
    # Cache for 60 seconds
    cache.set(cache_key, data, 60)
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def user_hobbies(request):
    """Get, save, or update user hobbies"""
    try:
        user = request.user
        
        if request.method == 'GET':
            # GET: Return user's hobbies
            hobbies = user.hobbies if user.hobbies else []
            return Response({
                'hobbies': hobbies
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            # POST: Save hobbies
            hobbies = request.data.get('hobbies', [])
            
            # Validate that hobbies is a list
            if not isinstance(hobbies, list):
                return Response({
                    'error': 'Invalid format. hobbies must be a list.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate that all items in hobbies are strings
            if not all(isinstance(hobby, str) for hobby in hobbies):
                return Response({
                    'error': 'Invalid format. All hobby IDs must be strings.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Save hobbies to user
            user.hobbies = hobbies
            user.save(update_fields=['hobbies'])
            
            return Response({
                'message': 'Hobbies saved successfully',
                'hobbies': hobbies
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'PATCH':
            # PATCH: Update hobbies
            hobbies = request.data.get('hobbies', [])
            
            # Validate that hobbies is a list
            if not isinstance(hobbies, list):
                return Response({
                    'error': 'Invalid format. hobbies must be a list.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate that all items in hobbies are strings
            if not all(isinstance(hobby, str) for hobby in hobbies):
                return Response({
                    'error': 'Invalid format. All hobby IDs must be strings.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update hobbies for user
            user.hobbies = hobbies
            user.save(update_fields=['hobbies'])
            
            return Response({
                'message': 'Hobbies updated successfully',
                'hobbies': hobbies
            }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Failed to process hobbies request',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Notification Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def notification_unread_count(request):
    """Get unread notification count with caching and graceful rate limiting"""
    from django.core.cache import cache
    
    # Check rate limit manually for better control
    user_id = getattr(request.user, 'id', 'anonymous')
    rate_limit_key = f"rate_limit_{user_id}_/api/notifications/unread-count/"
    current_calls = cache.get(rate_limit_key, 0)
    
    if current_calls >= 30:  # Max 30 calls per 60 seconds
        # Return cached data instead of error
        cache_key = f"unread_count_{request.user.id}"
        cached_count = cache.get(cache_key, 0)
        return Response({
            'unread': cached_count,
            'cached': True,
            'message': 'Using cached data due to rate limiting'
        }, status=status.HTTP_200_OK)
    
    # Increment rate limit counter
    cache.set(rate_limit_key, current_calls + 1, 60)
    
    # Get unread count with caching
    cache_key = f"unread_count_{request.user.id}"
    unread_count = cache.get(cache_key)
    
    if unread_count is None:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        cache.set(cache_key, unread_count, 30)  # Cache for 30 seconds
    
    return Response({
        'unread': unread_count,
        'cached': False
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def notification_list(request):
    """Get list of notifications"""
    user = request.user
    
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    include_read = request.GET.get('include_read', 'false').lower() == 'true'
    show_all = request.GET.get('show_all', 'false').lower() == 'true'
    all_notifications = request.GET.get('all', 'false').lower() == 'true'
    read_status = request.GET.get('read_status')
    
    # Build queryset
    notifications = Notification.objects.filter(user=user)
    
    # Apply filters
    if not include_read and not show_all and not all_notifications:
        notifications = notifications.filter(is_read=False)
    
    if read_status:
        if read_status.lower() == 'read':
            notifications = notifications.filter(is_read=True)
        elif read_status.lower() == 'unread':
            notifications = notifications.filter(is_read=False)
    
    # Order by creation date (newest first)
    notifications = notifications.order_by('-created_at')
    
    # Calculate pagination
    total_count = notifications.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    
    # Get paginated notifications
    paginated_notifications = notifications[start_index:end_index]
    
    # Format response
    notification_data = []
    for notification in paginated_notifications:
        # Build slide data if exists
        slide_data = None
        if notification.slide:
            slide_data = {
                'id': str(notification.slide.id),
                'title': notification.slide.title,
                'description': notification.slide.description,
                'image_url': request.build_absolute_uri(notification.slide.image.url) if notification.slide.image else notification.slide.image_url,
                'link_url': notification.slide.link_url
            }
        
        notification_data.append({
            'id': str(notification.id),
            'title': notification.title,
            'body': notification.body,
            'created_at': notification.created_at.isoformat(),
            'is_read': notification.is_read,
            'type': notification.notification_type,
            'link': notification.link,
            'slide': slide_data,
            'read_at': notification.read_at.isoformat() if notification.read_at else None
        })
    
    return Response({
        'notifications': notification_data,
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'has_next': end_index < total_count,
        'has_previous': page > 1
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def notification_mark_read(request, notification_id):
    """Mark a notification as read"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        # Invalidate the unread count cache
        cache_key = f"unread_count_{request.user.id}"
        cache.delete(cache_key)
    
    return Response({
        'id': str(notification.id),
        'is_read': notification.is_read,
        'read_at': notification.read_at.isoformat() if notification.read_at else None
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def notification_mark_all_read(request):
    """Mark all notifications as read"""
    updated_count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )
    
    # Invalidate the unread count cache
    cache_key = f"unread_count_{request.user.id}"
    cache.delete(cache_key)
    
    return Response({
        'updated_count': updated_count,
        'message': f'Marked {updated_count} notifications as read'
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def notification_delete(request, notification_id):
    """Delete a notification"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
    
    notification.delete()
    return Response({'message': 'Notification deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def notification_create(request):
    """Create a new notification (individual or bulk)"""
    # Only admins can create notifications for other users
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    user_id = request.data.get('user_id')
    target = request.data.get('target')  # For bulk notifications
    title = request.data.get('title')
    body = request.data.get('body', '')
    notification_type = request.data.get('type', 'info')
    link = request.data.get('link')
    slide_id = request.data.get('slide_id')

    # Validate required fields
    if not title:
        return Response({
            'error': 'title is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate notification type
    valid_types = ['info', 'warning', 'success', 'error']
    if notification_type not in valid_types:
        return Response({
            'error': f'type must be one of: {", ".join(valid_types)}'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Either user_id (individual) or target (bulk) must be provided
    if not user_id and not target:
        return Response({
            'error': 'Either user_id (individual) or target (bulk) is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    if user_id and target:
        return Response({
            'error': 'Cannot specify both user_id and target. Choose individual or bulk notification.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get slide if provided
        slide = None
        if slide_id:
            try:
                slide = Slide.objects.get(id=slide_id)
            except Slide.DoesNotExist:
                return Response({'error': 'Slide not found'}, status=status.HTTP_404_NOT_FOUND)

        if user_id:
            # Individual notification
            return create_individual_notification(user_id, title, body, notification_type, link, slide)
        else:
            # Bulk notification
            return create_bulk_notifications(target, title, body, notification_type, link, slide)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def notification_bulk(request):
    """Bulk notification creation endpoint (alternative to /create/ with target)"""
    # Only admins can create notifications for other users
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    target = request.data.get('target')
    title = request.data.get('title')
    body = request.data.get('body', '')
    notification_type = request.data.get('type', 'info')
    link = request.data.get('link')
    slide_id = request.data.get('slide_id')

    # Validate required fields
    if not target or not title:
        return Response({
            'error': 'target and title are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate notification type
    valid_types = ['info', 'warning', 'success', 'error']
    if notification_type not in valid_types:
        return Response({
            'error': f'type must be one of: {", ".join(valid_types)}'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate target
    valid_targets = ['all', 'students', 'staff']
    if target not in valid_targets:
        return Response({
            'error': f'target must be one of: {", ".join(valid_targets)}'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get slide if provided
        slide = None
        if slide_id:
            try:
                slide = Slide.objects.get(id=slide_id)
            except Slide.DoesNotExist:
                return Response({'error': 'Slide not found'}, status=status.HTTP_404_NOT_FOUND)

        # Bulk notification
        return create_bulk_notifications(target, title, body, notification_type, link, slide)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def create_individual_notification(user_id, title, body, notification_type, link, slide):
    """Create a single notification for a specific user"""
    try:
        # Get the target user
        target_user = User.objects.get(id=user_id)

        # Create the notification
        notification = Notification.objects.create(
            user=target_user,
            title=title,
            body=body,
            notification_type=notification_type,
            link=link,
            slide=slide
        )

        serializer = NotificationSerializer(notification)
        return Response({
            'message': 'Notification created successfully',
            'notification': serializer.data
        }, status=status.HTTP_201_CREATED)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


def create_bulk_notifications(target, title, body, notification_type, link, slide):
    """Create notifications for a group of users"""
    # Validate target
    valid_targets = ['all', 'students', 'staff']
    if target not in valid_targets:
        return Response({
            'error': f'target must be one of: {", ".join(valid_targets)}'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get target users based on group
        if target == 'all':
            target_users = User.objects.all()
        elif target == 'students':
            target_users = User.objects.filter(student_profile__isnull=False)
        elif target == 'staff':
            # Staff are users who are either superusers or have is_staff=True but no student profile
            target_users = User.objects.filter(
                models.Q(is_staff=True) | models.Q(is_superuser=True)
            ).exclude(student_profile__isnull=False)

        if not target_users.exists():
            return Response({
                'error': f'No users found for target group: {target}'
            }, status=status.HTTP_404_NOT_FOUND)

        # Create notifications for all target users
        notifications_created = 0
        for user in target_users:
            Notification.objects.create(
                user=user,
                title=title,
                body=body,
                notification_type=notification_type,
                link=link,
                slide=slide
            )
            notifications_created += 1

        return Response({
            'message': f'Bulk notifications sent successfully to {notifications_created} users',
            'target_group': target,
            'notifications_sent': notifications_created
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': f'Failed to send bulk notifications: {str(e)}'},
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_search(request):
    """
    Search users by name, email, or display name for notifications
    """
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))

    if len(query) < 2:
        return Response({'users': []})

    # Search in User model
    users = User.objects.filter(
        models.Q(display_name__icontains=query) |
        models.Q(email__icontains=query) |
        models.Q(username__icontains=query)
    ).exclude(id=request.user.id)[:limit]

    serializer = UserSearchSerializer(users, many=True)
    return Response({'users': serializer.data})


def notification_stream(request):
    """Server-Sent Events stream for notifications"""
    # Placeholder implementation - requires Notification model
    from django.http import StreamingHttpResponse
    import json
    import time
    
    def event_stream():
        while True:
            # Send a heartbeat every 30 seconds
            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
            time.sleep(30)
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    return response


# Timetable Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def timetable_my(request):
    """Get current user's timetable"""
    try:
        student = Student.objects.get(user=request.user)
        semester = request.GET.get('semester', student.semester)
        academic_year = request.GET.get('academic_year', '1')
        
        slots = TimetableSlot.objects.filter(
            student=student,
            semester=semester,
            academic_year=academic_year
        ).order_by('day_of_week', 'time_slot')
        
        timetable_data = []
        for slot in slots:
            timetable_data.append({
                'id': str(slot.id),
                'course_code': slot.course_code,
                'course_name': slot.course_name or slot.course,
                'day_of_week': slot.day_of_week,
                'time_slot': slot.time_slot,
                'venue': slot.venue,
                'instructor_name': slot.instructor,
                'semester': slot.semester,
                'academic_year': slot.academic_year
            })
        
        return Response({
            'timetable_slots': timetable_data,
            'semester': semester,
            'academic_year': academic_year
        }, status=status.HTTP_200_OK)
        
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def timetable_slots(request):
    """Get or create timetable slots"""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        """Get timetable slots with filtering"""
        # Get query parameters
        student_id = request.GET.get('student')
        semester = request.GET.get('semester', student.semester)
        academic_year = request.GET.get('academic_year', '2024')
        day = request.GET.get('day')
        
        # Filter by student if specified
        if student_id:
            try:
                target_student = Student.objects.get(id=student_id)
                slots = TimetableSlot.objects.filter(student=target_student)
            except Student.DoesNotExist:
                return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            slots = TimetableSlot.objects.filter(student=student)
        
        # Apply filters
        slots = slots.filter(semester=semester, academic_year=academic_year)
        
        if day:
            slots = slots.filter(day_of_week=day.lower())
        
        slots = slots.order_by('day_of_week', 'time_slot')
        
        # Format response to match frontend expectations
        timetable_data = []
        for slot in slots:
            # Get course info using the helper function
            course_info = get_course_info_from_slot(slot)
            
            timetable_data.append({
                'id': str(slot.id),
                'course': str(slot.course.id) if slot.course else None,
                'course_name': course_info['course_name'],
                'course_code': course_info['course_code'],
                'time_slot': slot.time_slot,
                'day_of_week': slot.day_of_week,
                'semester': slot.semester,
                'academic_year': slot.academic_year,
                'class_type': slot.class_type,
                'venue': slot.venue,
                'instructor': slot.instructor,
                'description': slot.description
            })
        
        return Response(timetable_data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        """Create new timetable slot"""
        data = request.data.copy()
        
        # Debug: Log the received data
        
        # Validate required fields (course is now optional)
        required_fields = ['day_of_week', 'time_slot']
        missing_fields = []
        for field in required_fields:
            if not data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            return Response({
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'received_data': data,
                'required_fields': required_fields
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate that at least course, course_code, or course_name is provided
        if not any([data.get('course'), data.get('course_code'), data.get('course_name')]):
            return Response({
                'error': 'At least one of course, course_code, or course_name must be provided',
                'received_data': data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate day_of_week format
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        day_of_week = data.get('day_of_week', '').lower()
        if day_of_week not in valid_days:
            return Response({
                'error': f'Invalid day_of_week: {day_of_week}. Must be one of: {", ".join(valid_days)}',
                'received_data': data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate time_slot format
        time_slot = data.get('time_slot', '')
        if not re.match(r'^\d{4}-\d{4}$', time_slot):
            return Response({
                'error': f'Invalid time_slot format: {time_slot}. Must be in format HHMM-HHMM (e.g., 0800-1000)',
                'received_data': data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle course - look in StudentCourse first, then fallback to Course model
        course = None
        student_course = None
        course_code = None
        course_name = None
        
        course_id = data.get('course')
        if course_id:
            # First, try to find in StudentCourse JSON field
            try:
                student_course_obj = StudentCourse.objects.get(student=student)
                # Look for the course in the student's courses JSON
                for course_data in _all_student_courses(student_course_obj):
                    if course_data.get('id') == course_id:
                        student_course = student_course_obj
                        course_code = course_data.get('code', course_id)
                        course_name = course_data.get('name', 'Custom Course')
                        break
                
                # If not found in StudentCourse, try Course model
                if not course_code:
                    try:
                        import uuid
                        uuid.UUID(course_id)
                        # It's a valid UUID, try to get from Course model
                        try:
                            course = Course.objects.get(id=course_id)
                            course_code = course.code
                            course_name = course.name
                        except Course.DoesNotExist:
                            # Course not found in either place, treat as custom course
                            course_code = data.get('course_code', course_id)
                            course_name = data.get('course_name', 'Custom Course')
                    except ValueError:
                        # Not a valid UUID, treat as custom course
                        course_code = course_id
                        course_name = data.get('course_name', 'Custom Course')
            except StudentCourse.DoesNotExist:
                # No StudentCourse exists, try Course model
                try:
                    import uuid
                    uuid.UUID(course_id)
                    try:
                        course = Course.objects.get(id=course_id)
                        course_code = course.code
                        course_name = course.name
                    except Course.DoesNotExist:
                        course_code = data.get('course_code', course_id)
                        course_name = data.get('course_name', 'Custom Course')
                except ValueError:
                    course_code = course_id
                    course_name = data.get('course_name', 'Custom Course')
        else:
            # No course ID provided, use course_code and course_name if available
            course_code = data.get('course_code')
            course_name = data.get('course_name')
        
        # Create the timetable slot
        try:
            slot = TimetableSlot.objects.create(
                student=student,
                course=course,  # Can be None for custom courses
                student_course=student_course,  # Reference to StudentCourse if found
                course_code=course_code,  # Store course code for custom courses
                course_name=course_name,  # Store course name for custom courses
                time_slot=time_slot,
                day_of_week=day_of_week,
                semester=data.get('semester', student.semester),
                academic_year=data.get('academic_year', '2024'),
                class_type=data.get('class_type', 'lecture'),
                venue=data.get('venue'),
                instructor=data.get('instructor'),
                description=data.get('description')
            )
            
            return Response({
                'id': str(slot.id),
                'course': str(slot.course.id) if slot.course else None,
                'course_name': slot.course_name,
                'course_code': slot.course_code,
                'time_slot': slot.time_slot,
                'day_of_week': slot.day_of_week,
                'semester': slot.semester,
                'academic_year': slot.academic_year,
                'class_type': slot.class_type,
                'venue': slot.venue,
                'instructor': slot.instructor,
                'description': slot.description
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'error': f'Failed to create timetable slot: {str(e)}',
                'received_data': data
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def timetable_slot_detail(request, slot_id):
    """Get, update, or delete a specific timetable slot"""
    try:
        slot = TimetableSlot.objects.get(id=slot_id, student__user=request.user)
    except TimetableSlot.DoesNotExist:
        return Response({'error': 'Timetable slot not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # Get course info using the helper function
        course_info = get_course_info_from_slot(slot)
        
        return Response({
            'id': str(slot.id),
            'course': str(slot.course.id) if slot.course else None,
            'course_name': course_info['course_name'],
            'course_code': course_info['course_code'],
            'time_slot': slot.time_slot,
            'day_of_week': slot.day_of_week,
            'semester': slot.semester,
            'academic_year': slot.academic_year,
            'class_type': slot.class_type,
            'venue': slot.venue,
            'instructor': slot.instructor,
            'description': slot.description
        })
    
    elif request.method == 'PATCH':
        data = request.data
        for field in ['time_slot', 'day_of_week', 'semester', 'academic_year', 'class_type', 'venue', 'instructor', 'description']:
            if field in data:
                setattr(slot, field, data[field])
        
        # Handle course update with flexible course handling
        if 'course' in data:
            course = None
            student_course = None
            course_code = None
            course_name = None
            
            course_id = data['course']
            if course_id:
                # First, try to find in StudentCourse JSON field
                try:
                    student_course_obj = StudentCourse.objects.get(student=slot.student)
                    # Look for the course in the student's courses JSON
                    for course_data in _all_student_courses(student_course_obj):
                        if course_data.get('id') == course_id:
                            student_course = student_course_obj
                            course_code = course_data.get('code', course_id)
                            course_name = course_data.get('name', 'Custom Course')
                            break
                    
                    # If not found in StudentCourse, try Course model
                    if not course_code:
                        try:
                            import uuid
                            uuid.UUID(course_id)
                            try:
                                course = Course.objects.get(id=course_id)
                                course_code = course.code
                                course_name = course.name
                            except Course.DoesNotExist:
                                course_code = data.get('course_code', course_id)
                                course_name = data.get('course_name', 'Custom Course')
                        except ValueError:
                            course_code = course_id
                            course_name = data.get('course_name', 'Custom Course')
                except StudentCourse.DoesNotExist:
                    try:
                        import uuid
                        uuid.UUID(course_id)
                        try:
                            course = Course.objects.get(id=course_id)
                            course_code = course.code
                            course_name = course.name
                        except Course.DoesNotExist:
                            course_code = data.get('course_code', course_id)
                            course_name = data.get('course_name', 'Custom Course')
                    except ValueError:
                        course_code = course_id
                        course_name = data.get('course_name', 'Custom Course')
            else:
                course_code = data.get('course_code')
                course_name = data.get('course_name')
            
            # Update the slot with new course information
            slot.course = course
            slot.student_course = student_course
            slot.course_code = course_code
            slot.course_name = course_name
        
        slot.save()
        
        # Get course info using the helper function
        course_info = get_course_info_from_slot(slot)
        
        return Response({
            'id': str(slot.id),
            'course': str(slot.course.id) if slot.course else None,
            'course_name': course_info['course_name'],
            'course_code': course_info['course_code'],
            'time_slot': slot.time_slot,
            'day_of_week': slot.day_of_week,
            'semester': slot.semester,
            'academic_year': slot.academic_year,
            'class_type': slot.class_type,
            'venue': slot.venue,
            'instructor': slot.instructor,
            'description': slot.description
        })
    
    elif request.method == 'DELETE':
        slot.delete()
        return Response({
            'success': True,
            'message': 'Timetable slot deleted successfully',
            'deleted_id': str(slot_id)
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def timetable_bulk_create(request):
    """Bulk create timetable slots"""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    slots_data = request.data.get('slots', [])
    if not slots_data:
        return Response({'error': 'No slots provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    created_slots = []
    errors = []
    
    for i, slot_data in enumerate(slots_data):
        try:
            # Validate required fields (course is now optional)
            required_fields = ['day_of_week', 'time_slot']
            missing_fields = [field for field in required_fields if not slot_data.get(field)]
            
            if missing_fields:
                errors.append(f'Slot {i+1}: Missing required fields: {", ".join(missing_fields)}')
                continue
            
            # Validate that at least course, course_code, or course_name is provided
            if not any([slot_data.get('course'), slot_data.get('course_code'), slot_data.get('course_name')]):
                errors.append(f'Slot {i+1}: At least one of course, course_code, or course_name must be provided')
                continue
            
            # Handle course - look in StudentCourse first, then fallback to Course model
            course = None
            student_course = None
            course_code = None
            course_name = None
            
            course_id = slot_data.get('course')
            if course_id:
                # First, try to find in StudentCourse JSON field
                try:
                    student_course_obj = StudentCourse.objects.get(student=student)
                    # Look for the course in the student's courses JSON
                    for course_data in _all_student_courses(student_course_obj):
                        if course_data.get('id') == course_id:
                            student_course = student_course_obj
                            course_code = course_data.get('code', course_id)
                            course_name = course_data.get('name', 'Custom Course')
                            break
                    
                    # If not found in StudentCourse, try Course model
                    if not course_code:
                        try:
                            import uuid
                            uuid.UUID(course_id)
                            try:
                                course = Course.objects.get(id=course_id)
                                course_code = course.code
                                course_name = course.name
                            except Course.DoesNotExist:
                                course_code = slot_data.get('course_code', course_id)
                                course_name = slot_data.get('course_name', 'Custom Course')
                        except ValueError:
                            course_code = course_id
                            course_name = slot_data.get('course_name', 'Custom Course')
                except StudentCourse.DoesNotExist:
                    try:
                        import uuid
                        uuid.UUID(course_id)
                        try:
                            course = Course.objects.get(id=course_id)
                            course_code = course.code
                            course_name = course.name
                        except Course.DoesNotExist:
                            course_code = slot_data.get('course_code', course_id)
                            course_name = slot_data.get('course_name', 'Custom Course')
                    except ValueError:
                        course_code = course_id
                        course_name = slot_data.get('course_name', 'Custom Course')
            else:
                course_code = slot_data.get('course_code')
                course_name = slot_data.get('course_name')
            
            # Create slot
            slot = TimetableSlot.objects.create(
                student=student,
                course=course,  # Can be None for custom courses
                student_course=student_course,  # Reference to StudentCourse if found
                course_code=course_code,  # Store course code for custom courses
                course_name=course_name,  # Store course name for custom courses
                time_slot=slot_data['time_slot'],
                day_of_week=slot_data['day_of_week'].lower(),
                semester=slot_data.get('semester', student.semester),
                academic_year=slot_data.get('academic_year', '2024'),
                class_type=slot_data.get('class_type', 'lecture'),
                venue=slot_data.get('venue'),
                instructor=slot_data.get('instructor'),
                description=slot_data.get('description')
            )
            
            created_slots.append({
                'id': str(slot.id),
                'course': str(slot.course.id) if slot.course else None,
                'course_name': slot.course_name,
                'course_code': slot.course_code,
                'time_slot': slot.time_slot,
                'day_of_week': slot.day_of_week,
                'semester': slot.semester,
                'academic_year': slot.academic_year,
                'class_type': slot.class_type,
                'venue': slot.venue,
                'instructor': slot.instructor,
                'description': slot.description
            })
            
        except Exception as e:
            errors.append(f'Slot {i+1}: {str(e)}')
    
    return Response({
        'created_slots': created_slots,
        'errors': errors,
        'total_created': len(created_slots),
        'total_errors': len(errors)
    }, status=status.HTTP_201_CREATED if created_slots else status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def timetable_bulk_delete(request):
    """Bulk delete timetable slots"""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    slot_ids = request.data.get('slot_ids', [])
    if not slot_ids:
        return Response({'error': 'No slot IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Delete slots that belong to the current user
    deleted_count, _ = TimetableSlot.objects.filter(
        id__in=slot_ids,
        student=student
    ).delete()
    
    return Response({
        'deleted_count': deleted_count,
        'message': f'Successfully deleted {deleted_count} timetable slots'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def timetable_debug_request(request):
    """Debug endpoint for timetable request format"""
    return Response({
        'message': 'Debug endpoint for timetable request format',
        'received_data': request.data,
        'method': request.method,
        'headers': dict(request.headers)
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def timetable_debug_validation(request):
    """Debug endpoint for timetable validation"""
    data = request.data
    
    # Basic validation
    errors = []
    if not data.get('course_code'):
        errors.append('course_code is required')
    if not data.get('day_of_week'):
        errors.append('day_of_week is required')
    if not data.get('time_slot'):
        errors.append('time_slot is required')
    
    # Validate day_of_week
    valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    if data.get('day_of_week') and data.get('day_of_week').lower() not in valid_days:
        errors.append(f'day_of_week must be one of: {", ".join(valid_days)}')
    
    # Validate time_slot format
    time_slot = data.get('time_slot', '')
    if time_slot and not re.match(r'^\d{4}-\d{4}$', time_slot):
        errors.append('time_slot must be in format HHMM-HHMM (e.g., 0800-1000)')
    
    if errors:
        return Response({
            'valid': False,
            'errors': errors,
            'data': data
        }, status=status.HTTP_400_BAD_REQUEST)
    
    return Response({
        'valid': True,
        'message': 'Data validation passed',
        'data': data
    }, status=status.HTTP_200_OK)


# Article Views
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def article_list(request):
    """
    List published articles with pagination and filtering.
    Returns content exactly as stored (JSON string) - no transformation on GET.
    """
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 12))
    sort_by = request.GET.get('sort_by', 'newest')
    category = request.GET.get('category')
    
    articles = Article.objects.filter(is_published=True)
    
    if category:
        articles = articles.filter(category=category)
    
    if sort_by == 'newest':
        articles = articles.order_by('-created_at')
    elif sort_by == 'oldest':
        articles = articles.order_by('created_at')
    elif sort_by == 'most_viewed':
        articles = articles.order_by('-views')
    elif sort_by == 'most_liked':
        articles = articles.order_by('-likes')
    
    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    articles_page = articles[start:end]
    
    # Use serializer for consistent data format
    serializer = ArticleSerializer(articles_page, many=True, context={'request': request})
    article_data = serializer.data
    
    # Add additional fields for list view
    for i, article in enumerate(articles_page):
        # Build cover image URL
        cover_image_url = None
        if article.cover_image:
            cover_image_url = request.build_absolute_uri(article.cover_image.url)
        article_data[i]['cover_image'] = cover_image_url
        
        # Build category data
        category_data = {
            'id': article.category,
            'name': article.get_category_display(),
            'slug': article.category,
            'description': f"{article.get_category_display()} content",
            'color': f"bg-{article.category}-500",
            'icon': "📚"
        }
        article_data[i]['category'] = category_data
        
        # Build author data
        author_data = {
            'id': str(article.author.id),
            'name': article.author.display_name if hasattr(article.author, 'display_name') else article.author.username,
            'avatar': None
        }
        article_data[i]['author'] = author_data
        
        # Add frontend-specific fields
        article_data[i]['is_liked'] = False
        article_data[i]['is_saved'] = False
        article_data[i]['is_shared'] = False
    
    return Response({
        'results': article_data,
        'count': articles.count(),
        'next': f'http://127.0.0.1:8000/api/articles/?page={page + 1}' if end < articles.count() else None,
        'previous': f'http://127.0.0.1:8000/api/articles/?page={page - 1}' if page > 1 else None,
        'filters': {
            'category': category,
            'sort_by': sort_by
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def article_detail(request, article_id):
    """
    Get a single article (public endpoint).
    Returns content exactly as stored (JSON string) - no transformation on GET.
    """
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Only show published articles to non-authenticated users
    if not request.user.is_authenticated and not article.is_published:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Use serializer to return data (content returned as-is, no transformation)
    serializer = ArticleSerializer(article, context={'request': request})
    data = serializer.data
    
    # Build cover image URL
    cover_image_url = None
    if article.cover_image:
        cover_image_url = request.build_absolute_uri(article.cover_image.url)
    data['cover_image'] = cover_image_url
    
    # Build category data
    category_data = {
        'id': article.category,
        'name': article.get_category_display(),
        'slug': article.category,
        'description': f"{article.get_category_display()} content",
        'color': f"bg-{article.category}-500",
        'icon': "📚"
    }
    data['category'] = category_data
    
    # Build author data
    author_data = {
        'id': str(article.author.id),
        'name': article.author.display_name if hasattr(article.author, 'display_name') else article.author.username,
        'avatar': None
    }
    data['author'] = author_data
    
    # Add frontend-specific fields
    data['is_liked'] = False  # TODO: Implement user-specific like status
    data['is_saved'] = False  # TODO: Implement user-specific save status
    data['is_shared'] = False  # TODO: Implement user-specific share status
    
    return Response(data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def article_view(request, article_id):
    """Track article view"""
    try:
        article = Article.objects.get(id=article_id, is_published=True)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    article.views += 1
    article.save(update_fields=['views'])
    
    return Response({
        'views': article.views
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def article_categories(request):
    """Get article categories"""
    categories = [
        {
            'id': 'academic',
            'name': 'Academic',
            'slug': 'academic',
            'description': 'Academic content',
            'color': 'bg-green-500',
            'icon': '📚'
        },
        {
            'id': 'campus_life',
            'name': 'Campus Life',
            'slug': 'campus_life',
            'description': 'Campus life content',
            'color': 'bg-blue-500',
            'icon': '🏫'
        },
        {
            'id': 'news',
            'name': 'News',
            'slug': 'news',
            'description': 'News content',
            'color': 'bg-red-500',
            'icon': '📰'
        },
        {
            'id': 'events',
            'name': 'Events',
            'slug': 'events',
            'description': 'Events content',
            'color': 'bg-purple-500',
            'icon': '🎉'
        },
        {
            'id': 'general',
            'name': 'General',
            'slug': 'general',
            'description': 'General content',
            'color': 'bg-gray-500',
            'icon': '📝'
        }
    ]
    
    return Response(categories, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def article_like(request, article_id):
    """Like/unlike article"""
    try:
        article = Article.objects.get(id=article_id, is_published=True)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # TODO: Implement user-specific like tracking
    # For now, just toggle the like count
    article.likes += 1
    article.save(update_fields=['likes'])
    
    return Response({
        'is_liked': True,  # TODO: Implement proper like status
        'likes': article.likes
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def article_save(request, article_id):
    """Save/unsave article"""
    try:
        article = Article.objects.get(id=article_id, is_published=True)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # TODO: Implement user-specific save tracking
    return Response({
        'is_saved': True  # TODO: Implement proper save status
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def article_share(request, article_id):
    """Share article"""
    try:
        article = Article.objects.get(id=article_id, is_published=True)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    platform = request.data.get('platform', 'unknown')
    
    # Increment share count
    article.share_count += 1
    article.save(update_fields=['share_count'])
    
    # Reward the sharer via the central token service (idempotent per user+article).
    try:
        from tokens import services as token_service
        token_service.reward(
            request.user,
            "ARTICLE_SHARE_REWARD",
            reference_key=f"article_share:{request.user.pk}:{article.id}",
            description=f"Reward for sharing article: {article.title}",
            content_object=article,
            initiated_by="api",
        )
    except Exception as e:  # noqa: BLE001 - never break sharing
        import logging
        logging.getLogger(__name__).warning(f"Share reward skipped: {str(e)}")
    
    return Response({
        'share_count': article.share_count,
        'platform': platform
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def article_saved(request):
    """Get saved articles"""
    # TODO: Implement user-specific saved articles
    return Response({
        'results': [],
        'count': 0,
        'next': None,
        'previous': None
    }, status=status.HTTP_200_OK)


def _comment_edit_delete_permission(comment, user):
    """Return True if the user may edit/delete a comment (owner, article author, or admin)."""
    is_owner = comment.user_id == user.id
    is_article_author = comment.article.author_id == user.id
    is_admin = user_is_admin(user) or getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)
    return is_owner or is_article_author or is_admin


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def article_comments(request, article_id):
    """List (GET) and create (POST) comments on an article.

    GET  /articles/<uuid>/comments/?page=&page_size=  -> paginated comment list
    POST /articles/<uuid>/comments/  {body, parent_id?} -> new comment
    """
    try:
        article = Article.objects.get(id=article_id, is_published=True)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(int(request.query_params.get('page_size', 50)), 100))
        except (TypeError, ValueError):
            page_size = 50

        queryset = article.comments.all().select_related('user')
        total = queryset.count()
        offset = (page - 1) * page_size
        items = queryset[offset:offset + page_size]
        serializer = ArticleCommentSerializer(items, many=True)
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'next_page': page + 1 if offset + len(items) < total else None,
            'previous_page': page - 1 if page > 1 else None,
            'results': serializer.data,
        }, status=status.HTTP_200_OK)

    # POST
    serializer = ArticleCommentCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'error': 'Validation failed',
            'details': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    parent = None
    parent_id = serializer.validated_data.get('parent_id')
    if parent_id is not None:
        try:
            parent = ArticleComment.objects.get(id=parent_id, article=article)
        except ArticleComment.DoesNotExist:
            return Response({'error': 'Parent comment not found for this article'}, status=status.HTTP_400_BAD_REQUEST)

    comment = ArticleComment.objects.create(
        article=article,
        user=request.user,
        parent=parent,
        body=serializer.validated_data['body'],
    )
    return Response(ArticleCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def article_comment_detail(request, article_id, comment_id):
    """Update (PATCH) or delete (DELETE) a single comment."""
    try:
        comment = ArticleComment.objects.select_related('user', 'article').get(id=comment_id, article_id=article_id)
    except ArticleComment.DoesNotExist:
        return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

    if not _comment_edit_delete_permission(comment, request.user):
        return Response({'error': 'You do not have permission to modify this comment'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PATCH':
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'error': 'Comment body cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)
        comment.body = body
        comment.save(update_fields=['body', 'updated_at'])
        return Response(ArticleCommentSerializer(comment).data, status=status.HTTP_200_OK)

    # DELETE
    deleted_id = str(comment.id)
    comment.delete()
    return Response({'ok': True, 'deleted_id': deleted_id}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def user_public_profile(request, user_id):
    """Public profile for a user, used for author navigation.

    GET /users/<uuid>/public-profile/
    """
    user = get_object_or_404(User, pk=user_id)
    if not user.public_profile:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

    page_size = 20

    university = None
    try:
        sp = user.student_profile
        if sp and sp.university_id:
            university = {
                'id': str(sp.university.id),
                'name': sp.university.name,
                'country': sp.university.country,
            }
    except Exception:  # noqa: BLE001 - no student profile is fine
        university = None

    articles_qs = Article.objects.filter(author=user, is_published=True).order_by('-created_at')
    total = articles_qs.count()
    articles = [
        {
            'id': str(a.id),
            'title': a.title,
            'excerpt': a.excerpt,
            'category': a.category,
            'likes': a.likes,
            'views': a.views,
            'created_at': a.created_at,
            'cover_image': a.cover_image.url if a.cover_image else None,
        }
        for a in articles_qs[:page_size]
    ]

    profile = {
        'id': str(user.id),
        'display_name': user.display_name,
        'email': user.email if user.show_email else None,
        'phone_number': user.phone_number if user.show_phone else None,
        'profile_picture': user.profile_picture,
        'bio': user.bio,
        'university': university,
        'articles': articles,
        'articles_count': total,
        'articles_page': 1,
        'articles_page_size': page_size,
        'opportunities': [],
        'opportunities_count': 0,
        'opportunities_page': 1,
        'opportunities_page_size': 20,
    }
    return Response(profile, status=status.HTTP_200_OK)


# Admin Article Management Endpoints
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_article_create(request):
    """
    Create a new article (admin endpoint).
    Endpoint: POST /admin/articles/
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Log incoming data for debugging
    logger.info(f"📝 Creating article - User: {request.user.id}")
    logger.debug(f"Request data keys: {list(request.data.keys())}")
    logger.debug(f"Request FILES keys: {list(request.FILES.keys())}")
    
    # Handle content if it comes as a JSON object instead of string
    data = request.data.copy()
    if 'content' in data:
        import json
        content = data['content']
        # If content is already a string, keep it
        # If it's a dict/list, convert to JSON string
        if isinstance(content, (dict, list)):
            try:
                data['content'] = json.dumps(content)
                logger.debug(f"Converted content from {type(content).__name__} to JSON string")
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to convert content to JSON string: {e}")
        elif not isinstance(content, str):
            logger.warning(f"Content is unexpected type: {type(content).__name__}")
    
    serializer = ArticleSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        article = serializer.save()
        logger.info(f"✅ Article created successfully - ID: {article.id}")
        
        # Build response with additional fields
        response_data = serializer.data
        
        # Build cover image URL
        cover_image_url = None
        if article.cover_image:
            cover_image_url = request.build_absolute_uri(article.cover_image.url)
        response_data['cover_image'] = cover_image_url
        
        # Build category data
        category_data = {
            'id': article.category,
            'name': article.get_category_display(),
            'slug': article.category,
            'description': f"{article.get_category_display()} content",
            'color': f"bg-{article.category}-500",
            'icon': "📚"
        }
        response_data['category'] = category_data
        
        # Build author data
        author_data = {
            'id': str(article.author.id),
            'name': article.author.display_name if hasattr(article.author, 'display_name') else article.author.username,
            'avatar': None
        }
        response_data['author'] = author_data
        
        return Response(response_data, status=status.HTTP_201_CREATED)
    
    # Log validation errors for debugging
    logger.warning(f"❌ Article creation failed - Validation errors:")
    for field, errors in serializer.errors.items():
        logger.warning(f"   {field}: {errors}")
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_article_detail(request, article_id):
    """
    Update or delete an article (admin endpoint).
    Endpoint: PUT/PATCH/DELETE /admin/articles/{id}/
    """
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check permissions (owner or superuser only)
    if article.author != request.user and not request.user.is_superuser:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    # DELETE request
    if request.method == 'DELETE':
        article.delete()
        return Response({'message': 'Article deleted successfully'}, status=status.HTTP_200_OK)
    
    # PUT/PATCH request - update article
    serializer = ArticleSerializer(
        article, 
        data=request.data, 
        partial=(request.method == 'PATCH'), 
        context={'request': request}
    )
    
    if serializer.is_valid():
        article = serializer.save()
        
        # Build response with additional fields
        response_data = serializer.data
        
        # Build cover image URL
        cover_image_url = None
        if article.cover_image:
            cover_image_url = request.build_absolute_uri(article.cover_image.url)
        response_data['cover_image'] = cover_image_url
        
        # Build category data
        category_data = {
            'id': article.category,
            'name': article.get_category_display(),
            'slug': article.category,
            'description': f"{article.get_category_display()} content",
            'color': f"bg-{article.category}-500",
            'icon': "📚"
        }
        response_data['category'] = category_data
        
        # Build author data
        author_data = {
            'id': str(article.author.id),
            'name': article.author.display_name if hasattr(article.author, 'display_name') else article.author.username,
            'avatar': None
        }
        response_data['author'] = author_data
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def article_image_upload(request):
    """
    Upload an image for use in article content blocks.
    
    Returns the filename that should be used in the image block's 'imageName' field.
    Frontend will insert this into the content block.
    
    Request: multipart/form-data with 'image' file and optional 'filename'
    Response: { "imageName": "1234567890-abc123.jpg" }
    
    Images are accessible at: /media/articles/{imageName}
    """
    if 'image' not in request.FILES:
        return Response(
            {'error': 'No image file provided'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    image_file = request.FILES['image']
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return Response(
            {'error': f'Invalid file type. Allowed types: {", ".join(allowed_types)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate file size (max 5MB)
    max_size = 5 * 1024 * 1024  # 5MB
    if image_file.size > max_size:
        return Response(
            {'error': f'File size exceeds maximum of {max_size / (1024*1024)}MB'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get filename from request or generate one
    import uuid
    import os
    from django.core.files.storage import default_storage
    
    provided_filename = request.POST.get('filename', '').strip()
    
    if provided_filename:
        # Use provided filename, but sanitize it
        filename = os.path.basename(provided_filename)  # Remove any path components
        # Ensure it has a valid extension
        file_ext = os.path.splitext(filename)[1].lower()
        if not file_ext:
            # Add extension from uploaded file
            original_ext = os.path.splitext(image_file.name)[1].lower()
            filename = f"{filename}{original_ext or '.jpg'}"
    else:
        # Generate unique filename
        file_ext = os.path.splitext(image_file.name)[1].lower()
        if not file_ext:
            file_ext = '.jpg'
        filename = f"{uuid.uuid4().hex[:12]}{file_ext}"
    
    # Ensure filename is safe (no path traversal)
    filename = os.path.basename(filename)
    
    # Save to articles directory
    file_path = f"articles/{filename}"
    
    # Save file
    try:
        saved_path = default_storage.save(file_path, image_file)
        
        # Extract just the filename (not the full path)
        # saved_path will be "articles/filename.jpg", we want just "filename.jpg"
        image_name = os.path.basename(saved_path)
        
        return Response({
            'imageName': image_name  # Just the filename: "1234567890-abc123.jpg"
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to save image: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Slide Views
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def slide_list(request):
    """Get list of active slides"""
    slide_type = request.GET.get('type')
    now = timezone.now()
    
    slides = Slide.objects.filter(is_active=True)
    
    # Filter by date range if provided
    slides = slides.filter(
        Q(start_date__isnull=True) | Q(start_date__lte=now),
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    )
    
    if slide_type:
        slides = slides.filter(slide_type=slide_type)
    
    slides = slides.order_by('order', '-created_at')
    
    slide_data = []
    for slide in slides:
        # Build image URLs
        image_url = None
        if slide.image:
            # Use the request's host to build the absolute URL
            image_url = request.build_absolute_uri(slide.image.url)
            # Always use localhost for frontend compatibility
            if '127.0.0.1' in image_url:
                image_url = image_url.replace('127.0.0.1', 'localhost')
        elif slide.image_url:
            image_url = slide.image_url
            # Also fix image_url if it contains 127.0.0.1
            if '127.0.0.1' in image_url:
                image_url = image_url.replace('127.0.0.1', 'localhost')
        
        slide_data.append({
            'id': str(slide.id),
            'title': slide.title,
            'description': slide.description,
            'image': slide.image.url if slide.image else None,
            'image_url': image_url,
            'image_url_display': image_url,
            'display_image': image_url,
            'background_gradient': slide.background_gradient,
            'link_url': slide.link_url,
            'order': slide.order,
            'is_active': slide.is_active,
            'created_at': slide.created_at.isoformat(),
            'updated_at': slide.updated_at.isoformat()
        })
    
    return Response(slide_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def slide_create(request):
    """Create a new slide"""
    data = request.data.copy()
    
    # Validate required fields
    required_fields = ['title']
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        return Response({
            'error': f'Missing required fields: {", ".join(missing_fields)}',
            'received_data': data
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        slide = Slide.objects.create(
            title=data['title'],
            description=data.get('description'),
            image_url=data.get('image_url'),
            link_url=data.get('link_url'),
            button_text=data.get('button_text'),
            background_gradient=data.get('background_gradient'),
            slide_type=data.get('slide_type', 'banner'),
            is_active=data.get('is_active', True),
            order=data.get('order', 0)
        )
        
        # Handle image upload
        if 'image' in request.FILES:
            slide.image = request.FILES['image']
            slide.save()
        
        return Response({
            'id': str(slide.id),
            'title': slide.title,
            'description': slide.description,
            'image': slide.image.url if slide.image else None,
            'image_url': slide.image_url,
            'link_url': slide.link_url,
            'button_text': slide.button_text,
            'background_gradient': slide.background_gradient,
            'slide_type': slide.slide_type,
            'is_active': slide.is_active,
            'order': slide.order,
            'created_at': slide.created_at.isoformat(),
            'updated_at': slide.updated_at.isoformat()
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': f'Failed to create slide: {str(e)}',
            'received_data': data
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def slide_detail(request, slide_id):
    """Update or delete a specific slide"""
    try:
        slide = Slide.objects.get(id=slide_id)
    except Slide.DoesNotExist:
        return Response({'error': 'Slide not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT':
        data = request.data
        
        # Update fields
        for field in ['title', 'description', 'image_url', 'link_url', 'button_text', 
                     'background_gradient', 'slide_type', 'is_active', 'order']:
            if field in data:
                setattr(slide, field, data[field])
        
        # Handle image upload
        if 'image' in request.FILES:
            slide.image = request.FILES['image']
        
        slide.save()
        
        return Response({
            'id': str(slide.id),
            'title': slide.title,
            'description': slide.description,
            'image': slide.image.url if slide.image else None,
            'image_url': slide.image_url,
            'link_url': slide.link_url,
            'button_text': slide.button_text,
            'background_gradient': slide.background_gradient,
            'slide_type': slide.slide_type,
            'is_active': slide.is_active,
            'order': slide.order,
            'created_at': slide.created_at.isoformat(),
            'updated_at': slide.updated_at.isoformat()
        })
    
    elif request.method == 'DELETE':
        slide.delete()
        return Response({'message': 'Slide deleted successfully'}, status=status.HTTP_200_OK)


# Help Center Views
@api_view(['POST'])
@permission_classes([permissions.AllowAny])  # Allow anonymous users to submit help messages
def submit_help_message(request):
    """Submit a help message from users"""
    from .serializers import HelpMessageSerializer, HelpMessageResponseSerializer
    
    serializer = HelpMessageSerializer(data=request.data)
    if serializer.is_valid():
        # If user is authenticated, link the message to the user
        if request.user.is_authenticated:
            help_message = serializer.save(user=request.user)
        else:
            help_message = serializer.save()
        
        # Return success response with ticket number
        response_data = HelpMessageResponseSerializer(help_message).data
        
        return Response({
            'success': True,
            'message': 'Your message has been sent successfully. We\'ll get back to you within 24 hours.',
            'ticket_number': help_message.ticket_number,
            'data': response_data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'success': False,
        'message': 'Invalid data provided.',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def help_message_list(request):
    """Get list of help messages for authenticated user"""
    from .serializers import HelpMessageResponseSerializer
    
    # Get messages for the current user
    messages = HelpMessage.objects.filter(user=request.user).order_by('-created_at')
    
    # Apply pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 10))
    
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    
    paginated_messages = messages[start_index:end_index]
    
    serializer = HelpMessageResponseSerializer(paginated_messages, many=True)
    
    return Response({
        'results': serializer.data,
        'count': messages.count(),
        'page': page,
        'page_size': page_size,
        'has_next': end_index < messages.count(),
        'has_previous': page > 1
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def help_message_detail(request, message_id):
    """Get details of a specific help message"""
    from .serializers import HelpMessageResponseSerializer
    
    try:
        message = HelpMessage.objects.get(id=message_id, user=request.user)
    except HelpMessage.DoesNotExist:
        return Response({'error': 'Help message not found'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = HelpMessageResponseSerializer(message)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def help_message_subjects(request):
    """Get list of available help message subjects"""
    subjects = [
        {'value': 'General Inquiry', 'label': 'General Inquiry'},
        {'value': 'Account & Login', 'label': 'Account & Login'},
        {'value': 'Timetable Help', 'label': 'Timetable Help'},
        {'value': 'GPA Calculator', 'label': 'GPA Calculator'},
        {'value': 'Bug Report', 'label': 'Bug Report'},
        {'value': 'Feature Request', 'label': 'Feature Request'},
    ]
    
    return Response({
        'subjects': subjects
    })


# Quote Views
@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # No authentication required
def quote_random(request):
    """Get one super random active quote with anti-repetition logic"""
    from .serializers import QuoteSerializer
    from django.core.cache import cache
    import random
    import time
    import hashlib
    
    # Get all active quotes
    quotes = Quote.objects.filter(is_active=True)
    
    if not quotes.exists():
        return Response({
            'error': 'No quotes available'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Convert to list for better random access
    quotes_list = list(quotes)
    total_quotes = len(quotes_list)
    
    # Create a cache key for recent quotes (last 10 quotes shown)
    recent_quotes_key = "recent_quotes_cache"
    recent_quotes = cache.get(recent_quotes_key, [])
    
    # Filter out recently shown quotes (last 10)
    available_quotes = [q for q in quotes_list if str(q.id) not in recent_quotes]
    
    # If we've shown all quotes recently, reset the recent quotes list
    if not available_quotes:
        available_quotes = quotes_list
        recent_quotes = []
    
    # Super randomization using multiple entropy sources
    # 1. Current timestamp (microseconds)
    time_seed = int(time.time() * 1000000) % 1000000
    
    # 2. Random number from Python's random
    random_seed = random.randint(0, 999999)
    
    # 3. Hash-based seed using request IP and timestamp
    ip_address = request.META.get('REMOTE_ADDR', 'unknown')
    hash_input = f"{ip_address}_{time.time()}_{random_seed}"
    hash_seed = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16) % 1000000
    
    # 4. Combine all seeds for maximum entropy
    combined_seed = (time_seed + random_seed + hash_seed) % 1000000
    
    # 5. Use the combined seed to select quote
    quote_index = combined_seed % len(available_quotes)
    selected_quote = available_quotes[quote_index]
    
    # Update recent quotes cache (keep last 10)
    recent_quotes.append(str(selected_quote.id))
    if len(recent_quotes) > 10:
        recent_quotes.pop(0)
    
    # Cache for 1 hour (3600 seconds)
    cache.set(recent_quotes_key, recent_quotes, 3600)
    
    serializer = QuoteSerializer(selected_quote)
    
    # Add randomization metadata for debugging (optional)
    response_data = serializer.data
    response_data['randomization_info'] = {
        'total_quotes': total_quotes,
        'available_quotes': len(available_quotes),
        'recent_quotes_count': len(recent_quotes),
        'selection_method': 'super_random_multi_entropy'
    }
    
    return Response(response_data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # No authentication required
def quote_list(request):
    """Get all active quotes"""
    from .serializers import QuoteSerializer
    
    quotes = Quote.objects.filter(is_active=True).order_by('-created_at')
    serializer = QuoteSerializer(quotes, many=True)
    
    return Response({
        'quotes': serializer.data
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])  # No authentication required (as requested)
def quote_create(request):
    """Create a new quote"""
    from .serializers import QuoteSerializer
    
    serializer = QuoteSerializer(data=request.data)
    if serializer.is_valid():
        quote = serializer.save()
        return Response(QuoteSerializer(quote).data, status=status.HTTP_201_CREATED)
    
    return Response({
        'error': 'Invalid data provided',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.AllowAny])  # No authentication required (as requested)
def quote_detail(request, quote_id):
    """Get, update, or delete a specific quote"""
    try:
        quote = Quote.objects.get(id=quote_id)
    except Quote.DoesNotExist:
        return Response({'error': 'Quote not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = QuoteSerializer(quote)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = QuoteSerializer(quote, data=request.data)
        if serializer.is_valid():
            quote = serializer.save()
            return Response(QuoteSerializer(quote).data, status=status.HTTP_200_OK)

        return Response({
            'error': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        quote.delete()
        return Response({'message': 'Quote deleted successfully'}, status=status.HTTP_200_OK)


# Academic Structure Management Views (for authenticated users)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_create_university(request):
    """Create a new university (authenticated users)"""
    from .serializers import UniversitySerializer
    
    serializer = UniversitySerializer(data=request.data)
    if serializer.is_valid():
        university = serializer.save()
        return Response({
            'message': 'University created successfully',
            'data': UniversitySerializer(university).data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'error': 'Invalid data provided',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_delete_university(request, university_id):
    """Delete a university (authenticated users)"""
    try:
        university = University.objects.get(id=university_id)
    except University.DoesNotExist:
        return Response({'error': 'University not found'}, status=status.HTTP_404_NOT_FOUND)

    university.delete()
    return Response({'message': 'University deleted successfully'}, status=status.HTTP_200_OK)


# Staff & RBAC endpoints
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def staff_me_roles(request):
    """Return my roles and ambassador universities for frontend gating."""
    amb_unis = list(UniversityAmbassador.objects.filter(user=request.user).values_list('university_id', flat=True))
    return Response({
        'is_admin': user_is_admin(request.user),
        'is_ambassador': user_is_ambassador(request.user),
        'ambassador_university_ids': amb_unis,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def staff_ambassador_assign(request):
    """Assign ambassador to a university (admin only)."""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    user_id = request.data.get('user_id')
    university_id = request.data.get('university_id')
    if not user_id or not university_id:
        return Response({'error': 'user_id and university_id are required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        target_user = User.objects.get(id=user_id)
        target_uni = University.objects.get(id=university_id)
        link, created = UniversityAmbassador.objects.get_or_create(user=target_user, university=target_uni)
        return Response({'message': 'Assigned', 'created': created}, status=status.HTTP_200_OK)
    except (User.DoesNotExist, University.DoesNotExist):
        return Response({'error': 'User or University not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def staff_ambassador_revoke(request):
    """Revoke ambassador from a university (admin only)."""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    user_id = request.data.get('user_id')
    university_id = request.data.get('university_id')
    if not user_id or not university_id:
        return Response({'error': 'user_id and university_id are required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        UniversityAmbassador.objects.get(user_id=user_id, university_id=university_id).delete()
        return Response({'message': 'Revoked'}, status=status.HTTP_200_OK)
    except UniversityAmbassador.DoesNotExist:
        return Response({'error': 'Assignment not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_ambassadors(request):
    """List all ambassadors (admin only)"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    ambassadors = UniversityAmbassador.objects.select_related('user', 'university').all()
    serializer = UniversityAmbassadorSerializer(ambassadors, many=True)
    return Response({'results': serializer.data, 'count': len(serializer.data)})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def ambassador_activities(request, ambassador_id):
    """Get activities for a specific ambassador (admin only)"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    try:
        ambassador = UniversityAmbassador.objects.get(id=ambassador_id)
    except UniversityAmbassador.DoesNotExist:
        return Response({'error': 'Ambassador not found'}, status=status.HTTP_404_NOT_FOUND)

    activities = AmbassadorActivity.objects.filter(ambassador=ambassador)
    serializer = AmbassadorActivitySerializer(activities, many=True)
    return Response({'results': serializer.data, 'count': len(serializer.data)})


@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def update_ambassador(request, ambassador_id):
    """Update ambassador (admin only)"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    try:
        ambassador = UniversityAmbassador.objects.get(id=ambassador_id)
    except UniversityAmbassador.DoesNotExist:
        return Response({'error': 'Ambassador not found'}, status=status.HTTP_404_NOT_FOUND)

    # For now, only allow updating the university assignment
    university_id = request.data.get('university_id')
    if university_id:
        try:
            university = University.objects.get(id=university_id)
            ambassador.university = university
            ambassador.save()

            # Log activity
            AmbassadorActivity.objects.create(
                ambassador=ambassador,
                activity_type='university_joined',
                description=f'Ambassador moved to {university.name}'
            )

        except University.DoesNotExist:
            return Response({'error': 'University not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = UniversityAmbassadorSerializer(ambassador)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_ambassador(request, ambassador_id):
    """Delete ambassador (admin only)"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    try:
        ambassador = UniversityAmbassador.objects.get(id=ambassador_id)
        ambassador.delete()
        return Response({'message': 'Ambassador deleted successfully'})
    except UniversityAmbassador.DoesNotExist:
        return Response({'error': 'Ambassador not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def send_ambassador_message(request):
    """Send message to ambassador (staff only)"""
    if not user_is_admin(request.user) and not user_is_ambassador(request.user):
        return Response({'error': 'Staff access required'}, status=status.HTTP_403_FORBIDDEN)

    serializer = AmbassadorMessageCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        message = serializer.save(sender=request.user)

        # Log activity for both sender and recipient
        AmbassadorActivity.objects.create(
            ambassador=message.recipient,
            activity_type='message_received',
            description=f'Received message: {message.subject}'
        )

        # Also log for sender if they're an ambassador
        try:
            sender_ambassador = UniversityAmbassador.objects.get(user=request.user)
            AmbassadorActivity.objects.create(
                ambassador=sender_ambassador,
                activity_type='message_sent',
                description=f'Sent message: {message.subject}'
            )
        except UniversityAmbassador.DoesNotExist:
            pass  # Sender is staff, not necessarily an ambassador

        response_serializer = AmbassadorMessageSerializer(message)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_ambassador_messages(request):
    """Get messages sent/received by current user"""
    user = request.user

    # Get messages where user is sender or recipient is one of their ambassador roles
    sent_messages = AmbassadorMessage.objects.filter(sender=user)
    received_messages = AmbassadorMessage.objects.filter(
        recipient__user=user
    )

    # Combine and order by creation date
    all_messages = (sent_messages | received_messages).distinct().order_by('-created_at')

    serializer = AmbassadorMessageSerializer(all_messages, many=True)
    return Response({'results': serializer.data, 'count': len(serializer.data)})


@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def mark_ambassador_message(request, message_id):
    """Mark message as read or completed"""
    try:
        message = AmbassadorMessage.objects.get(id=message_id)

        # Only allow marking messages where user is sender or recipient
        if message.sender != request.user and message.recipient.user != request.user:
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

    except AmbassadorMessage.DoesNotExist:
        return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)

    status_update = request.data.get('status')
    if status_update == 'read' and message.status != 'read':
        message.status = 'read'
        message.read_at = timezone.now()
        message.save()

        # Log activity
        AmbassadorActivity.objects.create(
            ambassador=message.recipient,
            activity_type='message_received',
            description=f'Message marked as read: {message.subject}'
        )

    elif status_update == 'completed' and message.status not in ['completed']:
        message.status = 'completed'
        message.completed_at = timezone.now()
        message.save()

        # Log activity
        AmbassadorActivity.objects.create(
            ambassador=message.recipient,
            activity_type='message_received',
            description=f'Message completed: {message.subject}'
        )

    serializer = AmbassadorMessageSerializer(message)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_create_college(request):
    """Create a new college (authenticated users)"""
    from .serializers import CollegeSerializer
    
    serializer = CollegeSerializer(data=request.data)
    if serializer.is_valid():
        college = serializer.save()
        return Response({
            'message': 'College created successfully',
            'data': CollegeSerializer(college).data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'error': 'Invalid data provided',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_delete_college(request, college_id):
    """Delete a college (authenticated users)"""
    try:
        college = College.objects.get(id=college_id)
    except College.DoesNotExist:
        return Response({'error': 'College not found'}, status=status.HTTP_404_NOT_FOUND)

    college.delete()
    return Response({'message': 'College deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_create_program(request):
    """Create a new program (authenticated users)"""
    from .serializers import ProgramSerializer
    
    serializer = ProgramSerializer(data=request.data)
    if serializer.is_valid():
        program = serializer.save()
        return Response({
            'message': 'Program created successfully',
            'data': ProgramSerializer(program).data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'error': 'Invalid data provided',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_delete_program(request, program_id):
    """Delete a program (authenticated users)"""
    try:
        program = Program.objects.get(id=program_id)
    except Program.DoesNotExist:
        return Response({'error': 'Program not found'}, status=status.HTTP_404_NOT_FOUND)

    program.delete()
    return Response({'message': 'Program deleted successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_create_course(request):
    """Create a new course (authenticated users)"""
    from .serializers import CourseSerializer

    serializer = CourseSerializer(data=request.data)
    if serializer.is_valid():
        course = serializer.save()
        return Response({
            'message': 'Course created successfully',
            'data': CourseSerializer(course).data
        }, status=status.HTTP_201_CREATED)

    return Response({
        'error': 'Invalid data provided',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_university_links(request):
    """Get university links for the current user's university"""
    try:
        # Get user's university from Student profile
        student_profile = request.user.student_profile
        user_university = student_profile.university

        # Filter links by user's university or show HESLB links if no university
        if user_university:
            # Show links for user's university + universal links (university is null)
            links = UniversityLink.objects.filter(
                Q(university=user_university) |
                Q(university__isnull=True)
            ).filter(is_active=True).order_by('name')
        else:
            # If user has no university, show only HESLB links as default
            try:
                heslb_university = University.objects.get(name__icontains='heslb')
                links = UniversityLink.objects.filter(
                    Q(university=heslb_university) |
                    Q(university__isnull=True)
                ).filter(is_active=True).order_by('name')
            except University.DoesNotExist:
                # Fallback: show only universal links if HESLB doesn't exist
                links = UniversityLink.objects.filter(
                    university__isnull=True,
                    is_active=True
                ).order_by('name')

    except:
        # If user doesn't have a student profile, show only HESLB links as default
        try:
            heslb_university = University.objects.get(name__icontains='heslb')
            links = UniversityLink.objects.filter(
                Q(university=heslb_university) |
                Q(university__isnull=True)
            ).filter(is_active=True).order_by('name')
        except University.DoesNotExist:
            # Fallback: show only universal links if HESLB doesn't exist
            links = UniversityLink.objects.filter(
                university__isnull=True,
                is_active=True
            ).order_by('name')

    serializer = UniversityLinkSerializer(links, many=True)
    return Response({
        'success': True,
        'data': {
            'links': serializer.data
        },
        'message': 'University links retrieved successfully'
    })