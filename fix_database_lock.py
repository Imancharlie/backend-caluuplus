#!/usr/bin/env python3
"""
Script to fix database lock issues
"""
import os
import sys
import django
import sqlite3
import time

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

def check_database_lock():
    """Check if database is locked and try to fix it"""
    
    print("🔍 Checking database lock status...")
    
    db_path = "db.sqlite3"
    
    try:
        # Try to connect to database
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        
        # Check if database is locked
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        if result:
            print("✅ Database is accessible")
            conn.close()
            return True
            
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print("❌ Database is locked")
            return False
        else:
            print(f"❌ Database error: {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return False

def fix_database_lock():
    """Try to fix database lock issues"""
    
    print("🔧 Attempting to fix database lock...")
    
    # Method 1: Wait and retry
    for i in range(5):
        print(f"⏳ Attempt {i+1}/5...")
        if check_database_lock():
            print("✅ Database lock resolved!")
            return True
        time.sleep(2)
    
    # Method 2: Try to force unlock (if possible)
    try:
        print("🔓 Attempting to force unlock...")
        conn = sqlite3.connect("db.sqlite3", timeout=1)
        conn.execute("PRAGMA busy_timeout = 1000")  # 1 second timeout
        conn.close()
        print("✅ Force unlock attempted")
    except Exception as e:
        print(f"❌ Force unlock failed: {e}")
    
    # Method 3: Check for long-running processes
    print("🔍 Checking for long-running database processes...")
    try:
        conn = sqlite3.connect("db.sqlite3", timeout=1)
        cursor = conn.cursor()
        
        # Check for active transactions
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        print(f"📊 Journal mode: {journal_mode}")
        
        # Check database integrity
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        print(f"🔍 Database integrity: {integrity}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
    
    return False

def main():
    """Main function"""
    print("🚀 Database Lock Fixer")
    print("=" * 50)
    
    if check_database_lock():
        print("✅ Database is working fine!")
        return
    
    print("❌ Database is locked, attempting to fix...")
    
    if fix_database_lock():
        print("✅ Database lock fixed!")
    else:
        print("❌ Could not fix database lock")
        print("\n💡 Manual solutions:")
        print("1. Restart the Django development server")
        print("2. Check for other processes using the database")
        print("3. Delete db.sqlite3 and run migrations again")
        print("4. Use a different database (PostgreSQL/MySQL) for production")

if __name__ == "__main__":
    main()



















