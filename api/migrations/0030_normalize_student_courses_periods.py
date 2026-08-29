# Data migration: normalize every StudentCourse.courses into the canonical
# {"_v": 2, "periods": {"1_1": [...]}} shape. Legacy flat arrays are grouped
# by (year, semester) into periods. No data is dropped.
from django.db import migrations

PERIODS_VERSION = 2


def _course_dict(d):
    if not isinstance(d, dict):
        return None
    cid = d.get('id') or d.get('course_id') or None
    if not cid:
        import uuid
        cid = str(uuid.uuid4())
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


def period_key(year, semester):
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = 1
    try:
        semester = int(semester)
    except (TypeError, ValueError):
        semester = 1
    return f"{year}_{semester}"


def forward(apps, schema_editor):
    StudentCourse = apps.get_model('api', 'StudentCourse')

    for sc in StudentCourse.objects.all():
        sc_id = sc.id
        raw = sc.courses

        if isinstance(raw, dict) and isinstance(raw.get('periods'), dict):
            # Already in periods shape; clean and version it.
            periods = {}
            for key, items in raw['periods'].items():
                if not isinstance(items, list):
                    continue
                cleaned = []
                for d in items:
                    cd = _course_dict(d)
                    if cd:
                        parts = str(key).split('_')
                        year = parts[0] if parts else None
                        sem = parts[1] if len(parts) > 1 else None
                        try:
                            cd['year'] = int(year) if year != '' else None
                        except (TypeError, ValueError):
                            cd['year'] = None
                        try:
                            cd['semester'] = int(sem) if (sem != '' and sem is not None) else None
                        except (TypeError, ValueError):
                            cd['semester'] = None
                        cleaned.append(cd)
                periods[str(key)] = cleaned
            new_value = {'_v': PERIODS_VERSION, 'periods': periods}
        elif isinstance(raw, list):
            # Legacy flat list: group by (year, semester).
            periods = {}
            for d in raw:
                cd = _course_dict(d)
                if not cd:
                    continue
                year = cd.get('year')
                semester = cd.get('semester')
                if year is None or semester is None:
                    year = sc.student.year if sc.student_id else 1
                    semester = sc.student.semester if sc.student_id else 1
                try:
                    year = int(year)
                except (TypeError, ValueError):
                    year = sc.student.year if sc.student_id else 1
                try:
                    semester = int(semester)
                except (TypeError, ValueError):
                    semester = sc.student.semester if sc.student_id else 1
                cd['year'] = year
                cd['semester'] = semester
                periods.setdefault(period_key(year, semester), []).append(cd)
            new_value = {'_v': PERIODS_VERSION, 'periods': periods}
        else:
            new_value = {'_v': PERIODS_VERSION, 'periods': {}}

        if new_value != raw:
            StudentCourse.objects.filter(pk=sc_id).update(courses=new_value)


def backward(apps, schema_editor):
    # Intentionally not reversible; this is purely a normalization.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_articlecomment'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
