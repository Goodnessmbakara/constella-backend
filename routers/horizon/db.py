from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from bson.objectid import ObjectId

from db.mongodb import db
from utils.json import parse_json

# MongoDB collection dedicated to Horizon chats
collection = db["horizon_chats"]

router = APIRouter(
	prefix="/horizon/chat",
	tags=["horizon_chat"],
)

class Message(BaseModel):
	role: str = Field(..., description="Role of the message sender, e.g. 'user' or 'assistant'")
	content: str = Field(..., description="Content of the message")

class CreateChatRequest(BaseModel):
	tenant_name: str = Field(..., description="Tenant identifier")
	title: str
	messages: List[Message] = []

class AddMessageRequest(BaseModel):
	tenant_name: str = Field(..., description="Tenant identifier")
	chat_id: str = Field(..., description="MongoDB _id of the chat as string")
	message: Message

class RenameChatRequest(BaseModel):
	tenant_name: str = Field(..., description="Tenant identifier")
	chat_id: str
	new_title: str

@router.post("/create")
def create_chat(req: CreateChatRequest):
	"""Create a new Horizon chat and return the stored record."""
	chat_doc: Dict[str, Any] = {
		"created": datetime.utcnow(),
		"lastModified": datetime.utcnow(),
		"tenantName": req.tenant_name,
		"title": req.title,
		"messages": [m.dict() for m in req.messages],
	}
	insert_result = collection.insert_one(chat_doc)
	return parse_json(collection.find_one({"_id": insert_result.inserted_id}))

@router.post("/add-message")
def add_message(req: AddMessageRequest):
	"""Append a message to an existing chat and return the updated record."""
	try:
		collection.update_one(
			{"_id": ObjectId(req.chat_id), "tenantName": req.tenant_name},
			{"$push": {"messages": req.message.dict()}, "$set": {"lastModified": datetime.utcnow()}},
		)
		return parse_json(collection.find_one({"_id": ObjectId(req.chat_id), "tenantName": req.tenant_name}))
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

@router.post("/rename")
def rename_chat(req: RenameChatRequest):
	"""Rename an existing chat and return the updated record."""
	try:
		collection.update_one(
			{"_id": ObjectId(req.chat_id), "tenantName": req.tenant_name},
			{"$set": {"title": req.new_title, "lastModified": datetime.utcnow()}},
		)
		return parse_json(collection.find_one({"_id": ObjectId(req.chat_id), "tenantName": req.tenant_name}))
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

@router.get("/search")
def search_chats(query: str, tenant_name: str):
	"""Search chats by title (case-insensitive substring match)."""
	try:
		cursor = collection.find({"tenantName": tenant_name, "title": {"$regex": query, "$options": "i"}})
		return [parse_json(item) for item in cursor]
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))
