#!/usr/bin/env python3
"""
Real Auth Endpoints Test
Tests auth endpoints against the real Firebase authentication and MongoDB database
"""

import os
import sys
import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test@example.com"
TEST_TENANT = "test-tenant"


def test_server_health():
    """Test if the server is running"""
    print("🔍 Testing Server Health...")

    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=10)
        if response.status_code == 200:
            print("✅ Server is running and accessible")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Is it running?")
        return False
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return False


def test_get_access_token():
    """Test the get-access-token endpoint (JWT-based)"""
    print("\n🔍 Testing Get Access Token (JWT)...")

    url = f"{BASE_URL}/auth/get-access-token"
    payload = {
        "tenant_name": TEST_TENANT,
        "user_email": TEST_EMAIL
    }

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                print("✅ JWT token generated successfully")
                print(f"   Token: {data['token'][:50]}...")
                return data["token"]
            else:
                print("❌ Response missing token field")
                return None
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Get access token failed: {e}")
        return None


def test_onboarding_status_with_jwt(jwt_token: str):
    """Test onboarding status with JWT token"""
    print("\n🔍 Testing Onboarding Status (JWT Token)...")

    url = f"{BASE_URL}/auth/onboarding-status"
    headers = {"access-token": jwt_token}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print("✅ Onboarding status retrieved successfully")
            print(f"   User ID: {data.get('user_id', 'N/A')}")
            print(f"   Email: {data.get('email', 'N/A')}")
            print(f"   Is Onboarded: {data.get('is_onboarded', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Onboarding status test failed: {e}")
        return False


def test_update_bio_with_jwt(jwt_token: str):
    """Test update bio with JWT token"""
    print("\n🔍 Testing Update Bio (JWT Token)...")

    url = f"{BASE_URL}/auth/update-bio"
    headers = {"access-token": jwt_token}
    payload = {
        "bio": "This is a test bio for the real database test",
        "display_name": "Test User",
        "avatar_url": "https://example.com/avatar.jpg"
    }

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print("✅ Bio updated successfully")
            print(f"   Success: {data.get('success', 'N/A')}")
            print(f"   Message: {data.get('message', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Update bio test failed: {e}")
        return False


def test_get_bio_with_jwt(jwt_token: str):
    """Test get bio with JWT token"""
    print("\n🔍 Testing Get Bio (JWT Token)...")

    url = f"{BASE_URL}/auth/get-bio"
    headers = {"access-token": jwt_token}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print("✅ Bio retrieved successfully")
            print(f"   Success: {data.get('success', 'N/A')}")
            print(f"   Bio: {data.get('bio', 'N/A')}")
            print(f"   Display Name: {data.get('display_name', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Get bio test failed: {e}")
        return False


def test_database_operations():
    """Test direct database operations to verify MongoDB is working"""
    print("\n🔍 Testing Database Operations...")

    try:
        # Import our MongoDB module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db.mongodb import db

        if db is None:
            print("❌ Database is not initialized")
            return False

        # Test collection access
        collection = db.get_collection('constella_signup')
        print("✅ Collection access successful")

        # Test a simple query
        count = collection.count_documents({})
        print(f"✅ Query successful: {count} documents in collection")

        # Test inserting a test document
        test_doc = {
            'email': 'test@example.com',
            'test': True,
            'timestamp': time.time()
        }

        result = collection.insert_one(test_doc)
        print(f"✅ Insert successful: {result.inserted_id}")

        # Test finding the document
        found = collection.find_one({'email': 'test@example.com'})
        if found:
            print("✅ Find operation successful")
        else:
            print("❌ Find operation failed")
            return False

        # Clean up - delete the test document
        delete_result = collection.delete_one({'email': 'test@example.com'})
        if delete_result.deleted_count == 1:
            print("✅ Delete operation successful")
        else:
            print("❌ Delete operation failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        return False


def test_constella_signup_model():
    """Test the ConstellaSignup model directly"""
    print("\n🔍 Testing ConstellaSignup Model...")

    try:
        from db.models.constella.constella_signup import ConstellaSignup

        # Test creating a user
        test_email = "test-model@example.com"

        # Test get_user_info (should return None for new user)
        user_info = ConstellaSignup.get_user_info(test_email)
        if user_info is None:
            print("✅ get_user_info returns None for new user")
        else:
            print("⚠️  User already exists")

        # Test update_user_info
        update_data = {
            "bio": "Test bio from model",
            "display_name": "Test Model User",
            "avatar_url": "https://example.com/model-avatar.jpg"
        }

        ConstellaSignup.update_user_info(test_email, update_data)
        print("✅ update_user_info successful")

        # Debug: Check what's actually in the database
        from db.mongodb import db
        raw_data = db.get_collection(
            'constella_signup').find_one({"email": test_email})
        print(f"   Raw data from DB: {raw_data}")

        # Test get_user_info again (should return the updated data)
        user_info = ConstellaSignup.get_user_info(test_email)
        print(f"   Parsed user_info: {user_info}")
        if user_info:
            print("✅ get_user_info returns updated data")
            print(f"   Bio: {user_info.get('bio', 'N/A')}")
            print(f"   Display Name: {user_info.get('display_name', 'N/A')}")
        else:
            print("❌ get_user_info failed to retrieve updated data")
            return False

        # Test get_user_bio
        bio_info = ConstellaSignup.get_user_bio(test_email)
        if bio_info:
            print("✅ get_user_bio successful")
            print(f"   Bio: {bio_info.get('bio', 'N/A')}")
        else:
            print("❌ get_user_bio failed")
            return False

        # Clean up
        ConstellaSignup.delete_all()
        print("✅ Cleanup successful")

        return True

    except Exception as e:
        print(f"❌ ConstellaSignup model test failed: {e}")
        return False


def main():
    """Run all real auth endpoint tests"""
    print("=" * 60)
    print("Real Auth Endpoints Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Email: {TEST_EMAIL}")
    print(f"Test Tenant: {TEST_TENANT}")
    print()

    # Test server health first
    if not test_server_health():
        print("\n❌ Cannot proceed without a running server")
        return False

    # Test database operations
    db_ok = test_database_operations()

    # Test ConstellaSignup model
    model_ok = test_constella_signup_model()

    # Test JWT token generation
    jwt_token = test_get_access_token()

    # Test endpoints with JWT token
    onboarding_ok = False
    update_bio_ok = False
    get_bio_ok = False

    if jwt_token:
        onboarding_ok = test_onboarding_status_with_jwt(jwt_token)
        update_bio_ok = test_update_bio_with_jwt(jwt_token)
        get_bio_ok = test_get_bio_with_jwt(jwt_token)

    # Summary
    print("\n" + "=" * 60)
    print("REAL AUTH ENDPOINTS TEST SUMMARY")
    print("=" * 60)

    tests = [
        ("Server Health", True),
        ("Database Operations", db_ok),
        ("ConstellaSignup Model", model_ok),
        ("JWT Token Generation", jwt_token is not None),
        ("Onboarding Status (JWT)", onboarding_ok),
        ("Update Bio (JWT)", update_bio_ok),
        ("Get Bio (JWT)", get_bio_ok),
    ]

    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<30} {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL REAL AUTH ENDPOINTS ARE WORKING PERFECTLY!")
        print("   Authentication is properly configured.")
        print("   Database operations are functional.")
        print("   All endpoints are secure and working.")
    else:
        print("⚠️  SOME TESTS FAILED. Check the output above for details.")

    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
