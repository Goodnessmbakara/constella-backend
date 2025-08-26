from datetime import datetime
from db.weaviate.operations.general import sync_by_last_modified
from utils.constella.syncing.integrations.integration_helper import sync_integrations_for_user
from db.models.constella.long_job import LongJob

def sync_everything_for_user(tenant_name: str, last_sync_datetime_utc: datetime, curr_device_id: str, user_email: str, long_job_id: str):
	"""
	Syncs all records and integrations for a user.
	1. Syncs all records from Weaviate since last sync time
	2. Syncs all integrations for the user
	Finally updates the long job status with all the results (the notes field)
	"""
	results = []
	try:
		# { results: [...], deleted_results: [...] }
		results = sync_by_last_modified(tenant_name, last_sync_datetime_utc, curr_device_id)
		integration_results = sync_integrations_for_user(tenant_name, user_email)
		results['results'].extend(integration_results)
	except Exception as e:
		raise e
	finally:
		print('updating long job status with id: ' + long_job_id)
		LongJob.update_status(long_job_id, 'completed', results)
	
