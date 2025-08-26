from os import getenv, path
import boto3
from botocore.signers import CloudFrontSigner
import rsa
import base64
from datetime import datetime, timedelta
from utils.constella.files.s3.s3_file_management import (get_cleaned_file_name,
	get_s3_path_for_tenant, get_temp_download_location)
from utils.constella.files.file_base64 import get_mime_type_from_file_type, remove_base64_prefix

boto_kwargs = {
	"aws_access_key_id": getenv("AWS_ACCESS_KEY_ID"),
	"aws_secret_access_key": getenv("AWS_SECRET_ACCESS_KEY"),
	"region_name": getenv("AWS_REGION"),
}

s3_client = boto3.Session(**boto_kwargs).client("s3")
s3 = boto3.resource('s3')

def rsa_signer(message):
	with open('./certs/cloudfront_private_key.pem', 'r') as key_file:
		private_key = key_file.read()
	return rsa.sign(
		message,
		rsa.PrivateKey.load_pkcs1(private_key.encode('utf8')),
		'SHA-1')  # CloudFront requires SHA-1 hash

# Key id is from AWS Dashboard Top Right -> Account Credentials -> CloudFront key pairs
cf_signer = CloudFrontSigner('APKA47CRYUHMW7O6CD7G', rsa_signer)

cloudfront_url_prefix = 'https://d29f4v4r8cofie.cloudfront.net/'

def sign_url(url: str):
	# get datetime 1 day from current time
	date_less_than = datetime.utcnow() + timedelta(days=1)

	if '?Expires=' in url:
		url = url.split('?Expires=')[0]

	# To sign with a canned policy::
	return cf_signer.generate_presigned_url(
		url, date_less_than=date_less_than)

def upload_file_bytes_to_s3(tenant_name, base_64, file_name, file_type, bucket="constella-users", slug: str = ''):
	"""Upload a file to an S3 bucket

	:param file_name: File to upload
	:param bucket: Bucket to upload to
	:param object_name: S3 object name. If not specified then file_name is used
	:return: True if file was uploaded, else False
	"""
	s3_client.put_object(Body=base64.b64decode(remove_base64_prefix(base_64)), Key=get_s3_path_for_tenant(tenant_name, file_name, file_type, slug), Bucket=bucket, ContentType=get_mime_type_from_file_type(file_type))
	return f'{cloudfront_url_prefix}{get_s3_path_for_tenant(tenant_name, file_name, file_type, slug)}'

def upload_file_to_s3(file_name, object_name=None, bucket="constella-users"):
	"""Upload a file to an S3 bucket

	:param file_name: File to upload
	:param bucket: Bucket to upload to
	:param object_name: S3 object name. If not specified then file_name is used
	:return: URL to the uploaded file
	"""
	# If S3 object_name was not specified, use file_name
	if object_name is None:
		object_name = file_name

	# Upload the file
	response = s3_client.upload_file(file_name, bucket, object_name)
	return f'https://d29f4v4r8cofie.cloudfront.net/{object_name if object_name else file_name}'

def delete_file_from_s3(file_name: str, bucket="constella-users"):
	"""Delete a file from an S3 bucket

	:param file_name: File to delete
	:param bucket: Bucket to delete from
	:return: True if file was deleted, else False
	"""
	try:
		# Remove the cloudfront URL prefix if it exists
		file_name = get_cleaned_file_name(file_name)
		
		# Delete the file from S3
		s3_client.delete_object(Bucket=bucket, Key=file_name)
		return True
	except Exception as e:
		print(e)
		return None

def get_file_url_from_path(tenant_name, file_name, file_type, slug: str = ''):
	return f'{cloudfront_url_prefix}{get_s3_path_for_tenant(tenant_name, file_name, file_type, slug)}'

def get_signed_file_url(file_url: str):
	return sign_url(file_url)


def download_video_from_s3(file_name, path_to_download_to="", bucket="constella-users"):
	"""Download a file from an S3 bucket

	:param file_name: File to download
	:param bucket: Bucket to download from
	:param object_name: S3 object name. If not specified then file_name is used
	:return: True if file was downloaded, else False
	"""
	try:
		# remove the cloudfront url if it exists
		file_name = get_cleaned_file_name(file_name)
		if not path_to_download_to:
			path_to_download_to = get_temp_download_location(file_name)
		
		# check if file already exists
		if path.exists(path_to_download_to):
			return path_to_download_to
		
		# Download the file
		s3_client.download_file(bucket, file_name, path_to_download_to)

		return path_to_download_to
	except Exception as e:
		print(e)
		return None


def remove_signed_params_from_url(url: str):
	try:
		# remove the signed params from the url
		url = url.split('?')[0]
		return url
	except Exception as e:
		print(e)
		return url

def delete_all_files_for_tenant(tenant_name: str, bucket="constella-users"):
	"""Delete all files for a specific tenant from S3 bucket
	
	:param tenant_name: The tenant name to delete files for
	:param bucket: Bucket to delete from
	:return: Dictionary with success count and any errors
	"""
	try:
		if not tenant_name or len(tenant_name) < 1:
			return {
				'success': False,
				'deleted_count': 0,
				'errors': ['Tenant name is required']
			}
		
		# The prefix for all tenant files based on get_s3_path_for_tenant structure
		prefix = f'constella/heytenants/{tenant_name}/'
		
		deleted_count = 0
		errors = []
		
		# Get the bucket resource
		bucket_resource = s3.Bucket(bucket)
		
		# Delete all objects with the tenant prefix
		for obj in bucket_resource.objects.filter(Prefix=prefix):
			try:
				s3.Object(bucket, obj.key).delete()
				deleted_count += 1
			except Exception as e:
				errors.append(f"Error deleting {obj.key}: {str(e)}")
		
		return {
			'success': True,
			'deleted_count': deleted_count,
			'errors': errors
		}
		
	except Exception as e:
		return {
			'success': False,
			'deleted_count': 0,
			'errors': [f"Error listing/deleting tenant files: {str(e)}"]
		}
