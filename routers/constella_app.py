from datetime import datetime
import json
from fastapi import APIRouter, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from fastapi import WebSocket
from ai.ai_api import stream_anthropic_response, stream_google_response, stream_openai_response
import requests
from typing import List, Dict, Optional
from utils.constella.stella_chat import (get_google_model_based_on_context_size,
	parse_frontend_messages)
from ai.stella.prompts import (get_system_prompt, stella_calling_realtime_instructions,
	stella_calling_realtime_max_tokens)
import jwt
import os
from db.models.constella.constella_shared_view import ConstellaSharedView
from fastapi.responses import JSONResponse
import traceback
from utils.loops import create_loops_contact, send_transactional_email
from db.weaviate.weaviate_client import delete_tenant

router = APIRouter(
	prefix="/constella-app",
	tags=["constella-app"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

secret_key = os.getenv("JWT_SECRET")

class GetJWTReq(BaseModel):
	user_id: str

class SaveSharedViewReq(BaseModel):
	sharing_user_email: str
	shared_view_data: Dict
	shared_url: str | None = None
	view_id: Optional[str] = None

class GetSharedViewReq(BaseModel):
	id: str

class DeleteSharedViewReq(BaseModel):
	id: str

@router.post("/get-jwt")
async def get_jwt(get_jwt_req: GetJWTReq):
	"""
	Gets a secure JWT token for TipTap to use for authentication.
	"""
	try:
		# Create the payload
		payload = {
			'sub': get_jwt_req.user_id,
			'allowedDocumentNames': [ get_jwt_req.user_id + '/*'],
		}
		
		# Get the secret key from environment variable
		if not secret_key:
			raise HTTPException(status_code=500, detail="JWT secret key not configured")
		
		# Generate the JWT token
		token = jwt.encode(payload, secret_key, algorithm="HS256")
		
		return {"token": token}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error generating JWT: {str(e)}")
	
@router.post("/save-shared-view")
async def save_shared_view(req: SaveSharedViewReq):
	try:
		# If view id is provided, attempt to update the existing shared view
		if req.view_id:
			success = ConstellaSharedView.update_by_id(req.view_id, {
				"shared_view_data": req.shared_view_data,
			})
			if success:
				return {
					"_id": req.view_id,
				}
			# Otherwise, proceed to save new shared view
		shared_view = ConstellaSharedView(
			sharing_user_email=req.sharing_user_email,
			shared_view_data=req.shared_view_data,
			shared_url=req.shared_url
		)
		result = shared_view.save()
		return {
			"_id": result.get('_id', ''),
		}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error saving shared view: {str(e)}")

@router.post("/get-shared-view")
async def get_shared_view(req: GetSharedViewReq):
	try:
		result = ConstellaSharedView.get_by_id(req.id)
		if result is None:
			raise HTTPException(status_code=404, detail="Shared view not found")
		return JSONResponse(content=result, media_type="application/json")
	except Exception as e:
		print(e)
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error retrieving shared view: {str(e)}")

@router.post("/delete-shared-view")
async def delete_shared_view(req: DeleteSharedViewReq):
	try:
		success = ConstellaSharedView.delete_by_id(req.id)
		if not success:
			raise HTTPException(status_code=404, detail="Shared view not found")
		return {"message": "Shared view deleted successfully"}
	except Exception as e:
		print(e)
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error deleting shared view: {str(e)}")
	
def log_messages(messages: list, system_prompt: str, think_mode: str, deep_think: bool):
	# Log the messages for debugging purposes
	try:
		# Create logs directory if it doesn't exist
		import os
		from datetime import datetime
		
		logs_dir = "logs"
		if not os.path.exists(logs_dir):
			os.makedirs(logs_dir)
		
		# Create timestamp for the log file
		timestamp = datetime.now().strftime("%H-%M-%S")
		log_file_path = f"{logs_dir}/{timestamp}.json"
		
		# Write messages to log file
		with open(log_file_path, "w") as log_file:
			print("writing to log file: ", log_file_path)
			log_data = {
				"timestamp": datetime.now().isoformat(),
				"messages": messages,
				"system_prompt": system_prompt,
				"think_mode": think_mode,
				"deep_think": deep_think
			}
			json.dump(log_data, log_file, indent=2)
	except Exception as log_error:
		print(f"Error logging messages: {log_error}")

@router.websocket("/stream-chat-request")
async def websocket_endpoint(websocket: WebSocket):
	await websocket.accept()
	try:
		print('RECEIVED')

		while True:
			# Assuming req is received from the WebSocket connection
			req = await websocket.receive_json()

			print("CALLING")
			
			# If init key in request, then send init message
			if 'init' in req:
				await websocket.send_text('|INIT|')
				continue
			
			deep_think = req.get('deep_think', False)
			think_mode = req.get('think_mode', '')
			edges_data = req.get('edges_data', {})
			daily_note_data = req.get('daily_note_data', None)

			try:
				# If deep_think is requested, deliberately trigger the exception handler
				if deep_think:
					raise Exception("Deliberately using Anthropic for deep thinking")
				
				messages, chars_in_context = parse_frontend_messages(req['messages'], req['graph_nodes'], model="google", edges_data=edges_data, daily_note_data=daily_note_data)			
				system_prompt = get_system_prompt(messages)
				
				for word in stream_google_response(
					messages,
					max_tokens=req['max_tokens'],
					system_prompt=system_prompt,
					model=get_google_model_based_on_context_size(chars_in_context)
				):
					await websocket.send_text(word)
			except Exception as e:
				# Only print the error if it's not the deliberate deep_think case
				if not deep_think:
					print('Error in stream google response: ', e)
				
				# Try anthropic as a backup (or as primary for deep_think)
				messages, chars_in_context = parse_frontend_messages(req['messages'], req['graph_nodes'], model="anthropic", edges_data=edges_data, daily_note_data=daily_note_data, deep_think=deep_think)
				system_prompt = get_system_prompt(messages)


				for word in stream_anthropic_response(
					messages,
					max_tokens=req['max_tokens'],
					system_prompt=system_prompt,
					thinking_enabled=deep_think
				):
					await websocket.send_text(word)

	except WebSocketDisconnect as e:
		pass
	except Exception as e:
		print('Error in stream chat request: ', e)
		await websocket.send_json({"error": str(e)})

class GetEphemeralKeyReq(BaseModel):
	user_id: str

default_data = {
	'instructions': stella_calling_realtime_instructions,
	'max_tokens': stella_calling_realtime_max_tokens,
	'client_secret': {
		'value': os.getenv('OPENAI_CLIENT_SECRET', '')
	}
}

@router.post("/get-ephemeral-key")
async def get_ephemeral_key(req: GetEphemeralKeyReq):
	"""
	Gets an ephemeral key for real-time API access.
	"""
	try:
		try:
			response = requests.post(
				"https://api.openai.com/v1/realtime/sessions",
				headers={
					"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
					"Content-Type": "application/json"
				},
				json={
					"model": "gpt-4o-mini-realtime-preview",
					# "voice": "sage"
				}
			)
		except Exception as e:
			print(f"Error getting ephemeral key: {e}")
			return default_data
			
		if response.status_code != 200:
			print(f"Failed to get ephemeral key. Status code: {response.status_code}")
			print(f"Response: {response.text}")
			return default_data
			
		response_json = response.json()
		response_json['instructions'] = stella_calling_realtime_instructions
		response_json['max_tokens'] = stella_calling_realtime_max_tokens
		return response_json
		
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, 
						  detail=f"Error generating ephemeral key: {str(e)}")


class SendDesktopDownloadEmailReq(BaseModel):
	email: str

@router.post("/send-desktop-download-email")
async def send_desktop_download_email_route(req: SendDesktopDownloadEmailReq):
	"""
	Sends a transactional email via Loops.
	"""
	try:
		send_transactional_email(
			email=req.email,
			transactional_id="cm70vxp1100ktt50z873qz723", 
		)
		try:
			create_loops_contact(email=req.email, user_id='', first_name='', auth_user_id='')
		except Exception as e:	
			print(f"Error creating loops contact: {e}")
		return {"status": "success"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500,
						  detail=f"Error sending transactional email: {str(e)}")

class DeleteTenantReq(BaseModel):
	auth_user_id: str

@router.post("/delete-tenant")
async def delete_tenant_route(req: DeleteTenantReq):
	"""
	Deletes a tenant from Weaviate based on auth_user_id.
	"""
	try:
		if not req.auth_user_id:
			raise HTTPException(status_code=400, detail="auth_user_id is required")
		
		# Use the auth_user_id as the tenant name
		tenant_name = req.auth_user_id
		
		# Check if tenant exists and delete it
		try:
			delete_tenant(tenant_name)
			return {"status": "success", "message": f"Tenant {tenant_name} deleted successfully"}
		except Exception as e:
			print(f"Error deleting tenant {tenant_name}: {e}")
			raise HTTPException(status_code=404, detail=f"Tenant {tenant_name} not found or could not be deleted")
	
	except HTTPException as he:
		# Re-raise HTTP exceptions
		raise he
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error deleting tenant: {str(e)}")

class UpdateEmbeddedBodiesStatusReq(BaseModel):
	subscription_id: str
	status: str

@router.post("/update-embedded-bodies-status")
async def update_embedded_bodies_status(req: UpdateEmbeddedBodiesStatusReq):
	"""
	Updates the embedded_bodies_status for a subscription.
	"""
	try:
		if not req.subscription_id:
			raise HTTPException(status_code=400, detail="subscription_id is required")
		if not req.status:
			raise HTTPException(status_code=400, detail="status is required")
		
		from db.models.constella.constella_subscription import ConstellaSubscription
		
		success = ConstellaSubscription.set_embedded_bodies_status(req.subscription_id, req.status)
		if not success:
			raise HTTPException(status_code=404, detail=f"Subscription with ID {req.subscription_id} not found")
		
		return {"status": "success", "message": f"Embedded bodies status updated to {req.status}"}
	
	except HTTPException as he:
		# Re-raise HTTP exceptions
		raise he
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error updating embedded bodies status: {str(e)}")


