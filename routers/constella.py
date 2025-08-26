from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from ai.ai_api import (create_chat_completion, create_chat_message)

from db.models.constella.constella_signup import ConstellaSignup
from utils.loops import create_loops_contact, update_contact_property, send_event
from db.models.constella.constella_feature_request import ConstellaFeatureRequest
from db.models.constella.constella_auth import ConstellaAuth
from utils.constella.files.s3.s3 import sign_url


router = APIRouter(
    prefix="/constella",
    tags=["constella"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

# create post route to create sign up

class CreateSignUpReq(BaseModel):
	email: str
	is_mobile: bool = False
	mailing_lists: Optional[List[str]] = []

@router.post("/create-signup")
async def create_signup(req: CreateSignUpReq):
	try:
		user_info = ConstellaSignup(email=req.email)
		user_info.save()
		create_loops_contact(email=req.email, user_id='', mailing_lists=req.mailing_lists)
		if req.is_mobile:
			send_event(email=req.email, event_name="Mobile Signup", user_id='')
		else:
			send_event(email=req.email, event_name="Signup", user_id='')
		return {"success": "User signed up successfully"}
	except Exception as e:
		print(e)
		return {"error": str(e)}

class SubmitFeatureRequest(BaseModel):
	request_text: str
	ip_address: str

class UpdateUserProperty(BaseModel):
	email: str
	property_name: str
	property_value: str

@router.post("/update-user-property")
async def mark_platform(req: UpdateUserProperty):
	try:
		update_contact_property(email=req.email, property_name=req.property_name, property_value=req.property_value)
		return {"success": "Property updated"}
	except Exception as e:
		print(e)
		return {"error": str(e)}

class MarkPlatformReq(BaseModel):
	email: str
	platform: str

@router.post("/mark-platform")
async def mark_platform(req: MarkPlatformReq):
	try:
		ConstellaSignup.add_platform(req.email, req.platform)
		update_contact_property(email=req.email, property_name="platforms", property_value=req.platform)
		return {"success": "Platform marked"}
	except Exception as e:
		print(e)
		return {"error": str(e)}

class SetLoopsPropertyReq(BaseModel):
	email: str
	property_name: str
	property_value: str

@router.post("/set-loops-property")
async def mark_platform(req: SetLoopsPropertyReq):
	try:
		update_contact_property(email=req.email, property_name=req.property_name, property_value=req.property_value)
		return {"success": "Platform marked"}
	except Exception as e:
		print(e)
		return {"error": str(e)}

@router.post("/submit-feature-request")
async def create_signup(req: SubmitFeatureRequest):
	try:
		# check the number of ip addresses first before submitting
		feature_requests = ConstellaFeatureRequest.get_by_ip(ip_address=req.ip_address)
		if len(feature_requests) > 10:
			return {"error": "You can only submit 10 feature requests!"}
		feature_request = ConstellaFeatureRequest(request_text=req.request_text, ip_address=req.ip_address)
		feature_request = feature_request.save()
		return {"feature_request": feature_request}
	except Exception as e:
		print(e)
		return {"error": str(e)}

@router.post("/get-feature-requests")
async def get_feature_requests():
	try:
		feature_requests = ConstellaFeatureRequest.get_all()
		return {"feature_requests": feature_requests}
	except Exception as e:
		print(e)
		return {"error": str(e)}

class VoteFeatureRequest(BaseModel):
	feature_request_id: str
	vote_change: int

@router.post("/vote-feature-request")
async def vote_feature_request(req: VoteFeatureRequest):
	try:
		ConstellaFeatureRequest.adjust_votes(_id=req.feature_request_id, vote_change=req.vote_change)
		return {"success": "Request Submitted"}
	except Exception as e:
		print(e)
		return {"error": str(e)}


class LandingPageChat(BaseModel):
	query: str
	max_tokens: int = 100

@router.post("/landing-page-chat")
async def landing_page_chat(req: LandingPageChat):
	try:
		system_prompt = """
			You are Constella. You are a revolutionary way to take notes and manage all the learnings of the user. 
			You are extremely innovative and no one is like you. Your features are:
			1. Take notes on a graph-first infinite canvas that rearranges itself as you type
			2. When a user is typing in a new note, similar notes are suggested. This allows users to form connections.
			3.Users can drag and drop to create connections between notes.
			4. The connections are also remembered and retrieved when similar notes are shown.
			5. Users can mind map by taking notes on the graph and creating connections to visualize.
			6. The graph automatically automatically adjusts each time something is typed.
			7. It is great for retrieving knowledge. Old notes never have to get lost since you retrieve old notes based on the context.

			The user is going to ask you a question for further clarification, please respond to them.
			Do not use bullet points or lists, write a paragraph with proper grammar and punctuation. Do not ask any questions.
			Keep your response brief and limit it to a maximum of 4 sentences. 
		"""
		response = create_chat_completion(
			[
				create_chat_message("system",  system_prompt),
				create_chat_message("user", req.query)
			],
			max_tokens=req.max_tokens
		)
		# response = create_inflection_request(system_prompt)
		return {"response": response}
	except Exception as e:
		print(e)
		return {"error": str(e)}


class CheckAuthStatusReq(BaseModel):
    auth_req_id: str

class UpdateAuthReq(BaseModel):
    auth_req_id: str
    auth_user_id: str
    auth_email: str

class GetDesktopDownloadLinksReq(BaseModel):
	mac_silicon_version: str
	mac_intel_version: str
	windows_version: str

@router.post("/check-auth-status")
async def check_auth_status(req: CheckAuthStatusReq):
    try:
        auth_info = ConstellaAuth.get_auth_info(req.auth_req_id)
        if auth_info:
            return {
                "auth_user_id": auth_info.get("auth_user_id") or None,
                "auth_email": auth_info.get("auth_email") or None
            }
        return {"auth_user_id": None, "auth_email": None}
    except Exception as e:
        print(e)
        return {"error": str(e)}

@router.post("/update-auth")
async def update_auth(req: UpdateAuthReq):
    try:
        auth_info = ConstellaAuth.get_auth_info(req.auth_req_id)
        if auth_info:
            ConstellaAuth.update_one(req.auth_req_id, req.auth_user_id, req.auth_email)
            return {"success": "Auth updated successfully"}
        return {"error": "Auth request not found"}
    except Exception as e:
        print(e)
        return {"error": str(e)}


@router.post("/get-desktop-download-links")
async def get_download_links(req: GetDesktopDownloadLinksReq):
	try:
		MAC_SILICON_DOWNLOAD_LINK = f"https://d1o7k6e9m830r9.cloudfront.net/constella/publish/Constella-{req.mac_silicon_version}-arm64.dmg"
		MAC_OTHER_DOWNLOAD_LINK = f"https://d1o7k6e9m830r9.cloudfront.net/constella/publish/mac-intel/Constella-{req.mac_intel_version}.dmg"
		WINDOWS_DOWNLOAD_LINK = f"https://d1o7k6e9m830r9.cloudfront.net/constella/publish/win/Constella Setup {req.windows_version}.exe"
		
		return {
			"mac_silicon": sign_url(MAC_SILICON_DOWNLOAD_LINK),
			"mac_intel": sign_url(MAC_OTHER_DOWNLOAD_LINK),
			"windows": sign_url(WINDOWS_DOWNLOAD_LINK)
		}
	except Exception as e:
		print(e)
		return {"error": str(e)}