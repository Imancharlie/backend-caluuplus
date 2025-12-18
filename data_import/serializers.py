from rest_framework import serializers
from .models import ImportJob, ImportError, RetryJob


class ImportJobSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.display_name', read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            'id', 'import_type', 'status', 'filename', 'uploaded_by', 'uploaded_by_name',
            'total_rows', 'processed_rows', 'successful_rows', 'failed_rows',
            'progress_percentage', 'duration', 'created_at', 'completed_at', 'error_message'
        ]
        read_only_fields = ['id', 'uploaded_by', 'created_at', 'completed_at']

    def get_progress_percentage(self, obj):
        if obj.total_rows == 0:
            return 0
        return round((obj.processed_rows / obj.total_rows) * 100, 2)

    def get_duration(self, obj):
        if obj.completed_at and obj.created_at:
            duration = obj.completed_at - obj.created_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None


class ImportErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportError
        fields = [
            'id', 'row_number', 'error_type', 'field_name', 'error_message',
            'original_data', 'created_at'
        ]


class ImportJobDetailSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.display_name', read_only=True)
    errors = ImportErrorSerializer(many=True, read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            'id', 'import_type', 'status', 'filename', 'uploaded_by', 'uploaded_by_name',
            'total_rows', 'processed_rows', 'successful_rows', 'failed_rows',
            'progress_percentage', 'duration', 'errors', 'created_at', 'completed_at', 'error_message'
        ]

    def get_progress_percentage(self, obj):
        if obj.total_rows == 0:
            return 0
        return round((obj.processed_rows / obj.total_rows) * 100, 2)

    def get_duration(self, obj):
        if obj.completed_at and obj.created_at:
            duration = obj.completed_at - obj.created_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None


class RetryJobSerializer(serializers.ModelSerializer):
    original_import_job_details = serializers.SerializerMethodField()

    class Meta:
        model = RetryJob
        fields = [
            'id', 'original_import_job', 'original_import_job_details',
            'status', 'total_errors', 'resolved_errors',
            'created_at', 'completed_at'
        ]
        read_only_fields = ['id', 'created_at', 'completed_at']

    def get_original_import_job_details(self, obj):
        return {
            'id': obj.original_import_job.id,
            'import_type': obj.original_import_job.import_type,
            'filename': obj.original_import_job.filename,
            'status': obj.original_import_job.status,
        }


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    import_type = serializers.ChoiceField(choices=[
        ('university_programs', 'University, College, Programs'),
        ('courses', 'Courses'),
    ])

    def validate_file(self, value):
        # Check file extension
        allowed_extensions = ['.xlsx', '.xls', '.csv']
        file_extension = value.name.split('.')[-1].lower()

        if f'.{file_extension}' not in allowed_extensions:
            raise serializers.ValidationError(
                f'Unsupported file format. Allowed formats: {", ".join(allowed_extensions)}'
            )

        # Check file size (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File size must be less than 10MB')

        return value













