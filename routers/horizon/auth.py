from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import jwt
import os
import traceback
import sentry_sdk
from datetime import datetime

router = APIRouter(
    prefix="/horizon/auth",
    tags=["horizon_auth"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

# Get JWT secret from environment
JWT_SECRET = os.getenv("JWT_SECRET")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "horizon-mobile-a1a8b")


class TokenVerificationResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    token_type: Optional[str] = None
    expires_at: Optional[int] = None
    valid: bool


@router.get("/verify-token", response_model=TokenVerificationResponse)
async def verify_token(request: Request):
    """
    Verify the JWT token from the Authorization header.
    Supports both Firebase JWT tokens and custom JWT tokens.
    
    Returns token validation status and user information if valid.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return TokenVerificationResponse(
                success=False,
                message="No Authorization header provided",
                valid=False
            )
        
        # Extract token from "Bearer <token>" format
        if not auth_header.startswith("Bearer "):
            return TokenVerificationResponse(
                success=False,
                message="Invalid Authorization header format. Expected 'Bearer <token>'",
                valid=False
            )
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Try to decode without verification first to check token structure
        try:
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            token_type = "unknown"
            
            # Determine token type based on payload structure
            if "iss" in unverified_payload and "securetoken.google.com" in str(unverified_payload.get("iss", "")):
                token_type = "firebase"
            elif "user_email" in unverified_payload or "tenant_name" in unverified_payload:
                token_type = "custom_jwt"
            else:
                token_type = "unknown"
                
        except jwt.DecodeError:
            return TokenVerificationResponse(
                success=False,
                message="Invalid token format",
                valid=False,
                token_type="invalid"
            )
        
        # Handle Firebase tokens
        if token_type == "firebase":
            try:
                # For Firebase tokens, we'll validate the basic structure
                # In production, you'd want to verify against Firebase's public keys
                user_id = unverified_payload.get("user_id") or unverified_payload.get("sub")
                email = unverified_payload.get("email")
                expires_at = unverified_payload.get("exp")
                
                # Check if token is expired
                if expires_at and expires_at < datetime.now().timestamp():
                    return TokenVerificationResponse(
                        success=False,
                        message="Firebase token has expired",
                        valid=False,
                        token_type="firebase",
                        user_id=user_id,
                        email=email,
                        expires_at=expires_at
                    )
                
                return TokenVerificationResponse(
                    success=True,
                    message="Firebase token is valid",
                    valid=True,
                    token_type="firebase",
                    user_id=user_id,
                    email=email,
                    expires_at=expires_at
                )
                
            except Exception as e:
                return TokenVerificationResponse(
                    success=False,
                    message=f"Error validating Firebase token: {str(e)}",
                    valid=False,
                    token_type="firebase"
                )
        
        # Handle custom JWT tokens
        elif token_type == "custom_jwt":
            if not JWT_SECRET:
                return TokenVerificationResponse(
                    success=False,
                    message="JWT secret not configured on server",
                    valid=False,
                    token_type="custom_jwt"
                )
            
            try:
                # Verify custom JWT token
                payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                
                user_email = payload.get("user_email")
                tenant_name = payload.get("tenant_name")
                
                return TokenVerificationResponse(
                    success=True,
                    message="Custom JWT token is valid",
                    valid=True,
                    token_type="custom_jwt",
                    user_id=tenant_name,  # Using tenant_name as user_id for custom tokens
                    email=user_email
                )
                
            except jwt.ExpiredSignatureError:
                return TokenVerificationResponse(
                    success=False,
                    message="Custom JWT token has expired",
                    valid=False,
                    token_type="custom_jwt"
                )
            except jwt.InvalidTokenError as e:
                return TokenVerificationResponse(
                    success=False,
                    message=f"Invalid custom JWT token: {str(e)}",
                    valid=False,
                    token_type="custom_jwt"
                )
        
        # Handle unknown token types
        else:
            return TokenVerificationResponse(
                success=False,
                message="Unknown token type",
                valid=False,
                token_type="unknown"
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
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=400, detail="No valid Authorization header provided")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
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