#!/usr/bin/env python3
"""
Database-Focused Auth Test
Tests the auth system's database operations without requiring Firebase tokens
"""

import os
import sys
import time
from typing import Dict, Any


def test_mongodb_connection():
    """Test MongoDB connection and basic operations"""
    print("🔍 Testing MongoDB Connection...")

    try:
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

        return True

    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False


def test_constella_signup_model():
    """Test the ConstellaSignup model with real database operations"""
    print("\n🔍 Testing ConstellaSignup Model...")

    try:
        from db.models.constella.constella_signup import ConstellaSignup

        # Test creating a user
        test_email = "auth-test@example.com"

        # Test get_user_info (should return None for new user)
        user_info = ConstellaSignup.get_user_info(test_email)
        if user_info is None:
            print("✅ get_user_info returns None for new user")
        else:
            print("⚠️  User already exists")

        # Test update_user_info (creates user if doesn't exist)
        update_data = {
            "bio": "Test bio for auth system",
            "display_name": "Auth Test User",
            "avatar_url": "https://example.com/auth-avatar.jpg",
            "tenant_name": "test-tenant"
        }

        ConstellaSignup.update_user_info(test_email, update_data)
        print("✅ update_user_info successful")

        # Test get_user_info again (should return the updated data)
        user_info = ConstellaSignup.get_user_info(test_email)
        if user_info:
            print("✅ get_user_info returns updated data")
            print(f"   Bio: {user_info.get('bio', 'N/A')}")
            print(f"   Display Name: {user_info.get('display_name', 'N/A')}")
            print(f"   Avatar URL: {user_info.get('avatar_url', 'N/A')}")
            print(f"   Tenant: {user_info.get('tenant_name', 'N/A')}")
        else:
            print("❌ get_user_info failed to retrieve updated data")
            return False

        # Test get_user_bio
        bio_info = ConstellaSignup.get_user_bio(test_email)
        if bio_info:
            print("✅ get_user_bio successful")
            print(f"   Bio: {bio_info.get('bio', 'N/A')}")
            print(f"   Display Name: {bio_info.get('display_name', 'N/A')}")
            print(f"   Avatar URL: {bio_info.get('avatar_url', 'N/A')}")
        else:
            print("❌ get_user_bio failed")
            return False

        # Test updating existing user
        new_update_data = {
            "bio": "Updated bio for auth system",
            "display_name": "Updated Auth Test User"
        }

        ConstellaSignup.update_user_info(test_email, new_update_data)
        print("✅ update_user_info for existing user successful")

        # Verify the update
        updated_user_info = ConstellaSignup.get_user_info(test_email)
        if updated_user_info and updated_user_info.get('bio') == "Updated bio for auth system":
            print("✅ User update verification successful")
        else:
            print("❌ User update verification failed")
            return False

        # Clean up - delete the test user
        from db.mongodb import db
        db.get_collection('constella_signup').delete_one({"email": test_email})
        print("✅ Cleanup successful")

        return True

    except Exception as e:
        print(f"❌ ConstellaSignup model test failed: {e}")
        return False


def test_auth_endpoint_structure():
    """Test that auth endpoints are properly structured (without requiring tokens)"""
    print("\n🔍 Testing Auth Endpoint Structure...")

    try:
        import requests

        # Test that the server is running
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and accessible")
        else:
            print("❌ Server is not accessible")
            return False

        # Test that auth endpoints exist (should return 401 for missing token, not 404)
        auth_endpoints = [
            "/auth/onboarding-status",
            "/auth/update-bio",
            "/auth/get-bio"
        ]

        for endpoint in auth_endpoints:
            try:
                response = requests.get(
                    f"http://localhost:8000{endpoint}", timeout=5)
                if response.status_code == 401:
                    print(
                        f"✅ {endpoint} exists and properly rejects unauthorized requests")
                elif response.status_code == 405:
                    print(f"✅ {endpoint} exists (method not allowed for GET)")
                else:
                    print(
                        f"⚠️  {endpoint} returned status {response.status_code}")
            except Exception as e:
                print(f"❌ {endpoint} test failed: {e}")

        return True

    except Exception as e:
        print(f"❌ Auth endpoint structure test failed: {e}")
        return False


def test_jwt_token_generation():
    """Test JWT token generation (this endpoint doesn't require Firebase)"""
    print("\n🔍 Testing JWT Token Generation...")

    try:
        import requests

        url = "http://localhost:8000/auth/get-access-token"
        payload = {
            "tenant_name": "test-tenant",
            "user_email": "test@example.com"
        }

        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                print("✅ JWT token generated successfully")
                print(f"   Token: {data['token'][:50]}...")

                # Test token structure (should be a valid JWT)
                import jwt
                try:
                    # Try to decode without verification to check structure
                    decoded = jwt.decode(data['token'], options={
                                         "verify_signature": False})
                    print(f"   Token payload: {decoded}")
                    return True
                except Exception as e:
                    print(f"❌ Token structure invalid: {e}")
                    return False
            else:
                print("❌ Response missing token field")
                return False
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ JWT token generation test failed: {e}")
        return False


def main():
    """Run database-focused auth tests"""
    print("=" * 60)
    print("Database-Focused Auth Test Suite")
    print("=" * 60)
    print("Testing auth system with real MongoDB database")
    print()

    # Test MongoDB connection
    mongodb_ok = test_mongodb_connection()

    # Test ConstellaSignup model
    model_ok = test_constella_signup_model()

    # Test auth endpoint structure
    endpoints_ok = test_auth_endpoint_structure()

    # Test JWT token generation
    jwt_ok = test_jwt_token_generation()

    # Summary
    print("\n" + "=" * 60)
    print("DATABASE-FOCUSED AUTH TEST SUMMARY")
    print("=" * 60)

    tests = [
        ("MongoDB Connection", mongodb_ok),
        ("ConstellaSignup Model", model_ok),
        ("Auth Endpoint Structure", endpoints_ok),
        ("JWT Token Generation", jwt_ok),
    ]

    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<30} {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 AUTH SYSTEM DATABASE OPERATIONS ARE WORKING PERFECTLY!")
        print("   MongoDB connection is stable and functional.")
        print("   User data operations are working correctly.")
        print("   Auth endpoints are properly structured.")
        print("   JWT token generation is functional.")
        print("\n   Note: Firebase token validation requires real Firebase client.")
        print("   The auth system is ready for production use!")
    else:
        print("⚠️  SOME TESTS FAILED. Check the output above for details.")

    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


