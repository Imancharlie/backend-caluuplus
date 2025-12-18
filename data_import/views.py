import pandas as pd
import os
import uuid
import logging
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import ImportJob, ImportError
from .serializers import FileUploadSerializer, ImportJobSerializer, ImportJobDetailSerializer
from api.models import University, College, Program, Course
from api.permissions import user_is_admin

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_and_import_university_data(request):
    """
    Upload and import university, college, program data from Excel/CSV file.
    Smart import that creates missing dependencies automatically.
    """
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    # Validate file upload
    serializer = FileUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    file = serializer.validated_data['file']
    import_type = serializer.validated_data['import_type']

    if import_type != 'university_programs':
        return Response({'error': 'This endpoint only accepts university_programs import type'},
                       status=status.HTTP_400_BAD_REQUEST)

    # Save file temporarily
    filename = f"import_{uuid.uuid4()}_{file.name}"
    file_path = os.path.join(settings.MEDIA_ROOT, 'imports', filename)

    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Save file
    with open(file_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Create import job
    import_job = ImportJob.objects.create(
        import_type=import_type,
        filename=file.name,
        uploaded_by=request.user,
        status='processing'
    )

    # Process file synchronously
    try:
        result = process_university_import_sync(import_job.id, file_path)
        import_job.refresh_from_db()

        if import_job.status == 'completed':
            return Response({
                'message': 'File uploaded and processed successfully.',
                'import_job': ImportJobDetailSerializer(import_job).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'message': 'File processed with some errors.',
                'import_job': ImportJobDetailSerializer(import_job).data
            }, status=status.HTTP_201_CREATED)

    except Exception as e:
        import_job.status = 'failed'
        import_job.error_message = f'Processing error: {str(e)}'
        import_job.completed_at = timezone.now()
        import_job.save()
        return Response({'error': f'Failed to process file: {str(e)}'},
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_and_import_courses_data(request):
    """
    Upload and import courses data from Excel/CSV file.
    Validates program relationships.
    """
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    # Validate file upload
    serializer = FileUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    file = serializer.validated_data['file']
    import_type = serializer.validated_data['import_type']

    if import_type != 'courses':
        return Response({'error': 'This endpoint only accepts courses import type'},
                       status=status.HTTP_400_BAD_REQUEST)

    # Save file temporarily
    filename = f"import_{uuid.uuid4()}_{file.name}"
    file_path = os.path.join(settings.MEDIA_ROOT, 'imports', filename)

    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Save file
    with open(file_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Create import job
    import_job = ImportJob.objects.create(
        import_type=import_type,
        filename=file.name,
        uploaded_by=request.user,
        status='processing'
    )

    # Process file synchronously
    try:
        result = process_courses_import_sync(import_job.id, file_path)
        import_job.refresh_from_db()

        if import_job.status == 'completed':
            return Response({
                'message': 'File uploaded and processed successfully.',
                'import_job': ImportJobDetailSerializer(import_job).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'message': 'File processed with some errors.',
                'import_job': ImportJobDetailSerializer(import_job).data
            }, status=status.HTTP_201_CREATED)

    except Exception as e:
        import_job.status = 'failed'
        import_job.error_message = f'Processing error: {str(e)}'
        import_job.completed_at = timezone.now()
        import_job.save()
        return Response({'error': f'Failed to process file: {str(e)}'},
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_import_jobs(request):
    """Get list of import jobs for the current user"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    import_jobs = ImportJob.objects.filter(uploaded_by=request.user).order_by('-created_at')
    serializer = ImportJobSerializer(import_jobs, many=True)
    return Response({'import_jobs': serializer.data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_import_job_detail(request, job_id):
    """Get detailed information about a specific import job"""
    if not user_is_admin(request.user):
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    try:
        import_job = ImportJob.objects.get(id=job_id, uploaded_by=request.user)
        serializer = ImportJobDetailSerializer(import_job)
        return Response(serializer.data)
    except ImportJob.DoesNotExist:
        return Response({'error': 'Import job not found'}, status=status.HTTP_404_NOT_FOUND)


# Synchronous processing functions (moved from tasks.py)
def process_university_import_sync(import_job_id, file_path):
    """
    Process university, college, program import from Excel file synchronously
    """
    try:
        import_job = ImportJob.objects.get(id=import_job_id)
        import_job.status = 'processing'
        import_job.save()

        # Read file based on extension
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Normalize column names (case-insensitive, strip whitespace)
        df.columns = df.columns.str.strip().str.lower()

        # Validate required columns
        required_columns = ['university', 'college', 'program', 'duration']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            import_job.status = 'failed'
            import_job.error_message = f"Missing required columns: {', '.join(missing_columns)}"
            import_job.completed_at = timezone.now()
            import_job.save()
            return

        total_rows = len(df)
        import_job.total_rows = total_rows
        import_job.save()

        successful_imports = 0
        failed_imports = 0

        for row_num, row in df.iterrows():
            try:
                # Extract and clean data
                university_name = str(row['university']).strip()
                college_name = str(row['college']).strip()
                program_name = str(row['program']).strip()
                duration_str = str(row['duration']).strip()

                # Validate data
                if not university_name or not college_name or not program_name:
                    raise ValueError("University, college, and program names are required")

                try:
                    duration = int(duration_str)
                    if duration <= 0:
                        raise ValueError("Duration must be a positive integer")
                except (ValueError, TypeError):
                    raise ValueError("Duration must be a valid integer")

                # Process row by row
                process_university_row_sync(import_job, row_num + 2, university_name, college_name, program_name, duration)
                successful_imports += 1

            except Exception as e:
                failed_imports += 1
                ImportError.objects.create(
                    import_job=import_job,
                    row_number=row_num + 2,
                    error_type='validation_error',
                    field_name='multiple',
                    error_message=str(e),
                    original_data={
                        'university': university_name if 'university_name' in locals() else row.get('university'),
                        'college': college_name if 'college_name' in locals() else row.get('college'),
                        'program': program_name if 'program_name' in locals() else row.get('program'),
                        'duration': duration_str if 'duration_str' in locals() else row.get('duration'),
                    }
                )

            # Update progress
            import_job.processed_rows = row_num + 1
            import_job.save()

        # Final update
        import_job.processed_rows = total_rows
        import_job.successful_rows = successful_imports
        import_job.failed_rows = failed_imports
        import_job.completed_at = timezone.now()

        if failed_imports == 0:
            import_job.status = 'completed'
        elif successful_imports == 0:
            import_job.status = 'failed'
        else:
            import_job.status = 'partially_failed'

        import_job.save()

        # Clean up file
        try:
            os.remove(file_path)
        except OSError:
            pass

    except ImportJob.DoesNotExist:
        logger.error(f"Import job {import_job_id} not found")
    except Exception as e:
        logger.error(f"Error processing university import {import_job_id}: {str(e)}")
        try:
            import_job = ImportJob.objects.get(id=import_job_id)
            import_job.status = 'failed'
            import_job.error_message = f"Processing error: {str(e)}"
            import_job.completed_at = timezone.now()
            import_job.save()
        except ImportJob.DoesNotExist:
            pass


def process_university_row_sync(import_job, row_num, university_name, college_name, program_name, duration):
    """Process a single row of university data, creating missing dependencies"""
    # Find or create university
    university, created = University.objects.get_or_create(
        name=university_name,
        defaults={'country': 'Nigeria'}  # Default country, can be updated later
    )

    if created:
        logger.info(f"Created new university: {university_name}")

    # Find or create college
    college, created = College.objects.get_or_create(
        name=college_name,
        university=university
    )

    if created:
        logger.info(f"Created new college: {college_name} under {university_name}")

    # Find or create program
    program, created = Program.objects.get_or_create(
        name=program_name,
        college=college,
        defaults={'duration': duration}
    )

    if created:
        logger.info(f"Created new program: {program_name} under {college_name}")
    else:
        # Update duration if program exists but duration is different
        if program.duration != duration:
            program.duration = duration
            program.save()
            logger.info(f"Updated duration for program: {program_name}")


def process_courses_import_sync(import_job_id, file_path):
    """
    Process courses import from Excel file synchronously
    """
    try:
        import_job = ImportJob.objects.get(id=import_job_id)
        import_job.status = 'processing'
        import_job.save()

        # Read file based on extension
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()

        # Validate required columns
        required_columns = ['program', 'year', 'semester', 'name', 'code', 'is_elective', 'credit']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            import_job.status = 'failed'
            import_job.error_message = f"Missing required columns: {', '.join(missing_columns)}"
            import_job.completed_at = timezone.now()
            import_job.save()
            return

        total_rows = len(df)
        import_job.total_rows = total_rows
        import_job.save()

        successful_imports = 0
        failed_imports = 0

        for row_num, row in df.iterrows():
            try:
                # Extract and clean data
                program_name = str(row['program']).strip()
                year_str = str(row['year']).strip()
                semester_str = str(row['semester']).strip()
                course_name = str(row['name']).strip()
                course_code = str(row['code']).strip()
                is_elective_str = str(row['is_elective']).strip().lower()
                credit_str = str(row['credit']).strip()

                # Validate data
                if not all([program_name, year_str, semester_str, course_name, course_code, credit_str]):
                    raise ValueError("All fields are required")

                try:
                    year = int(year_str)
                    semester = int(semester_str)
                    credit = int(credit_str)

                    if year <= 0 or semester <= 0 or credit <= 0:
                        raise ValueError("Year, semester, and credit must be positive integers")

                    if semester not in [1, 2]:
                        raise ValueError("Semester must be 1 or 2")

                except (ValueError, TypeError):
                    raise ValueError("Year, semester, and credit must be valid integers")

                # Validate is_elective
                if is_elective_str in ['true', '1', 'yes']:
                    is_elective = 'elective'
                elif is_elective_str in ['false', '0', 'no']:
                    is_elective = 'core'
                else:
                    raise ValueError("is_elective must be true/false, 1/0, or yes/no")

                # Process row
                process_course_row_sync(import_job, row_num + 2, program_name, year, semester,
                                 course_name, course_code, is_elective, credit)
                successful_imports += 1

            except Exception as e:
                failed_imports += 1
                ImportError.objects.create(
                    import_job=import_job,
                    row_number=row_num + 2,
                    error_type='validation_error',
                    field_name='multiple',
                    error_message=str(e),
                    original_data={
                        'program': program_name if 'program_name' in locals() else row.get('program'),
                        'year': year_str if 'year_str' in locals() else row.get('year'),
                        'semester': semester_str if 'semester_str' in locals() else row.get('semester'),
                        'name': course_name if 'course_name' in locals() else row.get('name'),
                        'code': course_code if 'course_code' in locals() else row.get('code'),
                        'is_elective': is_elective_str if 'is_elective_str' in locals() else row.get('is_elective'),
                        'credit': credit_str if 'credit_str' in locals() else row.get('credit'),
                    }
                )

            # Update progress
            import_job.processed_rows = row_num + 1
            import_job.save()

        # Final update
        import_job.processed_rows = total_rows
        import_job.successful_rows = successful_imports
        import_job.failed_rows = failed_imports
        import_job.completed_at = timezone.now()

        if failed_imports == 0:
            import_job.status = 'completed'
        elif successful_imports == 0:
            import_job.status = 'failed'
        else:
            import_job.status = 'partially_failed'

        import_job.save()

        # Clean up file
        try:
            os.remove(file_path)
        except OSError:
            pass

    except ImportJob.DoesNotExist:
        logger.error(f"Import job {import_job_id} not found")
    except Exception as e:
        logger.error(f"Error processing courses import {import_job_id}: {str(e)}")
        try:
            import_job = ImportJob.objects.get(id=import_job_id)
            import_job.status = 'failed'
            import_job.error_message = f"Processing error: {str(e)}"
            import_job.completed_at = timezone.now()
            import_job.save()
        except ImportJob.DoesNotExist:
            pass


def process_course_row_sync(import_job, row_num, program_name, year, semester, course_name, course_code, course_type, credits):
    """Process a single row of course data, validating program exists"""
    # Find program
    try:
        program = Program.objects.get(name=program_name)
    except Program.DoesNotExist:
        raise ValueError(f"Program '{program_name}' not found. Please import programs first.")

    # Check if course already exists
    existing_course = Course.objects.filter(
        code=course_code,
        program=program
    ).first()

    if existing_course:
        # Update existing course
        existing_course.name = course_name
        existing_course.type = course_type
        existing_course.credits = credits
        existing_course.semester = semester
        existing_course.year = year
        existing_course.save()
        logger.info(f"Updated existing course: {course_code}")
    else:
        # Create new course
        Course.objects.create(
            code=course_code,
            name=course_name,
            credits=credits,
            type=course_type,
            semester=semester,
            year=year,
            program=program
        )
        logger.info(f"Created new course: {course_code}")
