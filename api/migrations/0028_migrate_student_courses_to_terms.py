# Data migration: move legacy flat StudentCourse JSON into per-term rows.
from django.db import migrations


def _to_code(d):
    return (d.get('code') or d.get('course_code') or '').strip()


def _to_name(d):
    return (d.get('name') or d.get('course_name') or '').strip()


def _to_credits(d):
    try:
        return int(d.get('credits') or d.get('credit_hour') or 0)
    except (TypeError, ValueError):
        return 0


def _to_type(d):
    t = (d.get('type') or '').strip().lower()
    if t in ('elective', 'optional'):
        return 'elective'
    return 'core'


def forward(apps, schema_editor):
    Student = apps.get_model('api', 'Student')
    StudentCourse = apps.get_model('api', 'StudentCourse')
    StudentTerm = apps.get_model('api', 'StudentTerm')
    Enrollment = apps.get_model('api', 'StudentCourseEnrollment')
    Course = apps.get_model('api', 'Course')

    for sc in StudentCourse.objects.select_related('student').all():
        student = sc.student
        # Build a master-course lookup by code for this student's program.
        master_by_code = {}
        if student.program_id:
            for c in Course.objects.filter(program_id=student.program_id):
                master_by_code.setdefault(c.code.strip().upper().replace(' ', ''), c)

        # Normalize the stored JSON into (dict, year, semester) triples.
        triples = []
        raw = sc.courses
        if isinstance(raw, dict) and isinstance(raw.get('periods'), dict):
            for key, items in raw['periods'].items():
                key_y, key_s = None, None
                try:
                    key_y_s = str(key).split('_')
                    key_y = int(key_y_s[0]) if key_y_s else None
                    key_s = int(key_y_s[1]) if len(key_y_s) > 1 else None
                except (TypeError, ValueError, IndexError):
                    pass
                for d in items or []:
                    if not isinstance(d, dict):
                        continue
                    triples.append((d, d.get('year', key_y), d.get('semester', key_s)))
        elif isinstance(raw, list):
            for d in raw:
                if isinstance(d, dict):
                    triples.append((d, d.get('year'), d.get('semester')))

        by_term = {}
        for d, y, s in triples:
            if y is None:
                y = student.year
            if s is None:
                s = student.semester
            try:
                y = int(y)
            except (TypeError, ValueError):
                y = student.year
            try:
                s = int(s)
            except (TypeError, ValueError):
                s = student.semester
            by_term.setdefault((y, s), []).append(d)

        for (year, semester), items in by_term.items():
            term, _ = StudentTerm.objects.get_or_create(
                student=student, academic_year=year, semester=semester)
            for d in items:
                code = _to_code(d)
                if not code:
                    continue
                name = _to_name(d)
                credits = _to_credits(d)
                ctype = _to_type(d)
                course = master_by_code.get(code.strip().upper().replace(' ', ''))
                defaults = {
                    'name': name,
                    'credits': credits,
                    'type': ctype,
                    'course': course,
                }
                Enrollment.objects.get_or_create(term=term, code=code, defaults=defaults)


def backward(apps, schema_editor):
    # Intentionally not reversible data-wise; schema migration handles rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_university_grade_scheme_and_more'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
