from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional, Tuple
import jwt
import os
import traceback
import sentry_sdk
from datetime import datetime
from db.models.constella.constella_signup import ConstellaSignup

# Constants
JWT_SECRET = os.getenv("JWT_SECRET")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "horizon-mobile-a1a8b")
FIREBASE_ISSUER = "securetoken.google.com"
JWT_ALGORITHM = "HS256"

# Token types


class TokenType:
    FIREBASE = "firebase"
    CUSTOM_JWT = "custom_jwt"
    UNKNOWN = "unknown"
    INVALID = "invalid"


router = APIRouter(
    prefix="/horizon/auth",
    tags=["horizon_auth"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)


class TokenVerificationResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    token_type: Optional[str] = None
    expires_at: Optional[int] = None
    valid: bool


class UserBioRequest(BaseModel):
    bio: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserBioResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[int] = None  # Unix timestamp in milliseconds
    updated_at: Optional[int] = None  # Unix timestamp in milliseconds


# Helper functions
def extract_token_from_request(request: Request) -> str:
    """Extract JWT token from request headers"""
    auth_header = request.headers.get("Authorization")
    access_token = request.headers.get("access-token")

    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    elif access_token:
        return access_token
    else:
        raise HTTPException(
            status_code=401,
            detail="No Authorization header or access-token provided"
        )


def determine_token_type(payload: Dict[str, Any]) -> str:
    """Determine token type based on payload structure"""
    if "iss" in payload and FIREBASE_ISSUER in str(payload.get("iss", "")):
        return TokenType.FIREBASE
    elif "user_email" in payload or "tenant_name" in payload:
        return TokenType.CUSTOM_JWT
    else:
        return TokenType.UNKNOWN


def extract_user_info_from_payload(payload: Dict[str, Any], token_type: str) -> Dict[str, str]:
    """Extract user information from token payload based on token type"""
    if token_type == TokenType.FIREBASE:
        user_id = payload.get("user_id") or payload.get("sub")
        email = payload.get("email")
    elif token_type == TokenType.CUSTOM_JWT:
        user_id = payload.get("tenant_name")
        email = payload.get("user_email")
    else:
        raise HTTPException(status_code=401, detail="Unknown token format")

    if not email:
        raise HTTPException(status_code=401, detail="No email found in token")

    return {
        "user_id": user_id or email,
        "email": email
    }


def verify_custom_jwt_token(token: str) -> None:
    """Verify custom JWT token signature if secret is available"""
    if JWT_SECRET:
        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")


def get_current_timestamp_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(datetime.now().timestamp() * 1000)

# Helper function to extract user info from token


async def get_current_user_from_token(request: Request) -> Dict[str, Any]:
    """Extract user information from the token in request headers"""
    try:
        # Extract token from request
        token = extract_token_from_request(request)

        # Decode token without verification to check structure
        try:
            unverified_payload = jwt.decode(
                token, options={"verify_signature": False})
        except jwt.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid token format")

        # Determine token type and extract user info
        token_type = determine_token_type(unverified_payload)

        # Verify custom JWT tokens
        if token_type == TokenType.CUSTOM_JWT:
            verify_custom_jwt_token(token)

        # Extract user information
        return extract_user_info_from_payload(unverified_payload, token_type)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error extracting user from token: {e}")
        raise HTTPException(status_code=401, detail="Token validation failed")


def _handle_firebase_token_verification(payload: Dict[str, Any]) -> TokenVerificationResponse:
    """Handle Firebase token verification logic"""
    try:
        user_id = payload.get("user_id") or payload.get("sub")
        email = payload.get("email")
        expires_at = payload.get("exp")

        # Check if token is expired
        if expires_at and expires_at < datetime.now().timestamp():
            return TokenVerificationResponse(
                success=False,
                message="Firebase token has expired",
                valid=False,
                token_type=TokenType.FIREBASE,
                user_id=user_id,
                email=email,
                expires_at=expires_at
            )

        return TokenVerificationResponse(
            success=True,
            message="Firebase token is valid",
            valid=True,
            token_type=TokenType.FIREBASE,
            user_id=user_id,
            email=email,
            expires_at=expires_at
        )

    except Exception as e:
        return TokenVerificationResponse(
            success=False,
            message=f"Error validating Firebase token: {str(e)}",
            valid=False,
            token_type=TokenType.FIREBASE
        )


def _handle_custom_jwt_verification(token: str) -> TokenVerificationResponse:
    """Handle custom JWT token verification logic"""
    if not JWT_SECRET:
        return TokenVerificationResponse(
            success=False,
            message="JWT secret not configured on server",
            valid=False,
            token_type=TokenType.CUSTOM_JWT
        )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_email = payload.get("user_email")
        tenant_name = payload.get("tenant_name")

        return TokenVerificationResponse(
            success=True,
            message="Custom JWT token is valid",
            valid=True,
            token_type=TokenType.CUSTOM_JWT,
            user_id=tenant_name,
            email=user_email
        )

    except jwt.ExpiredSignatureError:
        return TokenVerificationResponse(
            success=False,
            message="Custom JWT token has expired",
            valid=False,
            token_type=TokenType.CUSTOM_JWT
        )
    except jwt.InvalidTokenError as e:
        return TokenVerificationResponse(
            success=False,
            message=f"Invalid custom JWT token: {str(e)}",
            valid=False,
            token_type=TokenType.CUSTOM_JWT
        )


@router.get("/verify-token", response_model=TokenVerificationResponse)
async def verify_token(request: Request):
    """
    Verify the JWT token from the Authorization header.
    Supports both Firebase JWT tokens and custom JWT tokens.

    Returns token validation status and user information if valid.
    """
    try:
        # Extract token from request
        try:
            token = extract_token_from_request(request)
        except HTTPException:
            return TokenVerificationResponse(
                success=False,
                message="No Authorization header or access-token provided",
                valid=False
            )

        # Decode token without verification to check structure
        try:
            unverified_payload = jwt.decode(
                token, options={"verify_signature": False})
        except jwt.DecodeError:
            return TokenVerificationResponse(
                success=False,
                message="Invalid token format",
                valid=False,
                token_type=TokenType.INVALID
            )

        # Determine token type and handle verification
        token_type = determine_token_type(unverified_payload)

        if token_type == TokenType.FIREBASE:
            return _handle_firebase_token_verification(unverified_payload)
        elif token_type == TokenType.CUSTOM_JWT:
            return _handle_custom_jwt_verification(token)
        else:
            return TokenVerificationResponse(
                success=False,
                message="Unknown token type",
                valid=False,
                token_type=TokenType.UNKNOWN
            )

    except Exception as e:
        print(f'Error verifying token: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify token: {str(e)}"
        )


@router.get("/token-info", response_model=Dict[str, Any])
async def get_token_info(request: Request):
    """
    Get detailed information about the token without full verification.
    Useful for debugging and token inspection.
    """
    try:
        # Extract token from request
        token = extract_token_from_request(request)

        # Decode without verification to get all payload information
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
        except jwt.DecodeError:
            raise HTTPException(status_code=400, detail="Invalid token format")

        # Get header information
        try:
            header = jwt.get_unverified_header(token)
        except Exception:
            header = {}

        return {
            "success": True,
            "header": header,
            "payload": payload,
            "message": "Token information extracted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f'Error getting token info: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get token info: {str(e)}"
        )

# Bio operation helper functions


def _create_new_bio_record(email: str, bio_request: UserBioRequest, timestamp: int) -> None:
    """Create new bio record with timestamps"""
    new_signup_data = {
        "email": email,
        "bio": bio_request.bio,
        "created_at": timestamp,
        "updated_at": timestamp
    }
    if bio_request.display_name:
        new_signup_data["display_name"] = bio_request.display_name
    if bio_request.avatar_url:
        new_signup_data["avatar_url"] = bio_request.avatar_url

    ConstellaSignup.update_user_info(email, new_signup_data)


def _update_existing_bio_record(email: str, bio_request: UserBioRequest,
                                signup_info: Dict[str, Any], timestamp: int) -> None:
    """Update existing bio record with new timestamp"""
    update_data = {
        "bio": bio_request.bio,
        "updated_at": timestamp
    }
    if bio_request.display_name:
        update_data["display_name"] = bio_request.display_name
    if bio_request.avatar_url:
        update_data["avatar_url"] = bio_request.avatar_url

    # For existing records without created_at, set it to current timestamp
    if not signup_info.get("created_at"):
        update_data["created_at"] = timestamp

    ConstellaSignup.update_user_info(email, update_data)


@router.post("/update-bio", response_model=UserBioResponse)
async def update_user_bio(
    bio_request: UserBioRequest,
    request: Request
):
    """
    Update user bio, display name, and avatar URL.
    Supports both Firebase and custom JWT tokens.
    """
    try:
        # Get current user from token
        current_user = await get_current_user_from_token(request)
        user_id = current_user["user_id"]
        email = current_user["email"]

        # Get current timestamp
        current_timestamp = get_current_timestamp_ms()

        # Get existing signup info
        signup_info = ConstellaSignup.get_user_info(email)

        # Create or update bio record
        if not signup_info:
            _create_new_bio_record(email, bio_request, current_timestamp)
        else:
            _update_existing_bio_record(
                email, bio_request, signup_info, current_timestamp)

        # Get the final data to return accurate timestamps
        final_signup_info = ConstellaSignup.get_user_info(email)

        return UserBioResponse(
            success=True,
            message="User bio updated successfully",
            user_id=user_id,
            email=email,
            bio=bio_request.bio,
            display_name=bio_request.display_name,
            avatar_url=bio_request.avatar_url,
            created_at=final_signup_info.get(
                "created_at") if final_signup_info else current_timestamp,
            updated_at=current_timestamp
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'Error updating user bio: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Error updating user bio: {str(e)}"
        )


@router.get("/get-bio", response_model=UserBioResponse)
async def get_user_bio(request: Request):
    """
    Get user bio, display name, and avatar URL.
    Supports both Firebase and custom JWT tokens.
    """
    try:
        # Get current user from token
        current_user = await get_current_user_from_token(request)
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

        return UserBioResponse(
            success=True,
            message="Bio information retrieved successfully",
            user_id=user_id,
            email=email,
            bio=signup_info.get("bio"),
            display_name=signup_info.get("display_name"),
            avatar_url=signup_info.get("avatar_url"),
            # None for legacy records
            created_at=signup_info.get("created_at"),
            # None for legacy records
            updated_at=signup_info.get("updated_at")
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'Error getting user bio: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user bio: {str(e)}"
        )
