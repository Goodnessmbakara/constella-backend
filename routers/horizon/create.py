from datetime import datetime
import time
import json
from utils.notifs import send_ios_image_notification
from weaviate.exceptions import UnexpectedStatusCodeError
import fastapi
from fastapi import BackgroundTasks
from weaviate.classes.query import Filter, MetadataQuery
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import traceback
import sentry_sdk
from typing import List, Dict, Any, Optional
from db.weaviate.operations.general import (delete_all_records, delete_record,
	delete_records_by_ids, get_most_recent_records, get_record_by_id, get_records_by_ids,
	insert_record, query_by_filter, query_by_keyword, query_by_keyword_with_filter, query_by_vector,
	query_by_vector_with_filter, update_record_metadata, update_record_vector, upsert_records)
from ai.embeddings import create_embedding, create_file_embedding, get_image_to_text
from db.weaviate.records.note import WeaviateNote
from db.models.constella.long_job import LongJob
from constants import default_query_limit, image_note_prefix
from utils.constella.files.file_base64 import clean_base64
from utils.constella.files.s3.s3 import (get_file_url_from_path, get_signed_file_url,
	upload_file_bytes_to_s3, remove_signed_params_from_url)
from db.models.constella.constella_retry_queue import RetryQueue
from utils.constella.files.s3.s3_file_management import cloudfront_url_prefix
from ai.vision.images import (format_ocr_json_to_string, image_matches_instruction,
	openai_ocr_image_to_text)
from ai.stella.prompts import get_system_prompt
from ai.ai_api import stream_anthropic_response, stream_google_response, create_google_request
from fastapi import WebSocket, WebSocketDisconnect
from ai.horizon.assist_ai import get_horizon_system_prompt, parse_horizon_frontend_messages
import re
import uuid
from db.weaviate.operations.tag_ops import get_all_tags
from ai.tags.auto_tag import get_auto_tags_with_objects


router = APIRouter(
	prefix="/horizon/create",
	tags=["horizon_assist"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)


class HorizonNoteIn(BaseModel):
	title: str
	tenant_name: str


@router.post("/note")
async def create_horizon_note(note_in: HorizonNoteIn):
	try:
		# Create minimal record with just title
		record = {
			"title": note_in.title,
			"content": "",
			"fileData": "",
			"fileType": "",
			"fileText": "",
			"imageCaption": "",
			"lastUpdateDevice": "horizon",
			"lastUpdateDeviceId": "horizon",
			"uniqueid": str(uuid.uuid4()),
			"vector": create_embedding(note_in.title)
		}

		record["tags"] = get_auto_tags_with_objects(note_in.title, note_in.tenant_name)
		
		uniqueid = insert_record(note_in.tenant_name, WeaviateNote.from_rxdb(record))
		return {"success": True, "uniqueid": uniqueid}
	except Exception as e:
		traceback.print_exc()
		# Add to retry queue
		retry_parameters = {
			"tenant_name": note_in.tenant_name,
			"title": note_in.title
		}
		RetryQueue.create("horizon_create_note", retry_parameters)
		raise HTTPException(
			status_code=500,
			detail=str(e)
		)