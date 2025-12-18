#!/usr/bin/env python
"""
Debug script to check timetable data
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from api.models import TimetableSlot, Student

def debug_timetable():
    print("🔍 Debugging Timetable Data")
    print("=" * 50)
    
    # Check all timetable slots
    all_slots = TimetableSlot.objects.all()
    print(f"Total timetable slots in database: {all_slots.count()}")
    
    # Group by student
    students_with_slots = {}
    for slot in all_slots:
        student_email = slot.student.user.email
        if student_email not in students_with_slots:
            students_with_slots[student_email] = []
        students_with_slots[student_email].append(slot)
    
    print(f"\nStudents with timetable slots:")
    for email, slots in students_with_slots.items():
        print(f"  {email}: {len(slots)} slots")
        
        # Show sample slots for this student
        for slot in slots[:3]:
            print(f"    - {slot.day_of_week} {slot.time_slot}: {slot.course.code} - {slot.venue}")
    
    # Check specific student if provided
    print(f"\nChecking specific students:")
    for student in Student.objects.all()[:3]:
        student_slots = TimetableSlot.objects.filter(student=student)
        print(f"  Student {student.user.email} (ID: {student.id}):")
        print(f"    - Semester: {student.semester}, Year: {student.year}")
        print(f"    - Timetable slots: {student_slots.count()}")
        
        # Check slots for current semester/year
        current_slots = student_slots.filter(
            semester=student.semester,
            academic_year=str(student.year)
        )
        print(f"    - Current semester slots: {current_slots.count()}")
        
        if current_slots.exists():
            print(f"    - Sample current slot: {current_slots.first().day_of_week} {current_slots.first().time_slot}")

if __name__ == "__main__":
    debug_timetable()





