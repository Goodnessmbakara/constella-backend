from fastapi import APIRouter, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import jwt
import os
from db.models.constella.constella_shared_view import ConstellaSharedView
from db.models.constella.constella_signup import ConstellaSignup
from dependencies import validate_access_token
import traceback

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

secret_key = os.getenv("JWT_SECRET")

# Helper function to get current user from JWT token


async def get_current_user(access_token: str = Depends(validate_access_token)) -> Dict:
    """
    Extract user information from the validated access token
    """
    try:
        # The validate_access_token function returns the decoded token
        # We need to extract user information from it
        user_id = access_token.get(
            "user_id", access_token.get("sub", "unknown"))
        email = access_token.get("email", "unknown@example.com")

        # For now, return basic user info
        # You can expand this to fetch additional user data from database
        return {
            "user_id": user_id,
            "email": email,
            "subscription": None,  # TODO: Fetch from database
            "signup_info": None,   # TODO: Fetch from database
        }
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid user token: {str(e)}")


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


@router.post("/get-access-token")
async def get_access_token(get_access_token_req: GetAccessTokenReq):
    """
    Gets a secure JWT token that they can use for future requests.
    """
    try:
        # Create the payload
        payload = {
            'tenant_name': get_access_token_req.tenant_name,
            'user_email': get_access_token_req.user_email,
        }

        # Get the secret key from environment variable
        if not secret_key:
            raise HTTPException(
                status_code=500, detail="JWT secret key not configured")

        # Generate the JWT token
        token = jwt.encode(payload, secret_key, algorithm="HS256")

        decoded = jwt.decode(token, secret_key, algorithms=["HS256"])

        return {"token": token}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating JWT: {str(e)}")

# 1. Onboarding Status Endpoint


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def check_onboarding_status(current_user: Dict = Depends(get_current_user)):
    """
    Check if a user has been onboarded (has subscription and/or signup)
    """
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]
        subscription = current_user["subscription"]
        signup_info = current_user["signup_info"]

        # User is considered onboarded if they have either a subscription or signup record
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

# 2. Send/Update User Bio Endpoint


@router.post("/update-bio", response_model=UserBioResponse)
async def update_user_bio(
    bio_request: UserBioRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Update user bio, display name, and avatar URL
    """
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]

        # Get existing signup info or create new one
        signup_info = ConstellaSignup.get_user_info(email)

        if not signup_info:
            # Create new signup record with bio info
            signup = ConstellaSignup(email=email)
            signup.bio = bio_request.bio
            if bio_request.display_name:
                signup.display_name = bio_request.display_name
            if bio_request.avatar_url:
                signup.avatar_url = bio_request.avatar_url
            signup.save()
        else:
            # Update existing signup record
            update_data = {"bio": bio_request.bio}
            if bio_request.display_name:
                update_data["display_name"] = bio_request.display_name
            if bio_request.avatar_url:
                update_data["avatar_url"] = bio_request.avatar_url

            ConstellaSignup.update_user_info(email, update_data)

        return UserBioResponse(
            success=True,
            message="User bio updated successfully",
            user_id=user_id,
            email=email,
            bio=bio_request.bio,
            display_name=bio_request.display_name,
            avatar_url=bio_request.avatar_url
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error updating user bio: {str(e)}")

# 3. Get User Bio Endpoint


@router.get("/get-bio", response_model=UserBioResponse)
async def get_user_bio(current_user: Dict = Depends(get_current_user)):
    """
    Get user bio, display name, and avatar URL
    """
    try:
        user_id = current_user["user_id"]
        email = current_user["email"]

        # Get signup info
        signup_info = ConstellaSignup.get_user_info(email)

        if not signup_info:
            return UserBioResponse(
                success=True,
                message="No bio information found",
                user_id=user_id,
                email=email
            )

        return UserBioResponse(success=True,
                               message="Bio information retrieved successfully",
                               user_id=user_id,
                               email=email,
                               bio=signup_info.get("bio"),
                               display_name=signup_info.get("display_name"),
                               avatar_url=signup_info.get("avatar_url")
                               )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error getting user bio: {str(e)}")
