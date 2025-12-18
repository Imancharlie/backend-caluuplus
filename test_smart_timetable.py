#!/usr/bin/env python
"""
Test the smart timetable fallback system
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from api.models import Student, TimetableSlot, Course, Program, College, University
from api.timetable_utils import get_smart_timetable_slots, find_fallback_timetable

def test_smart_timetable():
    print("🧪 Testing Smart Timetable Fallback System")
    print("=" * 60)
    
    # Get a student who has no timetable slots
    students_without_slots = []
    for student in Student.objects.all():
        slots = TimetableSlot.objects.filter(student=student, semester=1, academic_year='1')
        if not slots.exists():
            students_without_slots.append(student)
    
    print(f"Students without timetable slots: {len(students_without_slots)}")
    
    # Prefer the test_electrical@example.com student if it exists
    test_student = Student.objects.filter(user__email='test_electrical@example.com').first()
    if test_student:
        students_without_slots = [test_student]
        print(f"Using specific test student: {test_student.user.email}")
    
    if not students_without_slots:
        print("All students have timetable slots. Creating a test student...")
        
        # Create a test student without timetable slots
        university = University.objects.first()
        college = College.objects.first()
        program = Program.objects.first()
        
        if university and college and program:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            user, created = User.objects.get_or_create(
                email='test_fallback@example.com',
                defaults={
                    'display_name': 'Test Fallback Student',
                    'username': 'test_fallback@example.com'
                }
            )
            
            student, created = Student.objects.get_or_create(
                user=user,
                defaults={
                    'university': university,
                    'college': college,
                    'program': program,
                    'year': 1,
                    'semester': 1
                }
            )
            
            students_without_slots = [student]
            print(f"Created test student: {student.user.email}")
    
    if students_without_slots:
        test_student = students_without_slots[0]
        print(f"\nTesting with student: {test_student.user.email}")
        print(f"Program: {test_student.program.name}")
        print(f"Year: {test_student.year}, Semester: {test_student.semester}")
        
        # Test the smart timetable function
        print("\n1. Testing get_smart_timetable_slots...")
        smart_slots = get_smart_timetable_slots(test_student, 1, '1')
        print(f"   Smart slots found: {len(smart_slots) if hasattr(smart_slots, '__len__') else smart_slots.count()}")
        
        if smart_slots:
            print("   ✅ Smart fallback worked!")
            print("   Sample slots:")
            for i, slot in enumerate(smart_slots[:3]):
                print(f"     {i+1}. {slot.day_of_week} {slot.time_slot}: {slot.course.code} - {slot.venue}")
        else:
            print("   ❌ No smart slots found")
            
            # Test the fallback function directly
            print("\n2. Testing find_fallback_timetable directly...")
            fallback_slots = find_fallback_timetable(test_student, 1, '1')
            print(f"   Fallback slots found: {len(fallback_slots) if hasattr(fallback_slots, '__len__') else fallback_slots.count()}")
            
            if fallback_slots:
                print("   ✅ Fallback function worked!")
                print("   Sample fallback slots:")
                for i, slot in enumerate(fallback_slots[:3]):
                    print(f"     {i+1}. {slot.day_of_week} {slot.time_slot}: {slot.course.code} - {slot.venue}")
            else:
                print("   ❌ No fallback slots found")
                
                # Check if there are any similar students
                similar_students = Student.objects.filter(
                    program=test_student.program,
                    year=test_student.year,
                    semester=test_student.semester
                ).exclude(id=test_student.id)
                
                print(f"\n   Similar students found: {similar_students.count()}")
                
                if similar_students.exists():
                    print("   Similar students:")
                    for sim_student in similar_students[:3]:
                        sim_slots = TimetableSlot.objects.filter(
                            student=sim_student,
                            semester=1,
                            academic_year='1'
                        )
                        print(f"     - {sim_student.user.email}: {sim_slots.count()} slots")
    else:
        print("No students without timetable slots found for testing")
    
    print("\n" + "=" * 60)
    print("🎉 Smart Timetable Test Complete!")

if __name__ == "__main__":
    test_smart_timetable()
