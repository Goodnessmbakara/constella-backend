#!/usr/bin/env python3
"""
Test Application Startup with MongoDB
Verifies that the application can start and use MongoDB connection
"""

import os
import sys
import traceback


def test_app_startup():
    """Test if the application can start and use MongoDB"""
    print("🔍 Testing Application Startup...")

    try:
        # Import our MongoDB module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db.mongodb import get_client, get_db

        print("✅ MongoDB module imported successfully")

        # Test client creation
        client = get_client()
        if client is None:
            print("❌ Client creation failed")
            return False

        print("✅ Client created successfully")

        # Test database access
        db = get_db()
        if db is None:
            print("❌ Database access failed")
            return False

        print("✅ Database accessed successfully")

        # Test a simple database operation
        result = db.command('ping')
        print(f"✅ Database ping successful: {result}")

        # Test accessing a collection
        test_collection = db.get_collection('test_startup')
        print("✅ Collection access successful")

        # Test a simple query
        count = test_collection.count_documents({})
        print(f"✅ Query successful: {count} documents in test collection")

        print("\n🎉 Application startup test PASSED!")
        print("   MongoDB connection is working properly.")
        print("   The application should be able to start and use the database.")

        return True

    except Exception as e:
        print(f"❌ Application startup test failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        traceback.print_exc()
        return False


def test_main_import():
    """Test if main.py can be imported without errors"""
    print("\n🔍 Testing Main Module Import...")

    try:
        # Import main module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import main
        print("✅ Main module imported successfully")
        return True

    except Exception as e:
        print(f"❌ Main module import failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        traceback.print_exc()
        return False


def main():
    """Run application startup tests"""
    print("=" * 60)
    print("Application Startup Test")
    print("=" * 60)

    # Test main module import
    main_ok = test_main_import()

    # Test application startup with MongoDB
    startup_ok = test_app_startup()

    # Summary
    print("\n" + "=" * 60)
    print("STARTUP TEST SUMMARY")
    print("=" * 60)

    tests = [
        ("Main Module Import", main_ok),
        ("Application Startup", startup_ok),
    ]

    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<25} {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Your application should start properly.")
    else:
        print("⚠️  SOME TESTS FAILED. Check the output above for details.")

    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


