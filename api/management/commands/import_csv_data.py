import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from api.models import University, College, Program


class Command(BaseCommand):
    help = 'Import university, college, and program data from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('--csv-file', type=str, required=True, help='Path to CSV file to import')
        parser.add_argument('--university-country', type=str, default='Tanzania', help='Default country for universities')
        parser.add_argument('--skip-header', action='store_true', default=True, help='Skip first row (header row)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without actually importing')
        parser.add_argument('--delimiter', type=str, default=',', help='CSV delimiter character')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        country = options['university_country']
        skip_header = options['skip_header']
        dry_run = options['dry_run']
        delimiter = options['delimiter']

        # Validate CSV file exists
        if not os.path.exists(csv_file):
            raise CommandError(f"CSV file not found: {csv_file}")

        # Check if file is readable
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # Test read first few lines
                sample = f.read(1024)
                if not sample.strip():
                    raise CommandError(f"CSV file appears to be empty: {csv_file}")
        except UnicodeDecodeError:
            raise CommandError(f"CSV file encoding issue. Try saving the file as UTF-8: {csv_file}")
        except Exception as e:
            raise CommandError(f"Error reading CSV file: {e}")

        self.stdout.write(f"[INFO] Reading CSV file: {csv_file}")
        self.stdout.write(f"[INFO] Default country: {country}")
        self.stdout.write(f"[INFO] Skip header: {skip_header}")
        self.stdout.write(f"[INFO] Dry run: {dry_run}")
        self.stdout.write("-" * 50)

        # Parse CSV and validate structure
        rows = self.parse_csv_file(csv_file, delimiter, skip_header)

        if not rows:
            raise CommandError("No valid data rows found in CSV file")

        # Validate CSV structure
        required_columns = {'university', 'college', 'program', 'duration'}
        sample_row = rows[0]
        csv_columns = set(sample_row.keys())

        missing_columns = required_columns - csv_columns
        if missing_columns:
            raise CommandError(
                f"CSV file missing required columns: {missing_columns}. "
                f"Found columns: {sorted(csv_columns)}"
            )

        extra_columns = csv_columns - required_columns
        if extra_columns:
            self.stdout.write(
                self.style.WARNING(f"[WARNING] Extra columns found (will be ignored): {sorted(extra_columns)}")
            )

        self.stdout.write(f"[SUCCESS] CSV structure validated. Found {len(rows)} data rows")

        if dry_run:
            self.stdout.write("\n[DRY RUN] No data will be imported")
            self.stdout.write("=" * 50)
            self.perform_dry_run(rows)
            return

        # Perform actual import
        self.stdout.write("\n[IMPORT] Starting import...")
        self.stdout.write("=" * 50)

        stats = self.import_data(rows, country)

        # Display results
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("IMPORT COMPLETED")
        self.stdout.write("=" * 50)
        self.stdout.write(f"[STATS] Import Statistics:")
        self.stdout.write(f"  • Universities created: {stats['universities_created']}")
        self.stdout.write(f"  • Universities found: {stats['universities_found']}")
        self.stdout.write(f"  • Colleges created: {stats['colleges_created']}")
        self.stdout.write(f"  • Colleges found: {stats['colleges_found']}")
        self.stdout.write(f"  • Programs created: {stats['programs_created']}")
        self.stdout.write(f"  • Programs found: {stats['programs_found']}")
        self.stdout.write(f"  • Total rows processed: {stats['rows_processed']}")
        self.stdout.write(f"  • Errors: {stats['errors']}")

        if stats['errors'] > 0:
            self.stdout.write(self.style.WARNING(f"\n[WARNING] {stats['errors']} errors occurred during import"))
            if stats['error_details']:
                self.stdout.write("\nError Details:")
                for error in stats['error_details'][:10]:  # Show first 10 errors
                    self.stdout.write(f"  • {error}")
                if len(stats['error_details']) > 10:
                    self.stdout.write(f"  • ... and {len(stats['error_details']) - 10} more errors")
        else:
            self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Import completed successfully with no errors!"))

    def parse_csv_file(self, csv_file, delimiter, skip_header):
        """Parse CSV file and return list of row dictionaries"""
        rows = []

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)

                for row_num, row in enumerate(reader, 1):
                    # Skip header if requested
                    if skip_header and row_num == 1:
                        continue

                    # Clean up row data
                    clean_row = {}
                    for key, value in row.items():
                        if key is None:  # Skip None keys from CSV
                            continue
                        clean_key = key.strip().lower()
                        clean_value = value.strip() if value else ''
                        clean_row[clean_key] = clean_value

                    # Validate required fields are not empty
                    if not clean_row.get('university') or not clean_row.get('college') or \
                       not clean_row.get('program') or not clean_row.get('duration'):
                        self.stdout.write(
                            self.style.WARNING(f"[WARNING] Skipping row {row_num}: missing required data")
                        )
                        continue

                    rows.append(clean_row)

        except csv.Error as e:
            raise CommandError(f"CSV parsing error: {e}")
        except Exception as e:
            raise CommandError(f"Error reading CSV file: {e}")

        return rows

    def perform_dry_run(self, rows):
        """Show what would be imported without actually importing"""
        self.stdout.write("Preview of data to be imported:")
        self.stdout.write("-" * 80)

        # Show first 5 rows
        for i, row in enumerate(rows[:5], 1):
            self.stdout.write(f"\n{i}. University: '{row['university']}'")
            self.stdout.write(f"   College: '{row['college']}'")
            self.stdout.write(f"   Program: '{row['program']}'")
            self.stdout.write(f"   Duration: {row['duration']} years")

        if len(rows) > 5:
            self.stdout.write(f"\n... and {len(rows) - 5} more rows")

        # Analyze what would be created vs found
        university_names = set(row['university'] for row in rows)
        college_names = set(row['college'] for row in rows)
        program_names = set(row['program'] for row in rows)

        self.stdout.write("\n[ANALYSIS] Analysis:")
        self.stdout.write(f"  • Unique universities: {len(university_names)}")
        self.stdout.write(f"  • Unique colleges: {len(college_names)}")
        self.stdout.write(f"  • Unique programs: {len(program_names)}")
        self.stdout.write(f"  • Total relationships: {len(rows)}")

    def import_data(self, rows, country):
        """Import the data into the database"""
        stats = {
            'universities_created': 0,
            'universities_found': 0,
            'colleges_created': 0,
            'colleges_found': 0,
            'programs_created': 0,
            'programs_found': 0,
            'rows_processed': 0,
            'errors': 0,
            'error_details': []
        }

        # Create lookup maps for existing records
        university_map = {u.name.lower(): u for u in University.objects.all()}
        college_map = {(c.university.name.lower(), c.name.lower()): c for c in College.objects.all()}
        program_map = {(p.college.name.lower(), p.name.lower()): p for p in Program.objects.all()}

        with transaction.atomic():
            for row_num, row in enumerate(rows, 1):
                try:
                    university_name = row['university'].strip()
                    college_name = row['college'].strip()
                    program_name = row['program'].strip()

                    # Parse duration
                    try:
                        duration = int(row['duration'])
                        if duration <= 0:
                            raise ValueError("Duration must be positive")
                    except (ValueError, TypeError):
                        stats['errors'] += 1
                        stats['error_details'].append(
                            f"Row {row_num}: Invalid duration '{row['duration']}'"
                        )
                        continue

                    # Get or create university
                    university_key = university_name.lower()
                    if university_key not in university_map:
                        university = University.objects.create(
                            name=university_name,
                            country=country
                        )
                        university_map[university_key] = university
                        stats['universities_created'] += 1
                        self.stdout.write(f"  [CREATED] University: {university_name}")
                    else:
                        university = university_map[university_key]
                        stats['universities_found'] += 1

                    # Get or create college
                    college_key = (university.name.lower(), college_name.lower())
                    if college_key not in college_map:
                        college = College.objects.create(
                            name=college_name,
                            university=university
                        )
                        college_map[college_key] = college
                        stats['colleges_created'] += 1
                        self.stdout.write(f"    [CREATED] College: {college_name}")
                    else:
                        college = college_map[college_key]
                        stats['colleges_found'] += 1

                    # Get or create program
                    program_key = (college.name.lower(), program_name.lower())
                    if program_key not in program_map:
                        program = Program.objects.create(
                            name=program_name,
                            college=college,
                            duration=duration
                        )
                        program_map[program_key] = program
                        stats['programs_created'] += 1
                        self.stdout.write(f"      [CREATED] Program: {program_name} ({duration} years)")
                    else:
                        program = program_map[program_key]
                        # Update duration if different
                        if program.duration != duration:
                            program.duration = duration
                            program.save(update_fields=['duration'])
                            self.stdout.write(f"      [UPDATED] Program: {program_name} duration to {duration} years")
                        else:
                            stats['programs_found'] += 1

                    stats['rows_processed'] += 1

                except Exception as e:
                    stats['errors'] += 1
                    stats['error_details'].append(f"Row {row_num}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f"[ERROR] Error in row {row_num}: {e}")
                    )

        return stats
