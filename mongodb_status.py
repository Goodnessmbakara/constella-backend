#!/usr/bin/env python3
"""
MongoDB Status Check
Quick script to verify MongoDB connection is working
"""

import os
import sys


def check_mongodb_status():
    """Check MongoDB connection status"""
    print("🔍 Checking MongoDB Status...")

    # Check environment variable
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("❌ MONGODB_URI not set")
        return False

    print(f"✅ MONGODB_URI is configured")

    try:
        # Import our MongoDB module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db.mongodb import db, client

        if db is None:
            print("❌ Database object is None")
            return False

        if client is None:
            print("❌ Client object is None")
            return False

        print("✅ MongoDB objects are properly initialized")

        # Test a simple operation
        result = db.command('ping')
        print(f"✅ Database ping successful: {result}")

        # Test collection access
        test_collection = db.get_collection('test_status')
        count = test_collection.count_documents({})
        print(f"✅ Collection access successful: {count} documents")

        print("\n🎉 MongoDB is working perfectly!")
        print("   Connection: ✅")
        print("   Database: ✅")
        print("   Operations: ✅")

        return True

    except Exception as e:
        print(f"❌ MongoDB check failed: {e}")
        return False


if __name__ == "__main__":
    success = check_mongodb_status()
    sys.exit(0 if success else 1)


