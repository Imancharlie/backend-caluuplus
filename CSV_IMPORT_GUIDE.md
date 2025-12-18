# CSV Import Script Guide

This guide explains how to use the CSV import script to import university, college, and program data into the database.

## CSV File Format

Your CSV file must have the following headers (case-insensitive):
- `university` - Name of the university
- `college` - Name of the college/school within the university
- `program` - Name of the academic program
- `duration` - Duration of the program in years (must be a positive integer)

### Example CSV File:
```csv
university,college,program,duration
University of Dar es Salaam,College of Engineering and Technology,Bachelor of Science in Computer Engineering,4
University of Dar es Salaam,College of Engineering and Technology,Bachelor of Science in Electrical Engineering,4
University of Dar es Salaam,College of Information and Communication Technologies,Bachelor of Science in Computer Science,3
Muhimbili University of Health and Allied Sciences,School of Medicine,Doctor of Medicine,5
```

## Usage

### Basic Import
```bash
python manage.py import_csv_data --csv-file your_file.csv
```

### Import with Custom Country
```bash
python manage.py import_csv_data --csv-file your_file.csv --university-country "Kenya"
```

### Dry Run (Preview without importing)
```bash
python manage.py import_csv_data --csv-file your_file.csv --dry-run
```

### Custom CSV Delimiter
```bash
python manage.py import_csv_data --csv-file your_file.csv --delimiter ";"
```

### Skip Header Row (if your CSV doesn't have headers)
```bash
python manage.py import_csv_data --csv-file your_file.csv --skip-header
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--csv-file` | Path to CSV file (required) | - |
| `--university-country` | Default country for universities | "Tanzania" |
| `--skip-header` | Skip first row as header | True |
| `--dry-run` | Show preview without importing | False |
| `--delimiter` | CSV delimiter character | "," |

## Features

- **Smart Relationship Handling**: Automatically creates universities, colleges, and programs while maintaining proper relationships
- **Duplicate Prevention**: Uses `get_or_create` to avoid duplicate entries
- **Duration Updates**: Updates program duration if it changes
- **Error Handling**: Comprehensive error reporting and validation
- **Dry Run Mode**: Preview what will be imported before actually importing
- **Flexible CSV Parsing**: Handles various CSV formats and delimiters

## Example Output

### Dry Run Output:
```
[INFO] Reading CSV file: sample_university_data.csv
[INFO] Default country: Tanzania
[INFO] Skip header: True
[INFO] Dry run: True
--------------------------------------------------
[SUCCESS] CSV structure validated. Found 19 data rows

[DRY RUN] No data will be imported
==================================================
Preview of data to be imported:
--------------------------------------------------------------------------------

1. University: 'University of Dar es Salaam'
   College: 'College of Engineering and Technology'
   Program: 'Bachelor of Science in Electrical Engineering'
   Duration: 4 years

... and 14 more rows

[ANALYSIS] Analysis:
  • Unique universities: 4
  • Unique colleges: 12
  • Unique programs: 19
  • Total relationships: 19
```

### Import Output:
```
[INFO] Reading CSV file: sample_university_data.csv
[INFO] Default country: Tanzania
[INFO] Skip header: True
[INFO] Dry run: False
--------------------------------------------------
[SUCCESS] CSV structure validated. Found 19 data rows

[IMPORT] Starting import...
==================================================
  [CREATED] University: Muhimbili University of Health and Allied Sciences
    [CREATED] College: School of Medicine
      [CREATED] Program: Doctor of Medicine (5 years)
    [CREATED] College: School of Pharmacy
      [CREATED] Program: Bachelor of Pharmacy (4 years)

==================================================
IMPORT COMPLETED
==================================================
[STATS] Import Statistics:
  • Universities created: 3
  • Universities found: 16
  • Colleges created: 12
  • Colleges found: 7
  • Programs created: 19
  • Programs found: 0
  • Total rows processed: 19
  • Errors: 0

[SUCCESS] Import completed successfully with no errors!
```

## Error Handling

The script validates:
- CSV file existence and readability
- Required column presence
- Data completeness (no empty required fields)
- Duration values (must be positive integers)
- Proper relationships between entities

If errors occur, they will be displayed with details about which rows failed and why.

## Database Models

The script imports data into these models:
- **University**: `name`, `country`
- **College**: `name`, linked to `University`
- **Program**: `name`, `duration` (in years), linked to `College`

## Tips

1. **Test with Dry Run**: Always run `--dry-run` first to verify your data
2. **Consistent Naming**: Use consistent university and college names for better relationship handling
3. **Duration Format**: Ensure duration is a positive integer (1, 2, 3, 4, 5, etc.)
4. **Encoding**: Save your CSV file as UTF-8 for best compatibility
5. **Headers**: Make sure your CSV has the exact column headers specified above

## Troubleshooting

**"CSV file missing required columns"**
- Check that your CSV has the exact headers: university, college, program, duration
- Headers are case-insensitive but must match exactly

**"Invalid duration" errors**
- Ensure duration values are positive integers
- Check for empty or non-numeric values in the duration column

**"Unicode encoding issues"**
- Save your CSV file as UTF-8 encoded
- Avoid special characters that might cause encoding issues

**Import creates duplicates**
- The script uses `get_or_create` which should prevent duplicates
- If you see duplicates, check for slight variations in naming (extra spaces, capitalization)








