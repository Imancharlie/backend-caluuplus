from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import User, University, College, Program, Course, Student, StudentCourse, Article, Slide, HelpMessage, Quote, Notification, UniversityAmbassador, AmbassadorActivity, AmbassadorMessage, UniversityLink


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('email', 'password', 'password_confirm', 'display_name', 'is_student', 'phone_number')
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        
        # Check if user already exists with this email
        email = attrs.get('email')
        if email:
            try:
                existing_user = User.objects.get(email=email)
                # If user exists but has no password (Google-only user), allow registration to set password
                if existing_user.has_usable_password():
                    raise serializers.ValidationError({
                        'email': 'A user with this email already exists. Please login instead.'
                    })
                # User exists but no password - this will be handled in create()
            except User.DoesNotExist:
                pass  # New user, proceed with registration
        
        return attrs
    
    def create(self, validated_data):
        password_confirm = validated_data.pop('password_confirm')
        email = validated_data.get('email')
        password = validated_data.get('password')
        
        # Check if user already exists (from Google login) but has no password
        try:
            existing_user = User.objects.get(email=email)
            # User exists from Google login, now setting password
            if not existing_user.has_usable_password():
                existing_user.set_password(password)
                # Update other fields if provided
                if 'display_name' in validated_data:
                    existing_user.display_name = validated_data['display_name']
                if 'is_student' in validated_data:
                    existing_user.is_student = validated_data['is_student']
                if 'phone_number' in validated_data:
                    existing_user.phone_number = validated_data['phone_number']
                existing_user.save()
                return existing_user
        except User.DoesNotExist:
            pass
        
        # New user registration
        validated_data['username'] = validated_data['email']
        user = User.objects.create_user(**validated_data)
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include email and password')
        
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'display_name', 'is_student', 'phone_number', 'phone_verified', 'tokens_balance')


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'display_name', 'is_student', 'phone_number')

    def validate_email(self, value):
        user = self.context['request'].user
        if value and value != user.email:
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError('A user with this email already exists.')
        return value


class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = ('id', 'name', 'country')


class CollegeSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)
    
    class Meta:
        model = College
        fields = ('id', 'name', 'university', 'university_name')


class ProgramSerializer(serializers.ModelSerializer):
    college_name = serializers.CharField(source='college.name', read_only=True)
    university_name = serializers.CharField(source='college.university.name', read_only=True)
    
    class Meta:
        model = Program
        fields = ('id', 'name', 'college', 'college_name', 'university_name', 'duration')


class CourseSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source='program.name', read_only=True)
    
    class Meta:
        model = Course
        fields = ('id', 'code', 'name', 'credits', 'type', 'semester', 'year', 'program', 'program_name')


class StudentCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentCourse
        fields = ('id', 'courses', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

class CourseDataSerializer(serializers.Serializer):
    # Support both naming conventions: backend (code, name) and frontend (course_code, course_name)
    id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    course_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)  # Frontend naming
    
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    course_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)  # Frontend naming
    
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    course_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)  # Frontend naming
    
    credits = serializers.IntegerField(required=False, allow_null=True)
    credit_hour = serializers.IntegerField(required=False, allow_null=True)  # Frontend naming
    
    type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_elective = serializers.BooleanField(required=False, allow_null=True)  # Frontend naming
    
    semester = serializers.IntegerField(required=False, allow_null=True)
    year = serializers.IntegerField(required=False, allow_null=True)
    added_at = serializers.DateTimeField(required=False, allow_null=True)
    
    def validate(self, data):
        # Normalize field names - map frontend names to backend names
        # Handle course_id -> id
        if 'course_id' in data and data['course_id'] and not data.get('id'):
            data['id'] = data['course_id']
        
        # Handle course_code -> code
        if 'course_code' in data and data['course_code'] and not data.get('code'):
            data['code'] = data['course_code']
        
        # Handle course_name -> name
        if 'course_name' in data and data['course_name'] and not data.get('name'):
            data['name'] = data['course_name']
        
        # Handle credit_hour -> credits
        if 'credit_hour' in data and data['credit_hour'] is not None and data.get('credits') is None:
            data['credits'] = data['credit_hour']
        
        # Handle is_elective -> type
        if 'is_elective' in data and data['is_elective'] is not None and not data.get('type'):
            data['type'] = 'elective' if data['is_elective'] else 'core'
        
        return data

class StudentCourseUpdateSerializer(serializers.Serializer):
    courses = CourseDataSerializer(many=True)


class StudentSerializer(serializers.ModelSerializer):
    university = UniversitySerializer(read_only=True)
    college = CollegeSerializer(read_only=True)
    program = ProgramSerializer(read_only=True)
    courses = serializers.JSONField(source='student_courses.courses', read_only=True)
    has_courses = serializers.BooleanField(read_only=True)
    class Meta:
        model = Student
        fields = ('id', 'university', 'college', 'program', 'year', 'semester', 'courses', 'has_courses')


class StudentCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ('university', 'college', 'program', 'year', 'semester')
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class GPABreakdownSerializer(serializers.Serializer):
    gpa = serializers.FloatField()
    total_credits = serializers.IntegerField()
    total_points = serializers.FloatField()
    graded_courses = serializers.IntegerField()
    breakdown = serializers.ListField()


class TargetGPASerializer(serializers.Serializer):
    target_gpa = serializers.FloatField(min_value=0.0, max_value=5.0)


class GPACalculationSerializer(serializers.Serializer):
    # Preferred input: plaintext gpa (backend will encrypt automatically)
    gpa = serializers.DecimalField(required=False, max_digits=3, decimal_places=2, min_value=0.0, max_value=5.0)
    # Backward-compatible encrypted payload input (optional)
    gpa_ciphertext = serializers.CharField(required=False, allow_blank=True)
    gpa_iv = serializers.CharField(required=False, allow_blank=True)
    gpa_salt = serializers.CharField(required=False, allow_blank=True)
    gpa_alg = serializers.CharField(required=False, allow_blank=True, default='AES-GCM-PBKDF2')
    semester = serializers.IntegerField(min_value=1, max_value=2)
    academic_year = serializers.IntegerField(min_value=1)
    is_target = serializers.BooleanField(default=False)

    def validate(self, attrs):
        has_plain = attrs.get('gpa') is not None
        has_encrypted = all(
            attrs.get(key) is not None and str(attrs.get(key)).strip() != ''
            for key in ('gpa_ciphertext', 'gpa_iv', 'gpa_salt')
        )
        if not has_plain and not has_encrypted:
            raise serializers.ValidationError(
                "Provide either 'gpa' for automatic server-side encryption, "
                "or encrypted fields: gpa_ciphertext, gpa_iv, gpa_salt."
            )

        attrs['gpa_alg'] = (attrs.get('gpa_alg') or 'AES-GCM-PBKDF2').strip() or 'AES-GCM-PBKDF2'
        return attrs




class CourseAddSerializer(serializers.Serializer):
    course_id = serializers.UUIDField(required=False, allow_null=True)
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    credits = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=[('core', 'Core'), ('elective', 'Elective')], required=False, default='core')
    semester = serializers.IntegerField(required=False, allow_null=True)
    year = serializers.IntegerField(required=False, allow_null=True)
    
    def validate(self, data):
        # Either course_id must be provided, or course details (code, name, credits, semester, year) must be provided
        course_id = data.get('course_id')
        code = data.get('code')
        name = data.get('name')
        credits = data.get('credits')
        semester = data.get('semester')
        year = data.get('year')
        
        if not course_id and not (code and name and credits is not None and semester is not None and year is not None):
            raise serializers.ValidationError(
                "Either 'course_id' must be provided, or all of 'code', 'name', 'credits', 'semester', and 'year' must be provided."
            )
        return data


class ArticleSerializer(serializers.ModelSerializer):
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Article
        fields = (
            'id', 'title', 'content', 'excerpt', 'author', 'category', 'tags',
            'cover_image', 'is_published', 'is_featured', 'status',
            'views', 'likes', 'read_time', 'share_count',
            'created_at', 'updated_at', 'published_at'
        )
        read_only_fields = ('id', 'author', 'views', 'likes', 'share_count', 'created_at', 'updated_at')

    def validate_category(self, value):
        """
        Normalize and validate category:
        - null/blank -> general
        - normalize casing/whitespace
        - enforce enum membership
        """
        if value is None or str(value).strip() == '':
            return 'general'

        normalized = str(value).strip().lower()
        allowed_values = {choice for choice, _label in Article._meta.get_field('category').choices}
        if normalized not in allowed_values:
            raise serializers.ValidationError(
                f"Invalid category '{value}'. Allowed values: {', '.join(sorted(allowed_values))}."
            )
        return normalized

    def validate(self, attrs):
        # Ensure create requests can omit category and still persist safely.
        if self.instance is None and not attrs.get('category'):
            attrs['category'] = 'general'
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['author'] = request.user
        if validated_data.get('is_published') and not validated_data.get('published_at'):
            validated_data['published_at'] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        is_published = validated_data.get('is_published')
        if is_published is True and not instance.published_at and not validated_data.get('published_at'):
            validated_data['published_at'] = timezone.now()
        return super().update(instance, validated_data)


class SlideSerializer(serializers.ModelSerializer):
    image_display = serializers.ReadOnlyField()

    class Meta:
        model = Slide
        fields = (
            'id', 'title', 'description', 'image', 'image_url', 'image_display',
            'link_url', 'button_text', 'background_gradient', 'slide_type',
            'is_active', 'order', 'start_date', 'end_date',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'image_display', 'created_at', 'updated_at')


class HelpMessageSerializer(serializers.ModelSerializer):
    """Serializer for help messages"""
    
    class Meta:
        model = HelpMessage
        fields = ['subject', 'message', 'user_email', 'user_name']
        
    def validate_subject(self, value):
        """Validate that the subject is one of the allowed choices"""
        valid_subjects = [
            'General Inquiry',
            'Account & Login', 
            'Timetable Help',
            'GPA Calculator',
            'Bug Report',
            'Feature Request'
        ]
        if value not in valid_subjects:
            raise serializers.ValidationError("Invalid subject selected.")
        return value
    
    def validate_message(self, value):
        """Validate message content"""
        if not value or not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Message must be at least 3 characters long.")
        return value.strip()
    
    def validate_user_email(self, value):
        """Validate email format"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Please provide a valid email address.")
        return value.lower()
    
    def validate_user_name(self, value):
        """Validate user name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()


class HelpMessageResponseSerializer(serializers.ModelSerializer):
    """Serializer for help message responses (includes all fields)"""
    
    class Meta:
        model = HelpMessage
        fields = [
            'id', 'subject', 'message', 'user_email', 'user_name', 
            'status', 'ticket_number', 'admin_response', 'admin_responded_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'ticket_number', 'admin_response', 
            'admin_responded_at', 'created_at', 'updated_at'
        ]


class QuoteSerializer(serializers.ModelSerializer):
    """Serializer for quotes"""
    
    class Meta:
        model = Quote
        fields = ['id', 'text', 'author', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate_text(self, value):
        """Validate quote text"""
        if not value or not value.strip():
            raise serializers.ValidationError("Quote text cannot be empty.")
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Quote text must be at least 10 characters long.")
        return value.strip()
    
    def validate_author(self, value):
        """Validate author name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Author name cannot be empty.")
        return value.strip()


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        old_password = attrs.get('old_password')
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')
        if not user.check_password(old_password):
            raise serializers.ValidationError({'old_password': 'Old password is incorrect'})
        if new_password != new_password_confirm:
            raise serializers.ValidationError({'new_password_confirm': "Passwords don't match"})
        validate_password(new_password, user)
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.display_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_name', 'user_email', 'title', 'body',
            'notification_type', 'is_read', 'read_at', 'link', 'slide',
            'created_at'
        ]
        read_only_fields = ['id', 'is_read', 'read_at', 'created_at']


class UserSearchSerializer(serializers.ModelSerializer):
    """Serializer for user search results in notifications"""
    avatar_initials = serializers.SerializerMethodField()
    avatar_color = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'display_name', 'email', 'avatar_initials', 'avatar_color'
        ]

    def get_avatar_initials(self, obj):
        """Generate initials from display name"""
        if obj.display_name:
            words = obj.display_name.split()
            if len(words) >= 2:
                return f"{words[0][0]}{words[1][0]}".upper()
            else:
                return obj.display_name[:2].upper()
        return obj.email[:2].upper()

    def get_avatar_color(self, obj):
        """Generate consistent color for user avatar"""
        # Simple hash-based color generation
        import hashlib
        hash_obj = hashlib.md5(obj.email.encode())
        hash_hex = hash_obj.hexdigest()
        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899']
        color_index = int(hash_hex[-1], 16) % len(colors)
        return colors[color_index]


class UniversityAmbassadorSerializer(serializers.ModelSerializer):
    """Serializer for University Ambassador"""
    user_name = serializers.CharField(source='user.display_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = UniversityAmbassador
        fields = ['id', 'user', 'user_name', 'user_email', 'university', 'university_name', 'created_at']
        read_only_fields = ['id', 'created_at']


class AmbassadorActivitySerializer(serializers.ModelSerializer):
    """Serializer for Ambassador Activity"""
    ambassador_name = serializers.CharField(source='ambassador.user.display_name', read_only=True)
    university_name = serializers.CharField(source='ambassador.university.name', read_only=True)

    class Meta:
        model = AmbassadorActivity
        fields = ['id', 'ambassador', 'ambassador_name', 'university_name', 'activity_type', 'description', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']


class AmbassadorMessageSerializer(serializers.ModelSerializer):
    """Serializer for Ambassador Messages"""
    sender_name = serializers.CharField(source='sender.display_name', read_only=True)
    sender_email = serializers.EmailField(source='sender.email', read_only=True)
    recipient_name = serializers.CharField(source='recipient.user.display_name', read_only=True)
    university_name = serializers.CharField(source='recipient.university.name', read_only=True)

    class Meta:
        model = AmbassadorMessage
        fields = [
            'id', 'sender', 'sender_name', 'sender_email',
            'recipient', 'recipient_name', 'university_name',
            'subject', 'message', 'priority', 'status',
            'read_at', 'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'read_at', 'completed_at', 'created_at', 'updated_at']


class AmbassadorMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Ambassador Messages"""
    class Meta:
        model = AmbassadorMessage
        fields = ['recipient', 'subject', 'message', 'priority']

    def validate_recipient(self, value):
        """Ensure the recipient is a valid ambassador"""
        if not UniversityAmbassador.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Invalid ambassador selected.")
        return value

    def validate_subject(self, value):
        """Validate subject"""
        if not value or not value.strip():
            raise serializers.ValidationError("Subject cannot be empty.")
        return value.strip()

    def validate_message(self, value):
        """Validate message"""
        if not value or not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Message must be at least 10 characters long.")
        return value.strip()


class UniversityLinkSerializer(serializers.ModelSerializer):
    """Serializer for University Links"""
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = UniversityLink
        fields = [
            'id', 'name', 'url', 'description', 'is_active',
            'university', 'university_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']