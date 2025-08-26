#!/usr/bin/env python3
"""
MongoDB Connection Test Script
Tests various aspects of MongoDB connectivity to diagnose issues
"""

import os
import sys
import time
import traceback
from datetime import datetime


def test_environment_variable():
    """Test if MONGODB_URI environment variable is set"""
    print("🔍 Testing Environment Variable...")

    uri = os.getenv("MONGODB_URI")
    if uri:
        print(f"✅ MONGODB_URI is set")
        print(f"   URI starts with: {uri[:50]}...")
        return uri
    else:
        print("❌ MONGODB_URI environment variable is not set")
        print("   Please set it with: export MONGODB_URI='your-connection-string'")
        return None


def test_pymongo_import():
    """Test if PyMongo can be imported"""
    print("\n🔍 Testing PyMongo Import...")

    try:
        from pymongo import MongoClient
        from pymongo.read_preferences import ReadPreference
        from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure
        print("✅ PyMongo imported successfully")
        return True
    except ImportError as e:
        print(f"❌ PyMongo import failed: {e}")
        print("   Install with: pip install pymongo")
        return False


def test_basic_connection(uri):
    """Test basic MongoDB connection"""
    print("\n🔍 Testing Basic Connection...")

    try:
        from pymongo import MongoClient

        print(f"   Attempting to connect to: {uri[:50]}...")

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=10000,  # 10 seconds
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )

        # Test ping
        result = client.admin.command('ping')
        print(f"✅ Basic connection successful: {result}")

        # Get server info
        server_info = client.admin.command('serverStatus')
        print(f"   MongoDB version: {server_info.get('version', 'Unknown')}")
        print(f"   Uptime: {server_info.get('uptime', 0)} seconds")

        client.close()
        return True

    except Exception as e:
        print(f"❌ Basic connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


def test_resilient_connection(uri):
    """Test resilient connection with replica set handling"""
    print("\n🔍 Testing Resilient Connection...")

    try:
        from pymongo import MongoClient
        from pymongo.read_preferences import ReadPreference

        print("   Testing with SECONDARY_PREFERRED read preference...")

        client = MongoClient(
            uri,
            read_preference=ReadPreference.SECONDARY_PREFERRED,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            maxPoolSize=10,
            retryWrites=True,
            retryReads=True,
        )

        # Test ping
        result = client.admin.command('ping')
        print(f"✅ Resilient connection successful: {result}")

        # Test database access
        db = client.get_database('main')
        db.command('ping')
        print("✅ Database access successful")

        client.close()
        return True

    except Exception as e:
        print(f"❌ Resilient connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


def test_database_operations(uri):
    """Test basic database operations"""
    print("\n🔍 Testing Database Operations...")

    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        db = client.get_database('main')

        # Test collection operations
        test_collection = db.get_collection('test_connection')

        # Insert a test document
        test_doc = {
            'test': True,
            'timestamp': datetime.now(),
            'message': 'Connection test document'
        }

        result = test_collection.insert_one(test_doc)
        print(f"✅ Insert operation successful: {result.inserted_id}")

        # Find the document
        found_doc = test_collection.find_one({'_id': result.inserted_id})
        if found_doc:
            print("✅ Find operation successful")
        else:
            print("❌ Find operation failed")
            return False

        # Delete the test document
        delete_result = test_collection.delete_one({'_id': result.inserted_id})
        if delete_result.deleted_count == 1:
            print("✅ Delete operation successful")
        else:
            print("❌ Delete operation failed")
            return False

        client.close()
        return True

    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False


def test_our_mongodb_module():
    """Test our custom MongoDB module"""
    print("\n🔍 Testing Our MongoDB Module...")

    try:
        # Import our module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db.mongodb import get_client, get_db

        # Test client creation
        client = get_client()
        if client:
            print("✅ Client creation successful")
        else:
            print("❌ Client creation failed")
            return False

        # Test database access
        db = get_db()
        if db is not None:
            print("✅ Database access successful")

            # Test a simple operation
            result = db.command('ping')
            print(f"✅ Database ping successful: {result}")
        else:
            print("❌ Database access failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Our MongoDB module test failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        traceback.print_exc()
        return False


def test_network_connectivity(uri):
    """Test basic network connectivity"""
    print("\n🔍 Testing Network Connectivity...")

    try:
        import socket
        from urllib.parse import urlparse

        # Parse the URI to get hostname
        parsed = urlparse(uri)
        hostname = parsed.hostname

        if not hostname:
            print("❌ Could not parse hostname from URI")
            return False

        print(f"   Testing connection to: {hostname}")

        # Test DNS resolution
        try:
            ip = socket.gethostbyname(hostname)
            print(f"✅ DNS resolution successful: {hostname} -> {ip}")
        except socket.gaierror as e:
            print(f"❌ DNS resolution failed: {e}")
            return False

        # Test port connectivity (MongoDB default port)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((hostname, 27017))
            sock.close()

            if result == 0:
                print("✅ Port 27017 is reachable")
            else:
                print("⚠️  Port 27017 is not reachable (this might be normal for Atlas)")
        except Exception as e:
            print(f"⚠️  Port test failed: {e}")

        return True

    except Exception as e:
        print(f"❌ Network connectivity test failed: {e}")
        return False


def main():
    """Run all MongoDB connection tests"""
    print("=" * 60)
    print("MongoDB Connection Diagnostic Tool")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    print()

    # Test environment variable
    uri = test_environment_variable()
    if not uri:
        print("\n❌ Cannot proceed without MONGODB_URI")
        return False

    # Test PyMongo import
    if not test_pymongo_import():
        print("\n❌ Cannot proceed without PyMongo")
        return False

    # Test network connectivity
    network_ok = test_network_connectivity(uri)

    # Test basic connection
    basic_ok = test_basic_connection(uri)

    # Test resilient connection
    resilient_ok = test_resilient_connection(uri)

    # Test database operations
    operations_ok = test_database_operations(uri)

    # Test our module
    module_ok = test_our_mongodb_module()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    tests = [
        ("Environment Variable", True if uri else False),
        ("PyMongo Import", True),
        ("Network Connectivity", network_ok),
        ("Basic Connection", basic_ok),
        ("Resilient Connection", resilient_ok),
        ("Database Operations", operations_ok),
        ("Our MongoDB Module", module_ok),
    ]

    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<25} {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! MongoDB connection is working properly.")
    else:
        print("⚠️  SOME TESTS FAILED. Check the output above for details.")
        print("\nCommon solutions:")
        print("1. Check your MongoDB Atlas cluster status")
        print("2. Verify your connection string is correct")
        print("3. Ensure your IP is whitelisted in Atlas")
        print("4. Check if your cluster is paused or under maintenance")

    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
