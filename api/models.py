from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
import uuid


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    is_student = models.BooleanField(default=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    firebase_uid = models.CharField(max_length=128, blank=True, null=True, unique=True)
    profile_picture = models.URLField(max_length=500, blank=True, null=True)
    hobbies = models.JSONField(default=list, blank=True, help_text="List of hobby IDs")
    
    # NEW FIELDS for enhanced profile
    bio = models.TextField(max_length=500, blank=True, help_text="Short bio/about me")
    public_profile = models.BooleanField(default=True, help_text="Make profile visible to others")
    show_email = models.BooleanField(default=False, help_text="Show email on public profile")
    show_phone = models.BooleanField(default=False, help_text="Show phone on public profile")
    phone_verified = models.BooleanField(default=False, help_text="Phone number verified via OTP")
    social_links = models.JSONField(default=dict, blank=True, help_text="LinkedIn, Twitter, etc.")
    achievements = models.JSONField(default=list, blank=True, help_text="Badges, awards, achievements")
    tokens_balance = models.DecimalField(max_digits=10, decimal_places=0, default=0, help_text="Cached token balance")
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['display_name']
    
    def __str__(self):
        return self.display_name
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)
    
    def get_full_name(self):
        return self.display_name
    
    def get_short_name(self):
        return self.display_name


class University(models.Model):
    GRADE_SCHEME_GRADES = 'grades'
    GRADE_SCHEME_MARKS = 'marks'
    GRADE_SCHEMES = [
        (GRADE_SCHEME_GRADES, 'Letter grades (A, B+, B...)'),
        (GRADE_SCHEME_MARKS, 'Marks (0-100)'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    grade_scheme = models.CharField(max_length=10, choices=GRADE_SCHEMES, default=GRADE_SCHEME_GRADES,
                                    help_text="How grades are entered/computed for this university")
    grade_scheme_config = models.JSONField(default=dict, blank=True,
        help_text=(
            "Optional per-university grading configuration. For 'grades': "
            "{'letter_points': {'A':5,'B+':4,'B':3,'C':2,'D':1,'E':0}}. For 'marks': "
            "{'max_marks':100,'pass_mark':40,'thresholds':[[70,0.2,-10.5],...]} where each "
            "row is [min_marks, slope, intercept] mapping marks to points."
        ))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class College(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='colleges')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.university.name}"


class Program(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='programs')
    duration = models.IntegerField()  # in years
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.college.name}"


class Course(models.Model):
    COURSE_TYPES = [
        ('core', 'Core'),
        ('elective', 'Elective'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    credits = models.IntegerField()
    type = models.CharField(max_length=10, choices=COURSE_TYPES)
    semester = models.IntegerField()
    year = models.IntegerField()
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='courses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['code', 'program']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Student(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='students')
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='students')
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='students')
    year = models.IntegerField()
    semester = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    has_courses = models.BooleanField(default=False,blank=True)
    def __str__(self):
        return f"{self.user.display_name} - {self.program.name}"



class StudentCourse(models.Model): 
    # Version of the canonical "periods" storage shape. Bump only when the
    # JSON layout itself changes in a breaking way.
    PERIODS_VERSION = 2

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='student_courses')
    courses = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.student.user.display_name} - {self.period_count()} course(s) in {len(self.get_periods())} period(s)"

    def save(self, *args, **kwargs):
        """
        Ensure the related student's has_courses flag stays in sync with
        whether there are any courses stored for the student.
        """
        super().save(*args, **kwargs)
        has_any_courses = self.period_count() > 0
        if self.student.has_courses != has_any_courses:
            self.student.has_courses = has_any_courses
            # Save only the field that changed to avoid unnecessary writes
            self.student.save(update_fields=['has_courses'])

    # ------------------------------------------------------------------
    # Canonical "periods" storage helpers
    #
    # The canonical shape of `courses` is:
    #     {"_v": 2, "periods": {"1_1": [ {course dict}, ... ], "1_2": [...] }}
    #
    # Legacy flat arrays (each entry carrying its own year/semester) are
    # transparently recognized and normalized on read, so every consumer gets
    # a uniform view regardless of how the data was written historically.
    # ------------------------------------------------------------------

    @staticmethod
    def _course_dict(d):
        """Normalize a single course entry to canonical keys (id/code/name/credits/type/semester/year/added_at)."""
        if not isinstance(d, dict):
            return None
        cid = d.get('id') or d.get('course_id') or str(uuid.uuid4())
        code = (d.get('code') or d.get('course_code') or '').strip()
        name = d.get('name') or d.get('course_name') or ''
        credits = d.get('credits')
        if credits is None:
            credits = d.get('credit_hour', 0)
        try:
            credits = int(credits or 0)
        except (TypeError, ValueError):
            credits = 0
        t = (str(d.get('type') or '')).strip().lower()
        if t in ('elective', 'optional'):
            ctype = 'elective'
        elif t == 'core':
            ctype = 'core'
        elif d.get('is_elective') is not None:
            ctype = 'elective' if d['is_elective'] else 'core'
        else:
            ctype = 'core'
        return {
            'id': str(cid),
            'code': code,
            'name': name,
            'credits': credits,
            'type': ctype,
            'semester': d.get('semester'),
            'year': d.get('year'),
            'added_at': d.get('added_at'),
        }

    @classmethod
    def period_key(cls, year, semester):
        return f"{int(year)}_{int(semester)}"

    def ensure_periods(self):
        """Return the canonical periods dict, converting legacy flat lists in place (not persisted)."""
        raw = self.courses
        if isinstance(raw, dict) and isinstance(raw.get('periods'), dict):
            periods = {}
            for key, items in raw['periods'].items():
                if not isinstance(items, list):
                    continue
                cleaned = []
                for d in items:
                    cd = self._course_dict(d)
                    if cd:
                        cleaned.append(cd)
                periods[str(key)] = cleaned
            return {'_v': self.PERIODS_VERSION, 'periods': periods}
        # Legacy flat list: group by (year, semester).
        periods = {}
        if isinstance(raw, list):
            for d in raw:
                cd = self._course_dict(d)
                if not cd:
                    continue
                year = cd.get('year')
                sem = cd.get('semester')
                if year is None or sem is None:
                    year = self.student.year if self.student_id else 1
                    sem = self.student.semester if self.student_id else 1
                try:
                    year = int(year)
                except (TypeError, ValueError):
                    year = self.student.year if self.student_id else 1
                try:
                    sem = int(sem)
                except (TypeError, ValueError):
                    sem = self.student.semester if self.student_id else 1
                cd['year'] = year
                cd['semester'] = sem
                periods.setdefault(self.period_key(year, sem), []).append(cd)
        return {'_v': self.PERIODS_VERSION, 'periods': periods}

    def get_periods(self):
        """Return {period_key: [course dict, ...]} for all periods."""
        return self.ensure_periods().get('periods', {})

    def period_count(self):
        """Total number of courses across all periods."""
        return sum(len(v) for v in self.get_periods().values())

    def get_period(self, year, semester):
        """Return the list of course dicts for a given (year, semester), or []."""
        return self.get_periods().get(self.period_key(year, semester), [])

    def set_period(self, year, semester, courses, save=True):
        """
        Replace ONLY the given (year, semester) period's courses, preserving
        every other period untouched. `courses` may be a list of raw dicts.
        Returns the list of normalized course dicts that were stored.
        """
        cleaned = []
        for d in courses or []:
            cd = self._course_dict(d)
            if not cd:
                continue
            cd['year'] = int(year)
            cd['semester'] = int(semester)
            cleaned.append(cd)
        periods = self.get_periods()
        periods[self.period_key(year, semester)] = cleaned
        self.courses = {'_v': self.PERIODS_VERSION, 'periods': periods}
        if save:
            self.save()
        return cleaned

    def add_course_to_period(self, year, semester, course_data, save=True):
        """
        Add a course to the given period if not already present by id.
        Returns (course_dict, added: bool).
        """
        cd = self._course_dict(course_data)
        if not cd:
            return (None, False)
        cd['year'] = int(year)
        cd['semester'] = int(semester)
        key = self.period_key(year, semester)
        periods = self.get_periods()
        items = periods.setdefault(key, [])
        existing_ids = {str(c.get('id')) for c in items if isinstance(c, dict)}
        if cd['id'] in existing_ids:
            return (cd, False)
        items.append(cd)
        periods[key] = items
        self.courses = {'_v': self.PERIODS_VERSION, 'periods': periods}
        if save:
            self.save()
        return (cd, True)

    def update_course_in_period(self, year, semester, course_data, save=True):
        """
        Update an existing course (matched by id) within the given period.
        Returns (course_dict, updated: bool).
        """
        cd = self._course_dict(course_data)
        if not cd:
            return (None, False)
        cd['year'] = int(year)
        cd['semester'] = int(semester)
        key = self.period_key(year, semester)
        periods = self.get_periods()
        items = periods.get(key, [])
        target_id = cd['id']
        for i, existing in enumerate(items):
            if isinstance(existing, dict) and str(existing.get('id')) == target_id:
                items[i] = cd
                periods[key] = items
                self.courses = {'_v': self.PERIODS_VERSION, 'periods': periods}
                if save:
                    self.save()
                return (cd, True)
        return (None, False)

    def remove_course_from_period(self, year, semester, course_id, save=True):
        """
        Remove a course by id from the given period. Returns True if removed.
        """
        target_id = str(course_id)
        key = self.period_key(year, semester)
        periods = self.get_periods()
        items = periods.get(key, [])
        filtered = [c for c in items if not (isinstance(c, dict) and str(c.get('id')) == target_id)]
        if len(filtered) == len(items):
            return False
        if filtered:
            periods[key] = filtered
        else:
            periods.pop(key, None)
        self.courses = {'_v': self.PERIODS_VERSION, 'periods': periods}
        if save:
            self.save()
        return True

    def remove_period(self, year, semester, save=True):
        """Remove an entire period (all its courses). Returns True if it existed."""
        key = self.period_key(year, semester)
        periods = self.get_periods()
        if key not in periods:
            return False
        del periods[key]
        self.courses = {'_v': self.PERIODS_VERSION, 'periods': periods}
        if save:
            self.save()
        return True

    # Backward-compatible wrappers used by older code paths.

    def add_course(self, course_data):
        """Legacy: add a single course into its own (year, semester) period."""
        year = course_data.get('year') or self.student.year or 1
        semester = course_data.get('semester') or self.student.semester or 1
        _, added = self.add_course_to_period(year, semester, course_data)
        return added

    def remove_course(self, course_id):
        """Legacy: remove a course by id from whichever period contains it."""
        for key, items in self.get_periods().items():
            for item in items:
                if isinstance(item, dict) and str(item.get('id')) == str(course_id):
                    parts = str(key).split('_')
                    year = int(parts[0]) if parts else 1
                    sem = int(parts[1]) if len(parts) > 1 else 1
                    return self.remove_course_from_period(year, sem, course_id)
        return False

    def next_period(self, year, semester):
        """
        Given a (year, semester), return the (next_year, next_semester) tuple
        treating the year as 1-indexed with two semesters per academic year.
        """
        if int(semester) == 1:
            return (int(year), 2)
        return (int(year) + 1, 1)


class StudentTerm(models.Model):
    """A student's academic term (a specific academic_year + semester).

    This is the anchor for per-year/per-semester course history. Each student
    has one row per (academic_year, semester) they have engaged with, enabling
    a 4th-year student to see (and compute GPA from) their 1st-year data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='terms')
    academic_year = models.IntegerField(help_text="Academic year (1, 2, 3, ...)")
    semester = models.IntegerField(help_text="Semester (1 or 2)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'academic_year', 'semester']
        ordering = ['academic_year', 'semester']

    def __str__(self):
        return f"{self.student.user.display_name} - Yr{self.academic_year} Sem{self.semester}"


class StudentCourseEnrollment(models.Model):
    """A course the student is enrolled in / entered grades for, within one term.

    `course` links to the master Course catalog when it exists; it is nullable so
    custom/freestyle courses not in the catalog can still be stored (code/name/
    credits/type are denormalized to survive without a master row).
    """
    COURSE_TYPES = [
        ('core', 'Core'),
        ('elective', 'Elective'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    term = models.ForeignKey(StudentTerm, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, related_name='student_enrollments',
                               null=True, blank=True)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    credits = models.IntegerField(default=0)
    type = models.CharField(max_length=10, choices=COURSE_TYPES, default='core')
    grade = models.CharField(max_length=4, blank=True, null=True, help_text="Letter grade e.g. 'A', 'B+'")
    marks = models.IntegerField(blank=True, null=True, help_text="Raw marks (0-100) for marks-based schemes")
    points = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True,
                                 help_text="Grade point value (0.00-5.00)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['term', 'code']
        ordering = ['code']

    def __str__(self):
        return f"{self.term} - {self.code}"


class TimetableSlot(models.Model):
    """Timetable slots for student schedules"""
    CLASS_TYPE_CHOICES = [
        ('lecture', 'Lecture'),
        ('tutorial', 'Tutorial'),
        ('practical', 'Practical'),
        ('seminar', 'Seminar'),
        ('exam', 'Exam'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='timetable_slots')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, related_name='timetable_slots', null=True, blank=True)
    student_course = models.ForeignKey(StudentCourse, on_delete=models.SET_NULL, related_name='timetable_slots', null=True, blank=True)
    course_code = models.CharField(max_length=20, blank=True, null=True)  # Keep for backward compatibility
    course_name = models.CharField(max_length=200, blank=True, null=True)  # Keep for backward compatibility
    time_slot = models.CharField(max_length=20, help_text="Format: HHMM-HHMM (e.g., 0800-1000)")
    day_of_week = models.CharField(max_length=10, choices=[
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
    ])
    semester = models.IntegerField(default=1)
    academic_year = models.CharField(max_length=10, default='2024')
    class_type = models.CharField(max_length=20, choices=CLASS_TYPE_CHOICES, default='lecture')
    venue = models.CharField(max_length=100, blank=True, null=True)
    instructor = models.CharField(max_length=100, blank=True, null=True)  # Renamed from instructor_name
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['day_of_week', 'time_slot']
        indexes = [
            models.Index(fields=['student', 'semester', 'academic_year']),
            models.Index(fields=['day_of_week']),
        ]
    
    def __str__(self):
        return f"{self.course_code or self.course_name or 'Course'} - {self.day_of_week} {self.time_slot}"


class Article(models.Model):
    """Articles for the knowledge base"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    content = models.TextField()
    excerpt = models.TextField(blank=True, null=True, help_text="Short description of the article")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='articles')
    category = models.CharField(max_length=50, choices=[
        ('academic', 'Academic'),
        ('campus_life', 'Campus Life'),
        ('news', 'News'),
        ('events', 'Events'),
        ('general', 'General'),
    ], default='general')
    tags = models.JSONField(default=list, blank=True, help_text="List of tags")
    cover_image = models.ImageField(upload_to='articles/', blank=True, null=True)
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ], default='published')
    views = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    read_time = models.IntegerField(default=5, help_text="Estimated read time in minutes")
    share_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_published', 'is_featured']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return self.title


class ArticleLike(models.Model):
    """Tracks which users have liked an article."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='user_likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='liked_articles')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('article', 'user')
        indexes = [
            models.Index(fields=['article', 'user']),
        ]

    def __str__(self):
        return f"{self.user} liked {self.article}"


class ArticleComment(models.Model):
    """Threaded comments on published articles."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='article_comments',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['article', 'created_at']),
            models.Index(fields=['parent']),
        ]

    def __str__(self):
        return f"{self.user.display_name} on {self.article_id}"


class Notification(models.Model):
    """Notifications for users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField(default='')  # Renamed from message to body
    notification_type = models.CharField(max_length=50, choices=[
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('success', 'Success'),
        ('error', 'Error'),
    ], default='info')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    link = models.URLField(blank=True, null=True, help_text="Link when notification is clicked")
    slide = models.ForeignKey('Slide', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.user.display_name} - {self.title}"


class Slide(models.Model):
    """Slides for carousel/banner functionality"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='slides/', blank=True, null=True)
    image_url = models.URLField(blank=True, null=True, help_text="External image URL")
    link_url = models.URLField(blank=True, null=True, help_text="Link when slide is clicked")
    button_text = models.CharField(max_length=50, blank=True, null=True)
    background_gradient = models.CharField(max_length=100, blank=True, null=True, help_text="CSS gradient class")
    slide_type = models.CharField(max_length=50, choices=[
        ('banner', 'Banner'),
        ('carousel', 'Carousel'),
        ('promotion', 'Promotion'),
        ('announcement', 'Announcement'),
    ], default='banner')
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0, help_text="Display order (lower numbers first)")
    start_date = models.DateTimeField(blank=True, null=True, help_text="When to start showing this slide")
    end_date = models.DateTimeField(blank=True, null=True, help_text="When to stop showing this slide")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'order']),
            models.Index(fields=['slide_type']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def image_display(self):
        """Return the image URL for display"""
        if self.image:
            return self.image.url
        elif self.image_url:
            return self.image_url
        return None


class HelpMessage(models.Model):
    """Help messages from users asking for support"""
    SUBJECT_CHOICES = [
        ('General Inquiry', 'General Inquiry'),
        ('Account & Login', 'Account & Login'),
        ('Timetable Help', 'Timetable Help'),
        ('GPA Calculator', 'GPA Calculator'),
        ('Bug Report', 'Bug Report'),
        ('Feature Request', 'Feature Request'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.CharField(max_length=200, choices=SUBJECT_CHOICES)
    message = models.TextField()
    user_email = models.EmailField()
    user_name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='help_messages')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    ticket_number = models.CharField(max_length=20, unique=True, blank=True)
    admin_response = models.TextField(blank=True, null=True)
    admin_responded_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['user_email']),
            models.Index(fields=['ticket_number']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            # Generate ticket number: HC-YYYY-MM-DD-XXXX
            date_str = timezone.now().strftime('%Y-%m-%d')
            # Get count of messages created today for the sequence number
            today_count = HelpMessage.objects.filter(
                created_at__date=timezone.now().date()
            ).count()
            self.ticket_number = f"HC-{date_str}-{today_count + 1:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.ticket_number} - {self.subject} ({self.user_name})"


class Quote(models.Model):
    """Inspirational quotes for the application"""
    text = models.TextField()
    author = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.author}: {self.text[:50]}..."


# RBAC: Map ambassadors to specific universities
class UniversityAmbassador(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ambassador_links')
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='ambassadors')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'university')
        indexes = [
            models.Index(fields=['user', 'university']),
        ]

    def __str__(self):
        return f"{self.user.display_name} -> {self.university.name}"


class AmbassadorActivity(models.Model):
    """Track activities performed by ambassadors"""
    ACTIVITY_TYPES = [
        ('assigned', 'Assigned to University'),
        ('message_sent', 'Message Sent'),
        ('message_received', 'Message Received'),
        ('login', 'Login'),
        ('profile_updated', 'Profile Updated'),
        ('university_joined', 'Joined University'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ambassador = models.ForeignKey(UniversityAmbassador, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)  # For storing additional data
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ambassador', '-created_at']),
            models.Index(fields=['activity_type']),
        ]

    def __str__(self):
        return f"{self.ambassador.user.display_name} - {self.activity_type}"


class AmbassadorMessage(models.Model):
    """Messages between staff and ambassadors"""
    MESSAGE_STATUS = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('completed', 'Completed'),
    ]

    MESSAGE_PRIORITY = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_ambassador_messages')
    recipient = models.ForeignKey(UniversityAmbassador, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=MESSAGE_PRIORITY, default='normal')
    status = models.CharField(max_length=10, choices=MESSAGE_STATUS, default='sent')
    read_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        return f"{self.sender.display_name} -> {self.recipient.user.display_name}: {self.subject}"


class UniversityLink(models.Model):
    """University-related external links"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    url = models.URLField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='links', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['university']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        if self.university:
            return f"{self.name} ({self.university.name})"
        return f"{self.name} (Universal)"


class GPACalculation(models.Model):
    """Store encrypted GPA calculation events for users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gpa_calculations')
    gpa_ciphertext = models.TextField(help_text="Encrypted GPA payload (base64 ciphertext)", default='', null=True, blank=True)
    gpa_iv = models.CharField(max_length=64, help_text="Base64 IV/nonce used for encryption", default='', null=True, blank=True)
    gpa_salt = models.CharField(max_length=128, help_text="Base64 salt used for key derivation", default='', null=True, blank=True)
    gpa_alg = models.CharField(max_length=50, default='AES-GCM-PBKDF2', help_text="Client-side encryption algorithm metadata", null=True, blank=True)
    semester = models.IntegerField(help_text="Semester number (1 or 2)")
    academic_year = models.IntegerField(help_text="Academic year (1, 2, 3, etc.)")
    is_target = models.BooleanField(default=False, help_text="True if this is a target GPA calculation")
    
    # NEW FIELDS for enhanced GPA tracking
    feedback = models.TextField(blank=True, help_text="User's explanation of GPA result vs expectation")
    feedback_tokens_awarded = models.IntegerField(default=0, help_text="Tokens awarded for providing feedback")
    is_planned = models.BooleanField(default=False, help_text="Was this a planned/target GPA calculation?")
    planned_gpa_value = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, help_text="Target GPA if planned")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['semester', 'academic_year']),
            models.Index(fields=['is_target']),
        ]
    
    def __str__(self):
        gpa_type = "Target" if self.is_target else "Actual"
        return f"{self.user.display_name} - {gpa_type} GPA event (encrypted) (Sem {self.semester}, Year {self.academic_year})"


class LoginActivity(models.Model):
    """Track user login activity for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_activities')
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    login_type = models.CharField(max_length=20, choices=[
        ('email', 'Email/Password'),
        ('firebase', 'Firebase'),
        ('jwt_refresh', 'JWT Refresh'),
        ('admin', 'Admin Dashboard'),
    ], default='email')
    success = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-login_time']
        indexes = [
            models.Index(fields=['user', '-login_time']),
            models.Index(fields=['-login_time']),
            models.Index(fields=['login_type']),
            models.Index(fields=['success']),
        ]
        verbose_name_plural = 'Login Activities'
    
    def __str__(self):
        return f"{self.user.display_name} - {self.login_time.strftime('%Y-%m-%d %H:%M')}"
