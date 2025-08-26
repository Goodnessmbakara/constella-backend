from db.models.constella.deleted_record import DeletedRecord
import boto3


# Initialize S3 client
s3_client = boto3.client('s3')

def cleanup_old_deleted_records():
	"""
	Cleanup function to delete old records and their corresponding S3 files
	"""
	try:
		old_records = DeletedRecord.get_old_records_with_s3_path()
		for record in old_records:
			if record.get('s3_path'):
				# Extract bucket and key from s3_path
				s3_path = record['s3_path']
				# Assuming s3_path is in format 'bucket_name/path/to/file'
				bucket_name = 'constella-users'

				
				try:
					# Delete from S3
					s3_client.delete_object(Bucket=bucket_name, Key=s3_path)
					if s3_path.endswith('.jpeg'):
						jpg_path = s3_path[:-5] + '.jpg'
						try:
							s3_client.delete_object(Bucket=bucket_name, Key=jpg_path)
						except Exception as e:
							print(f"Error deleting jpg version: {e}")
				
				except Exception as e:
					print(f"Error deleting S3 object {s3_path}: {e}")

	except Exception as e:
		print(f"Error in cleanup job: {e}")
