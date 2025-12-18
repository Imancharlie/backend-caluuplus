from rest_framework import serializers
from django.core.files.base import ContentFile
from .models import Resource, Opportunity

# Try to import magic, but handle gracefully if not available
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False


class ResourceSerializer(serializers.ModelSerializer):
    """
    Serializer for Resource model with file validation and metadata extraction.
    """
    file_size = serializers.SerializerMethodField(read_only=True)
    file_url = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = Resource
        fields = [
            'id', 'university', 'university_name', 'title', 'description',
            'file', 'file_type', 'file_size', 'file_url',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_type', 'file_size', 'file_url', 'created_by_name', 'created_at', 'updated_at']

    def validate_file(self, value):
        """Validate uploaded file."""
        if not value:
            raise serializers.ValidationError("File is required.")

        # Check file size (limit to 50MB)
        max_size = 50 * 1024 * 1024  # 50MB
        if value.size > max_size:
            raise serializers.ValidationError(f"File size must be less than {max_size / (1024*1024):.1f}MB.")

        # Validate file type based on content (magic numbers) if available
        if MAGIC_AVAILABLE:
            try:
                mime = magic.from_buffer(value.read(1024), mime=True)
                value.seek(0)  # Reset file pointer

                # Map MIME types to file types
                mime_to_type = {
                    'application/pdf': 'pdf',
                    'application/msword': 'doc',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                    'application/vnd.ms-excel': 'xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
                    'application/vnd.ms-powerpoint': 'ppt',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
                    'text/plain': 'txt',
                    'application/zip': 'zip',
                    'application/x-rar-compressed': 'rar',
                    'image/jpeg': 'image',
                    'image/png': 'image',
                    'image/gif': 'image',
                    'image/webp': 'image',
                    'video/mp4': 'video',
                    'video/mpeg': 'video',
                    'video/quicktime': 'video',
                    'audio/mpeg': 'audio',
                    'audio/wav': 'audio',
                }

                file_type = mime_to_type.get(mime, 'unknown')
                if file_type == 'unknown':
                    raise serializers.ValidationError(f"Unsupported file type: {mime}")

                # Store file type for later use
                self.context['file_type'] = file_type

            except Exception as e:
                raise serializers.ValidationError(f"Could not determine file type: {str(e)}")
        else:
            # Fallback: determine file type from extension
            file_name = value.name.lower()
            extension_to_type = {
                '.pdf': 'pdf',
                '.doc': 'doc',
                '.docx': 'docx',
                '.xls': 'xls',
                '.xlsx': 'xlsx',
                '.ppt': 'ppt',
                '.pptx': 'pptx',
                '.txt': 'txt',
                '.zip': 'zip',
                '.rar': 'rar',
                '.jpg': 'image',
                '.jpeg': 'image',
                '.png': 'image',
                '.gif': 'image',
                '.webp': 'image',
                '.mp4': 'video',
                '.avi': 'video',
                '.mov': 'video',
                '.mp3': 'audio',
                '.wav': 'audio',
            }

            file_type = 'unknown'
            for ext, ftype in extension_to_type.items():
                if file_name.endswith(ext):
                    file_type = ftype
                    break

            if file_type == 'unknown':
                raise serializers.ValidationError("Unsupported file type. Please upload PDF, DOC, XLS, PPT, TXT, ZIP, RAR, image, video, or audio files.")

            # Store file type for later use
            self.context['file_type'] = file_type

        return value

    def create(self, validated_data):
        """Create resource and set file_type."""
        file_type = self.context.get('file_type', 'unknown')
        validated_data['file_type'] = file_type
        return super().create(validated_data)

    def get_file_size(self, obj):
        """Get formatted file size."""
        if obj.file:
            size = obj.file.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f}{unit}"
                size /= 1024.0
        return None

    def get_file_url(self, obj):
        """Get file URL."""
        if obj.file:
            return obj.file.url
        return None

    def get_created_by_name(self, obj):
        """Get creator's display name."""
        if obj.created_by:
            return obj.created_by.display_name
        return None


class OpportunitySerializer(serializers.ModelSerializer):
    """
    Serializer for Opportunity model with media validation and comprehensive fields.
    """
    cover_media_url = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)
    days_remaining = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Opportunity
        fields = [
            'id', 'university', 'university_name', 'category', 'title',
            'cover_media', 'cover_media_url', 'media_type', 'content',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
            'start_date', 'end_date', 'application_url',
            'days_remaining', 'is_active', 'status'
        ]
        read_only_fields = [
            'id', 'cover_media_url', 'created_by_name', 'created_at', 'updated_at',
            'days_remaining', 'is_active', 'status'
        ]

    def validate_cover_media(self, value):
        """Validate cover media file."""
        if value:
            # Check file size (limit to 10MB for media)
            max_size = 10 * 1024 * 1024  # 10MB
            if value.size > max_size:
                raise serializers.ValidationError(f"Media file size must be less than {max_size / (1024*1024):.1f}MB.")

            # Validate media type
            if MAGIC_AVAILABLE:
                try:
                    mime = magic.from_buffer(value.read(1024), mime=True)
                    value.seek(0)  # Reset file pointer

                    # Check if it's an image or video
                    if not mime.startswith(('image/', 'video/')):
                        raise serializers.ValidationError(f"File must be an image or video, got: {mime}")

                    # Determine media type
                    if mime.startswith('image/'):
                        media_type = 'image'
                    elif mime.startswith('video/'):
                        media_type = 'video'
                    else:
                        raise serializers.ValidationError("Unsupported media type.")

                    # Store media type for later use
                    self.context['media_type'] = media_type

                except Exception as e:
                    raise serializers.ValidationError(f"Could not determine media type: {str(e)}")
            else:
                # Fallback: determine media type from extension
                file_name = value.name.lower()
                image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
                video_extensions = ['.mp4', '.avi', '.mov']

                media_type = None
                if any(file_name.endswith(ext) for ext in image_extensions):
                    media_type = 'image'
                elif any(file_name.endswith(ext) for ext in video_extensions):
                    media_type = 'video'

                if not media_type:
                    raise serializers.ValidationError("File must be an image or video file.")

                # Store media type for later use
                self.context['media_type'] = media_type

        return value

    def validate(self, data):
        """Validate opportunity dates."""
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError("Start date must be before or equal to end date.")

        return data

    def create(self, validated_data):
        """Create opportunity and set media_type."""
        media_type = self.context.get('media_type')
        if media_type:
            validated_data['media_type'] = media_type
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update opportunity and handle media_type."""
        media_type = self.context.get('media_type')
        if media_type:
            validated_data['media_type'] = media_type
        return super().update(instance, validated_data)

    def get_cover_media_url(self, obj):
        """Get cover media URL."""
        if obj.cover_media:
            return obj.cover_media.url
        return None

    def get_created_by_name(self, obj):
        """Get creator's display name."""
        if obj.created_by:
            return obj.created_by.display_name
        return None

    def get_days_remaining(self, obj):
        """Calculate days remaining until end date."""
        if obj.end_date:
            from django.utils import timezone
            today = timezone.now().date()
            if obj.end_date >= today:
                return (obj.end_date - today).days
        return None

    def get_is_active(self, obj):
        """Check if opportunity is currently active based on status and dates."""
        # First check status - must be approved
        if obj.status != 'approved' or not obj.is_active:
            return False
        
        # Then check dates
        from django.utils import timezone
        today = timezone.now().date()

        if obj.start_date and obj.start_date > today:
            return False  # Not yet started

        if obj.end_date and obj.end_date < today:
            return False  # Already ended

        return True  # Currently active
