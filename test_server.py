#!/usr/bin/env python3
"""
Minimal Test Server for Auth Endpoints
Bypasses MongoDB initialization issues to test auth functionality
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Dict, Optional, Any
import jwt
import os

app = FastAPI(title="Auth Test Server")

# Mock JWT secret for testing
JWT_SECRET = "test-secret-key-for-testing-only"

# Mock user data
MOCK_USERS = {
    "test@example.com": {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "subscription": None,
        "signup_info": None
    }
}


class GetAccessTokenReq(BaseModel):
    tenant_name: str
    user_email: str


class OnboardingStatusResponse(BaseModel):
    is_onboarded: bool
    has_subscription: bool
    has_signup: bool
    user_id: str
    email: str
    subscription: Optional[Dict[str, Any]] = None
    signup_info: Optional[Dict[str, Any]] = None


class UserBioRequest(BaseModel):
    bio: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserBioResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    email: str
    bio: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


def validate_access_token(access_token: Optional[str] = Header(None)):
    """Mock access token validation"""
    if access_token is None:
        raise HTTPException(status_code=401, detail="Access token missing")

    try:
        # Decode the JWT token
        decoded_token = jwt.decode(
            access_token, JWT_SECRET, algorithms=["HS256"])
        return decoded_token
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token")
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Token validation error: {str(e)}")


async def get_current_user(access_token: str = Depends(validate_access_token)) -> Dict:
    """Mock current user function"""
    return {
        "user_id": access_token.get("user_id", "unknown"),
        "email": access_token.get("email", "unknown@example.com"),
        "subscription": None,
        "signup_info": None,
    }


@app.post("/auth/get-access-token")
async def get_access_token(get_access_token_req: GetAccessTokenReq):
    """Get a test JWT token"""
    try:
        payload = {
            'tenant_name': get_access_token_req.tenant_name,
            'user_email': get_access_token_req.user_email,
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        return {"token": token}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating JWT: {str(e)}")


@app.get("/auth/onboarding-status", response_model=OnboardingStatusResponse)
async def check_onboarding_status(current_user: Dict = Depends(get_current_user)):
    """Check onboarding status"""
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]
        subscription = current_user["subscription"]
        signup_info = current_user["signup_info"]

        has_subscription = subscription is not None
        has_signup = signup_info is not None
        is_onboarded = has_subscription or has_signup

        return OnboardingStatusResponse(
            is_onboarded=is_onboarded,
            has_subscription=has_subscription,
            has_signup=has_signup,
            user_id=user_id,
            email=email,
            subscription=subscription,
            signup_info=signup_info
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error checking onboarding status: {str(e)}")


@app.post("/auth/update-bio", response_model=UserBioResponse)
async def update_user_bio(
    bio_request: UserBioRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Update user bio"""
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]

        # Mock update - in real app this would save to database
        print(f"Mock: Updating bio for {email}")

        return UserBioResponse(
            success=True,
            message="Bio updated successfully",
            user_id=user_id,
            email=email,
            bio=bio_request.bio,
            display_name=bio_request.display_name,
            avatar_url=bio_request.avatar_url
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating user bio: {str(e)}")


@app.get("/auth/get-bio", response_model=UserBioResponse)
async def get_user_bio(current_user: Dict = Depends(get_current_user)):
    """Get user bio"""
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]

        # Mock data - in real app this would fetch from database
        return UserBioResponse(
            success=True,
            message="Bio information retrieved successfully",
            user_id=user_id,
            email=email,
            bio="Mock bio for testing",
            display_name="Test User",
            avatar_url="https://example.com/avatar.jpg"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting user bio: {str(e)}")


@app.get("/")
async def root():
    return {"message": "Auth Test Server is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
