from fastapi import APIRouter, WebSocketDisconnect, HTTPException, Request, WebSocket

from pydantic import BaseModel
from typing import List
import csv
import io
import os
import firebase_admin
from firebase_admin import auth
from db.weaviate.weaviate_client import delete_tenant
from utils.constella.files.s3.s3 import delete_all_files_for_tenant
import traceback

router = APIRouter(
	prefix="/admin",
	tags=["admin"],
)

class DeleteAccountsResponse(BaseModel):
	success_count: int
	failed_emails: List[str]
	errors: List[str]
	s3_deletion_summary: dict

@router.post("/delete-accounts", response_model=DeleteAccountsResponse)
async def delete_accounts():
	"""
	Delete user accounts from Firebase and Weaviate using emails.csv file at root.
	CSV should have emails in the first column.
	"""
	try:
		# Read the CSV file from root directory
		csv_file_path = "emails.csv"

		print("Deleting accounts")
		
		if not os.path.exists(csv_file_path):
			raise HTTPException(status_code=404, detail="emails.csv file not found at root directory")
		
		with open(csv_file_path, 'r', encoding='utf-8') as file:
			csv_reader = csv.reader(file)
			
			success_count = 0
			failed_emails = []
			errors = []
			s3_deletion_summary = {
				'total_files_deleted': 0,
				'tenant_deletions': [],
				'errors': []
			}
			
			for row in csv_reader:
				if not row or not row[0].strip():
					continue
					
				email = row[0].strip()
				
				try:
					# email lower case
					email = email.lower()
					
					# Look up Firebase auth ID
					user = auth.get_user_by_email(email)
					user_id = user.uid
					
					# Delete S3 files for the tenant
					try:
						if user_id:
							s3_result = delete_all_files_for_tenant(user_id)
							s3_deletion_summary['tenant_deletions'].append({
								'tenant_id': user_id,
								'email': email,
								'files_deleted': s3_result.get('deleted_count', 0),
								'success': s3_result.get('success', False),
								'errors': s3_result.get('errors', [])
							})
							s3_deletion_summary['total_files_deleted'] += s3_result.get('deleted_count', 0)
							if s3_result.get('errors'):
								s3_deletion_summary['errors'].extend([f"{email}: {error}" for error in s3_result.get('errors', [])])
					except Exception as e:
						error_msg = f"Error deleting S3 files for {email} (user_id: {user_id}): {str(e)}"
						s3_deletion_summary['errors'].append(error_msg)
						print(error_msg)
					
					# Delete tenant in Weaviate
					try:
						if user_id:
							delete_tenant(user_id)  # Using email as tenant name based on context
					except Exception as e:
						print(f"Error deleting Weaviate tenant for {email} and user_id {user_id}: {e}")
						# Continue with Firebase deletion even if Weaviate fails
					
					# Delete user in Firebase
					auth.delete_user(user_id)
					
					success_count += 1
					print(f"Successfully deleted account for {email}")
					
				except auth.UserNotFoundError:
					failed_emails.append(email)
					errors.append(f"User not found in Firebase: {email}")
					print(f"User not found in Firebase: {email}")
				except Exception as e:
					failed_emails.append(email)
					error_msg = f"Error deleting {email}: {str(e)}"
					errors.append(error_msg)
					print(error_msg)
					traceback.print_exc()
		
		return DeleteAccountsResponse(
			success_count=success_count,
			failed_emails=failed_emails,
			errors=errors,
			s3_deletion_summary=s3_deletion_summary
		)
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error processing emails.csv file: {str(e)}")

if __name__ == "__main__":
	delete_accounts()