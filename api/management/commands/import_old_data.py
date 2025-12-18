from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from api.models import University, College, Program, Course
import json
import os
import decimal


class Command(BaseCommand):
    help = 'Import legacy data from old-dat.json and upsert into University, College, Program, and Course tables.'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='old-dat.json', help='Path to old-dat.json file')
        parser.add_argument('--university', type=str, default='University of Dar es Salaam', help='University name to import')
        parser.add_argument('--country', type=str, default='Tanzania', help='Country for the university record if created')

    def handle(self, *args, **options):
        path = options['path']
        university_name = options['university']
        country = options['country']

        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            try:
                payload = json.load(f)
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid JSON in {path}: {exc}")

        # Expected generic structure in legacy file (flexible):
        # {
        #   "universities": [ {"name": ..., "country": ..., "colleges": [...] }, ... ]
        # }
        # or flat lists: { "colleges": [...], "programs": [...], "courses": [...] }

        # Normalize lists (support both dict and list roots)
        universities = []
        colleges = []
        programs = []
        courses = []
        udsm_course_items = []  # previous project's export shape

        if isinstance(payload, dict):
            universities = payload.get('universities') or []
            colleges = payload.get('colleges') or []
            programs = payload.get('programs') or []
            courses = payload.get('courses') or []
        elif isinstance(payload, list):
            # Detect Django dumpdata format: list of {model, pk, fields}
            is_dumpdata = all(isinstance(x, dict) and 'model' in x and 'fields' in x for x in payload) if payload else False
            if is_dumpdata:
                # First, collect legacy objects by model
                legacy_colleges = {}
                legacy_programs = {}
                legacy_academic_years = {}
                legacy_courses = []

                for item in payload:
                    model_name = item.get('model') or ''
                    fields = item.get('fields') or {}
                    pk = item.get('pk')
                    if 'college' in model_name:
                        # e.g., {name: "CoET"}
                        legacy_colleges[pk] = (fields.get('name') or '').strip()
                    elif 'program' in model_name and 'academic' not in model_name:
                        legacy_programs[pk] = {
                            'name': (fields.get('name') or '').strip(),
                            'college_pk': fields.get('college'),
                            'duration': fields.get('duration') or fields.get('years') or 4,
                        }
                    elif 'academicyear' in model_name or ('academic' in model_name and 'year' in model_name):
                        legacy_academic_years[pk] = {
                            'program_pk': fields.get('program'),
                            'year': fields.get('year') or fields.get('level') or 1,
                        }
                    elif 'course' in model_name:
                        legacy_courses.append({
                            'academic_year_pk': fields.get('academic_year'),
                            'code': (fields.get('code') or '').strip(),
                            'name': (fields.get('name') or '').strip(),
                            'credit_hours': fields.get('credit_hours') or fields.get('credits') or fields.get('units'),
                            'semester': fields.get('semester') or fields.get('sem') or 1,
                            'optional': fields.get('optional') or fields.get('elective') or False,
                        })

                # Build flat colleges list
                colleges = [{'name': cname} for cname in legacy_colleges.values() if cname]

                # Build flat programs list with resolved college names
                programs = []
                for p in legacy_programs.values():
                    college_name = legacy_colleges.get(p.get('college_pk'))
                    programs.append({
                        'name': p.get('name'),
                        'college': college_name,
                        'duration': p.get('duration') or 4,
                    })

                # Build flat courses list by resolving through academic_year → program → college
                courses = []
                for c in legacy_courses:
                    ay = legacy_academic_years.get(c.get('academic_year_pk')) or {}
                    prog = legacy_programs.get(ay.get('program_pk')) or {}
                    college_name = legacy_colleges.get(prog.get('college_pk'))
                    # Normalize credits and semester to ints
                    ch_val = c.get('credit_hours') or 3
                    try:
                        credits_int = int(decimal.Decimal(str(ch_val)))
                    except Exception:
                        credits_int = 3
                    sem_raw = c.get('semester')
                    if isinstance(sem_raw, str):
                        digits = ''.join([ch for ch in sem_raw if ch.isdigit()])
                        semester_int = int(digits) if digits else 1
                    else:
                        try:
                            semester_int = int(sem_raw)
                        except Exception:
                            semester_int = 1
                    try:
                        year_int = int(ay.get('year') or 1)
                    except Exception:
                        year_int = 1
                    courses.append({
                        'program_name': prog.get('name') or '',
                        'college_name': college_name or '',
                        'code': c.get('code') or '',
                        'name': c.get('name') or '',
                        'credits': credits_int,
                        'semester': semester_int,
                        'year': year_int,
                        'type': 'elective' if bool(c.get('optional')) else 'core',
                    })
            else:
                sample = payload[0] if payload else {}
                sample_keys = set(sample.keys()) if isinstance(sample, dict) else set()
                # Detect UDSM course export (previous project) by presence of academic_year or credit_hours
                if 'academic_year' in sample_keys or 'credit_hours' in sample_keys:
                    udsm_course_items = payload
                elif {'code', 'name'} & sample_keys or {'course_code'} & sample_keys:
                    courses = payload
                elif {'duration'} & sample_keys or {'program', 'program_name'} & sample_keys:
                    programs = payload
                elif {'university', 'university_name'} & sample_keys or 'programs' in sample_keys or 'college' in sample_keys or 'college_name' in sample_keys:
                    colleges = payload
                else:
                    universities = payload

        # If nested under universities, merge down for the target university only
        if universities:
            # Filter to the requested university by case-insensitive match
            target_unis = [u for u in universities if str(u.get('name', '')).strip().lower() == university_name.strip().lower()]
            if not target_unis:
                self.stdout.write(self.style.WARNING(f"No university named '{university_name}' found in file; creating it and importing any global colleges/programs/courses."))
                target_uni_block = {}
            else:
                target_uni_block = target_unis[0]

            # If nested blocks exist, append to flat lists
            colleges = target_uni_block.get('colleges') or colleges
            # programs nested under colleges or directly under university
            programs = target_uni_block.get('programs') or programs
            courses = target_uni_block.get('courses') or courses

            # Also gather programs/courses from each college if provided
            nested_programs = []
            nested_courses = []
            for c in colleges or []:
                nested_programs.extend(c.get('programs') or [])
                for p in c.get('programs') or []:
                    nested_courses.extend(p.get('courses') or [])
            # Prefer explicit lists if present, else use nested aggregate
            if not programs:
                programs = nested_programs
            if not courses:
                courses = nested_courses

        with transaction.atomic():
            # Upsert University
            university, _ = University.objects.get_or_create(
                name=university_name,
                defaults={"country": country},
            )

            # Build quick indexes by normalized names to map relationships
            def norm(value):
                if value is None:
                    return ''
                return slugify(str(value))

            # Helper: infer college from program name using UDSM patterns
            def infer_college_from_program(program_name: str) -> str:
                if not program_name:
                    return 'College of Science and Technology'
                patterns = {
                    'COET': 'College of Engineering and Technology',
                    'COICT': 'College of Information and Communication Technologies',
                    'COBASS': 'College of Business and Social Sciences',
                    'COHAS': 'College of Health and Allied Sciences',
                    'COST': 'College of Science and Technology',
                    'COA': 'College of Agriculture',
                    'COED': 'College of Education',
                    'COMREC': 'College of Natural and Applied Sciences',
                }
                upper = program_name.upper()
                for code, college_name in patterns.items():
                    if code in upper:
                        return college_name
                words = program_name.split()
                if len(words) >= 3:
                    for i in range(len(words)):
                        if words[i].lower() in ['in', 'of'] and i + 1 < len(words):
                            subject = ' '.join(words[i+1:])
                            subj = subject.lower()
                            if 'engineering' in subj:
                                return 'College of Engineering and Technology'
                            if 'science' in subj:
                                return 'College of Science and Technology'
                            if 'business' in subj:
                                return 'College of Business and Social Sciences'
                            if 'education' in subj:
                                return 'College of Education'
                            if 'agriculture' in subj:
                                return 'College of Agriculture'
                            if 'health' in subj:
                                return 'College of Health and Allied Sciences'
                return 'College of Science and Technology'

            # Upsert Colleges
            name_to_college = {}
            for c in colleges:
                name = (c.get('name') or '').strip()
                if not name:
                    continue
                college, _ = College.objects.get_or_create(
                    university=university,
                    name=name,
                    defaults={},
                )
                name_to_college[norm(name)] = college

            # Upsert Programs
            program_key_to_program = {}
            for p in programs:
                program_name = (p.get('name') or '').strip()
                if not program_name:
                    continue

                # Determine college for program
                college_name = (p.get('college') or p.get('college_name') or p.get('faculty') or '').strip()
                college = None
                if college_name:
                    college = name_to_college.get(norm(college_name))
                    if college is None:
                        college, _ = College.objects.get_or_create(
                            university=university,
                            name=college_name,
                            defaults={},
                        )
                        name_to_college[norm(college_name)] = college
                else:
                    # Fallback: if only one college exists, attach to it
                    if len(name_to_college) == 1:
                        college = list(name_to_college.values())[0]
                    else:
                        # Skip program without resolvable college
                        self.stdout.write(self.style.WARNING(f"Skipped program without college: {program_name}"))
                        continue

                duration = p.get('duration') or p.get('years') or 4
                program, _ = Program.objects.get_or_create(
                    college=college,
                    name=program_name,
                    defaults={"duration": int(duration)},
                )
                # Update duration if changed
                if program.duration != int(duration):
                    program.duration = int(duration)
                    program.save(update_fields=['duration'])

                program_key_to_program[(norm(college.name), norm(program_name))] = program

            # Upsert Courses (flat course lists with explicit mapping)
            created_courses = 0
            updated_courses = 0
            skipped_courses = 0
            for c in courses:
                code = (c.get('code') or c.get('course_code') or '').strip()
                name = (c.get('name') or c.get('title') or '').strip()
                if not code or not name:
                    skipped_courses += 1
                    continue

                # Map to program via fields available
                program_name = (c.get('program') or c.get('program_name') or '').strip()
                college_name = (c.get('college') or c.get('college_name') or '').strip()

                program = None
                key = None
                if college_name and program_name:
                    key = (norm(college_name), norm(program_name))
                    program = program_key_to_program.get(key)
                if program is None and program_name:
                    # Try any program with matching name (if unique under the university)
                    candidates = [p for k, p in program_key_to_program.items() if k[1] == norm(program_name)]
                    if len(candidates) == 1:
                        program = candidates[0]
                if program is None:
                    skipped_courses += 1
                    continue

                credits = c.get('credits') or c.get('credit') or c.get('units') or 3
                course_type = (c.get('type') or c.get('category') or 'core').lower()
                if course_type not in {'core', 'elective'}:
                    course_type = 'core'
                semester = int(c.get('semester') or c.get('sem') or 1)
                year = int(c.get('year') or c.get('level') or 1)

                obj, created = Course.objects.get_or_create(
                    program=program,
                    code=code,
                    defaults={
                        'name': name,
                        'credits': int(credits),
                        'type': course_type,
                        'semester': semester,
                        'year': year,
                    }
                )
                if created:
                    created_courses += 1
                else:
                    # Update only if fields changed
                    changed = False
                    if obj.name != name:
                        obj.name = name
                        changed = True
                    if obj.credits != int(credits):
                        obj.credits = int(credits)
                        changed = True
                    if obj.type != course_type:
                        obj.type = course_type
                        changed = True
                    if obj.semester != semester:
                        obj.semester = semester
                        changed = True
                    if obj.year != year:
                        obj.year = year
                        changed = True
                    if changed:
                        obj.save()
                        updated_courses += 1

            # Upsert from UDSM-style course export (list of course records with academic_year and program)
            if udsm_course_items:
                # Group by (program_name, year)
                grouped = {}
                for item in udsm_course_items:
                    prog_name = ''
                    yr = None
                    ay = item.get('academic_year')
                    if isinstance(ay, dict):
                        # academic_year may have nested program
                        prog = ay.get('program')
                        if isinstance(prog, dict):
                            prog_name = (prog.get('name') or '').strip()
                        else:
                            prog_name = str(prog or '').strip()
                        yr = ay.get('year') or ay.get('level') or item.get('year')
                    else:
                        prog_name = (item.get('program_name') or item.get('program') or '').strip()
                        yr = item.get('year') or item.get('level')
                    try:
                        yr_int = int(str(yr)[-1]) if isinstance(yr, str) else int(yr)
                    except Exception:
                        yr_int = 1
                    key = (prog_name, yr_int)
                    grouped.setdefault(key, []).append(item)

                for (program_name, year_val), items in grouped.items():
                    if not program_name:
                        continue
                    college_name = infer_college_from_program(program_name)
                    college = name_to_college.get(norm(college_name))
                    if college is None:
                        college, _ = College.objects.get_or_create(
                            university=university,
                            name=college_name,
                            defaults={},
                        )
                        name_to_college[norm(college_name)] = college

                    program, _ = Program.objects.get_or_create(
                        college=college,
                        name=program_name,
                        defaults={"duration": 4},
                    )

                    for item in items:
                        code = (item.get('code') or item.get('course_code') or '').strip()
                        title = (item.get('name') or item.get('title') or '').strip()
                        if not code or not title:
                            skipped_courses += 1
                            continue
                        # credits from credit_hours/units
                        ch = item.get('credit_hours') or item.get('credits') or item.get('units') or 3
                        try:
                            credits_int = int(decimal.Decimal(str(ch)))
                        except Exception:
                            credits_int = 3
                        sem_raw = item.get('semester') or item.get('sem') or 1
                        if isinstance(sem_raw, str):
                            sem = ''.join([ch for ch in sem_raw if ch.isdigit()])
                            semester_val = int(sem) if sem else 1
                        else:
                            semester_val = int(sem_raw)
                        course_type = (item.get('type') or item.get('category') or 'core').lower()
                        if course_type not in {'core', 'elective'}:
                            course_type = 'core'

                        obj, created = Course.objects.get_or_create(
                            program=program,
                            code=code,
                            defaults={
                                'name': title,
                                'credits': credits_int,
                                'type': course_type,
                                'semester': semester_val,
                                'year': int(year_val),
                            }
                        )
                        if created:
                            created_courses += 1
                        else:
                            changed = False
                            if obj.name != title:
                                obj.name = title
                                changed = True
                            if obj.credits != credits_int:
                                obj.credits = credits_int
                                changed = True
                            if obj.type != course_type:
                                obj.type = course_type
                                changed = True
                            if obj.semester != semester_val:
                                obj.semester = semester_val
                                changed = True
                            if obj.year != int(year_val):
                                obj.year = int(year_val)
                                changed = True
                            if changed:
                                obj.save()
                                updated_courses += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported data for '{university_name}'. Courses: +{created_courses} created, {updated_courses} updated, {skipped_courses} skipped."
        ))


