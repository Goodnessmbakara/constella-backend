from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from pydantic import BaseModel
import traceback
import json

from ai.aury.analyzer import analyze_mbti_from_messages, MBTIProfile, MessageData

router = APIRouter(prefix="/aury/analysis", tags=["aury"])


class AnalysisRequest(BaseModel):
    """Request model for MBTI analysis"""
    messages: List[Dict[str, Any]]


class AnalysisResponse(BaseModel):
    """Response model for MBTI analysis"""
    success: bool
    profile: MBTIProfile = None
    error: str = None


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_mbti_personality(request: AnalysisRequest):
    """
    Analyze MBTI personality from message data
    
    This endpoint takes a list of message data and returns an MBTI personality analysis
    using OpenAI's structured output capabilities.
    
    Args:
        request: AnalysisRequest containing message data
        
    Returns:
        AnalysisResponse with either the MBTI profile or error information
    """
    try:
        # Validate that we have messages
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided for analysis")
        
        print(f"🔍 Received analysis request with {len(request.messages)} messages")
        
        # Validate message structure (basic validation)
        required_fields = ["text", "contact", "timestamp", "is_from_me"]
        for i, message in enumerate(request.messages[:5]):  # Check first 5 messages
            missing_fields = [field for field in required_fields if field not in message]
            if missing_fields:
                print(f"⚠️ Warning: Message {i} missing fields: {missing_fields}")
        
        # Analyze the messages using our analyzer
        profile = analyze_mbti_from_messages(request.messages)
        
        return AnalysisResponse(
            success=True,
            profile=profile
        )
        
    except Exception as e:
        print(f"❌ Error during MBTI analysis: {e}")
        traceback.print_exc()
        
        # Return error response instead of raising HTTP exception
        # This allows the client to handle errors gracefully
        return AnalysisResponse(
            success=False,
            error=str(e)
        )


@router.post("/validate-messages")
async def validate_message_format(request: AnalysisRequest):
    """
    Validate message format without running analysis
    
    Useful for testing message data structure before running expensive analysis
    """
    try:
        if not request.messages:
            return {
                "valid": False,
                "error": "No messages provided",
                "message_count": 0
            }
        
        required_fields = ["text", "contact", "timestamp", "is_from_me"]
        validation_results = []
        
        for i, message in enumerate(request.messages[:10]):  # Check first 10 messages
            missing_fields = [field for field in required_fields if field not in message]
            validation_results.append({
                "message_index": i,
                "valid": len(missing_fields) == 0,
                "missing_fields": missing_fields,
                "has_text": bool(message.get("text", "").strip()),
                "contact": message.get("contact", "Unknown")
            })
        
        # Count user messages
        user_message_count = sum(1 for msg in request.messages if msg.get("is_from_me", False))
        
        # Count valid conversations (contacts with at least 5 messages)
        contact_counts = {}
        for msg in request.messages:
            contact = msg.get("contact", "Unknown")
            if contact != "Unknown":
                contact_counts[contact] = contact_counts.get(contact, 0) + 1
        
        valid_conversations = sum(1 for count in contact_counts.values() if count >= 5)
        
        return {
            "valid": len([r for r in validation_results if r["valid"]]) == len(validation_results),
            "message_count": len(request.messages),
            "user_message_count": user_message_count,
            "valid_conversations": valid_conversations,
            "total_contacts": len(contact_counts),
            "validation_sample": validation_results,
            "top_contacts": sorted(contact_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "message_count": len(request.messages) if request.messages else 0
        }
