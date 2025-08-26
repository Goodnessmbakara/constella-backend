#!/usr/bin/env python3
"""
Simple Auth Endpoints Test
Quick test of auth endpoints with shorter timeouts
"""

import requests
import json

BASE_URL = "http://localhost:8000"


def test_get_access_token():
    """Test the get-access-token endpoint"""
    print("🔍 Testing Get Access Token...")

    url = f"{BASE_URL}/auth/get-access-token"
    payload = {
        "tenant_name": "test-tenant",
        "user_email": "test@example.com"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("✅ Token generated successfully")
            print(f"Token: {data.get('token', 'N/A')[:50]}...")
            return data.get('token')
        else:
            print(f"❌ Failed: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_onboarding_status(token):
    """Test onboarding status with token"""
    print("\n🔍 Testing Onboarding Status...")

    url = f"{BASE_URL}/auth/onboarding-status"
    headers = {"access-token": token}

    try:
        response = requests.get(url, headers=headers, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Headers sent: {headers}")

        if response.status_code == 200:
            data = response.json()
            print("✅ Onboarding status retrieved")
            print(f"User ID: {data.get('user_id', 'N/A')}")
            print(f"Email: {data.get('email', 'N/A')}")
            return True
        else:
            print(f"❌ Failed: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("=" * 50)
    print("Simple Auth Endpoints Test")
    print("=" * 50)

    # Test get access token
    token = test_get_access_token()

    if token:
        # Test onboarding status
        test_onboarding_status(token)

    print("\n" + "=" * 50)
    print("Test completed!")


if __name__ == "__main__":
    main()
