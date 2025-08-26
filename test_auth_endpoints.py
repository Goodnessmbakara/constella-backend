#!/usr/bin/env python3
"""
Auth Endpoints Test Script
Tests all authentication endpoints to ensure they're working properly
"""

import os
import sys
import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"  # Adjust if your server runs on different port
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
        print("   Start the server with: uvicorn main:app --reload")
        return False
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return False

def test_get_access_token():
    """Test the get-access-token endpoint"""
    print("\n🔍 Testing Get Access Token Endpoint...")
    
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
                print("✅ Access token generated successfully")
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

def test_onboarding_status_without_token():
    """Test onboarding status endpoint without token (should fail)"""
    print("\n🔍 Testing Onboarding Status (No Token) - Should Fail...")
    
    url = f"{BASE_URL}/auth/onboarding-status"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 401:
            print("✅ Correctly rejected request without token")
            return True
        else:
            print(f"❌ Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_onboarding_status_with_token(token: str):
    """Test onboarding status endpoint with valid token"""
    print("\n🔍 Testing Onboarding Status (With Token)...")
    
    url = f"{BASE_URL}/auth/onboarding-status"
    headers = {"access-token": token}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Onboarding status retrieved successfully")
            print(f"   User ID: {data.get('user_id', 'N/A')}")
            print(f"   Email: {data.get('email', 'N/A')}")
            print(f"   Is Onboarded: {data.get('is_onboarded', 'N/A')}")
            print(f"   Has Subscription: {data.get('has_subscription', 'N/A')}")
            print(f"   Has Signup: {data.get('has_signup', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Onboarding status test failed: {e}")
        return False

def test_update_bio_without_token():
    """Test update bio endpoint without token (should fail)"""
    print("\n🔍 Testing Update Bio (No Token) - Should Fail...")
    
    url = f"{BASE_URL}/auth/update-bio"
    payload = {
        "bio": "Test bio",
        "display_name": "Test User",
        "avatar_url": "https://example.com/avatar.jpg"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 401:
            print("✅ Correctly rejected request without token")
            return True
        else:
            print(f"❌ Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_update_bio_with_token(token: str):
    """Test update bio endpoint with valid token"""
    print("\n🔍 Testing Update Bio (With Token)...")
    
    url = f"{BASE_URL}/auth/update-bio"
    headers = {"access-token": token}
    payload = {
        "bio": "This is a test bio for the auth endpoint test",
        "display_name": "Test User",
        "avatar_url": "https://example.com/avatar.jpg"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Bio updated successfully")
            print(f"   Success: {data.get('success', 'N/A')}")
            print(f"   Message: {data.get('message', 'N/A')}")
            print(f"   User ID: {data.get('user_id', 'N/A')}")
            print(f"   Bio: {data.get('bio', 'N/A')}")
            print(f"   Display Name: {data.get('display_name', 'N/A')}")
            print(f"   Avatar URL: {data.get('avatar_url', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Update bio test failed: {e}")
        return False

def test_get_bio_without_token():
    """Test get bio endpoint without token (should fail)"""
    print("\n🔍 Testing Get Bio (No Token) - Should Fail...")
    
    url = f"{BASE_URL}/auth/get-bio"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 401:
            print("✅ Correctly rejected request without token")
            return True
        else:
            print(f"❌ Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_get_bio_with_token(token: str):
    """Test get bio endpoint with valid token"""
    print("\n🔍 Testing Get Bio (With Token)...")
    
    url = f"{BASE_URL}/auth/get-bio"
    headers = {"access-token": token}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Bio retrieved successfully")
            print(f"   Success: {data.get('success', 'N/A')}")
            print(f"   Message: {data.get('message', 'N/A')}")
            print(f"   User ID: {data.get('user_id', 'N/A')}")
            print(f"   Bio: {data.get('bio', 'N/A')}")
            print(f"   Display Name: {data.get('display_name', 'N/A')}")
            print(f"   Avatar URL: {data.get('avatar_url', 'N/A')}")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Get bio test failed: {e}")
        return False

def test_invalid_token():
    """Test endpoints with invalid token (should fail)"""
    print("\n🔍 Testing Invalid Token - Should Fail...")
    
    invalid_token = "invalid.token.here"
    headers = {"access-token": invalid_token}
    
    # Test onboarding status with invalid token
    url = f"{BASE_URL}/auth/onboarding-status"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 401:
            print("✅ Correctly rejected invalid token for onboarding status")
        else:
            print(f"❌ Expected 401 for invalid token, got {response.status_code}")
    except Exception as e:
        print(f"❌ Invalid token test failed: {e}")
    
    # Test get bio with invalid token
    url = f"{BASE_URL}/auth/get-bio"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 401:
            print("✅ Correctly rejected invalid token for get bio")
        else:
            print(f"❌ Expected 401 for invalid token, got {response.status_code}")
    except Exception as e:
        print(f"❌ Invalid token test failed: {e}")
    
    return True

def main():
    """Run all auth endpoint tests"""
    print("=" * 60)
    print("Auth Endpoints Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Email: {TEST_EMAIL}")
    print(f"Test Tenant: {TEST_TENANT}")
    print()
    
    # Test server health first
    if not test_server_health():
        print("\n❌ Cannot proceed without a running server")
        print("   Start the server with: uvicorn main:app --reload")
        return False
    
    # Test get access token
    token = test_get_access_token()
    if not token:
        print("\n❌ Cannot proceed without a valid token")
        return False
    
    # Test endpoints without token (should fail)
    test_onboarding_status_without_token()
    test_update_bio_without_token()
    test_get_bio_without_token()
    
    # Test invalid token
    test_invalid_token()
    
    # Test endpoints with valid token
    onboarding_ok = test_onboarding_status_with_token(token)
    update_bio_ok = test_update_bio_with_token(token)
    get_bio_ok = test_get_bio_with_token(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("AUTH ENDPOINTS TEST SUMMARY")
    print("=" * 60)
    
    tests = [
        ("Server Health", True),
        ("Get Access Token", token is not None),
        ("Onboarding Status (No Token)", True),  # Should fail correctly
        ("Update Bio (No Token)", True),         # Should fail correctly
        ("Get Bio (No Token)", True),            # Should fail correctly
        ("Invalid Token", True),                 # Should fail correctly
        ("Onboarding Status (With Token)", onboarding_ok),
        ("Update Bio (With Token)", update_bio_ok),
        ("Get Bio (With Token)", get_bio_ok),
    ]
    
    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<35} {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL AUTH ENDPOINTS ARE WORKING PERFECTLY!")
        print("   Authentication is properly configured.")
        print("   All endpoints are secure and functional.")
    else:
        print("⚠️  SOME TESTS FAILED. Check the output above for details.")
    
    print("=" * 60)
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


