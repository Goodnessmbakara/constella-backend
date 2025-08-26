from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Optional
import os
from utils.notifs import send_ios_image_notification

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
)

class IOSImageNotificationRequest(BaseModel):
    token: str
    title: str
    body: str
    image_url: str
    image_data: Optional[Dict] = None
    additional_data: Optional[Dict] = None
    link: Optional[str] = None

@router.post("/ios/image")
async def send_ios_image_notification_route(notification_request: IOSImageNotificationRequest, request: Request):
    """
    Send an image notification to an iOS device using FCM.
    
    The image_url must be a publicly accessible URL.
    For iOS, the notification service extension must be set up in the app to handle the image.
    
    If link is provided, clicking the notification will open that URL in the app or browser.
    """
    try:
        # Validate the token
        if not notification_request.token:
            raise HTTPException(status_code=400, detail="Device token is required")
        
        # Validate the image URL
        if not notification_request.image_url:
            raise HTTPException(status_code=400, detail="Image URL is required")
        
        # Send the notification
        response = send_ios_image_notification(
            token=notification_request.token,
            title=notification_request.title,
            body=notification_request.body,
            image_url=notification_request.image_url,
            image_data=notification_request.image_data,
            data=notification_request.additional_data,
            link=notification_request.link
        )
        
        if not response:
            raise HTTPException(status_code=500, detail="Failed to send notification")
        
        return {"message": "Notification sent successfully", "message_id": response}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")

class StandardNotificationRequest(BaseModel):
    token: str
    title: str
    body: str
    data: Optional[Dict] = None
    click_action: Optional[str] = None
    link: Optional[str] = None

@router.post("/standard")
async def send_standard_notification_route(notification_request: StandardNotificationRequest, request: Request):
    """
    Send a standard notification to a device using FCM.
    
    You can specify:
    - click_action: An action identifier for Android to open a specific activity
    - link: A URL that will be opened when the notification is clicked
    """
    from utils.notifs import send_notification
    
    try:
        # Validate the token
        if not notification_request.token:
            raise HTTPException(status_code=400, detail="Device token is required")
        
        # Send the notification
        response = send_notification(
            token=notification_request.token,
            title=notification_request.title,
            body=notification_request.body,
            data=notification_request.data,
            click_action=notification_request.click_action,
            link=notification_request.link
        )
        
        if not response:
            raise HTTPException(status_code=500, detail="Failed to send notification")
        
        return {"message": "Notification sent successfully", "message_id": response}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}") 