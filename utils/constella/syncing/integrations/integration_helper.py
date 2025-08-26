from db.models.constella.constella_integration import ConstellaIntegration
from utils.constella.syncing.integrations.readwise import fetch_from_export_api
from datetime import datetime
import traceback
from db.models.constella.long_job import LongJob

def sync_integrations_for_user(tenant_name: str, user_email: str, long_job_id: str = None):
	"""
	For each integration in the user's integration object, sync the data from the integration if the api key exists
	Update the last updated time for each integration as well.
	"""
	try:
		user_integrations = ConstellaIntegration.get_by_email(user_email)
		all_results = []
		
		# If no integrations, mark the long job as completed and return empty list
		if not user_integrations:
			if long_job_id:
				LongJob.update_status(long_job_id, 'completed', [])
			return []

		for integration_name, integration_data in user_integrations.integrations.items():
			try:
				if integration_name == "readwise" and integration_data.apiKey:
					# Convert lastUpdated milliseconds timestamp to ISO 8601 format for Readwise API if exists
					last_updated_utc = None
					if integration_data.lastUpdated:
						last_updated_utc = datetime.fromtimestamp(integration_data.lastUpdated / 1000).strftime('%Y-%m-%dT%H:%M:%SZ')
					
					# Fetch all the data from Readwise since last updated --> Those notes in VectorDB will have lastUpdated at time of operation
					res = fetch_from_export_api(tenant_name, integration_data.apiKey, updated_after=last_updated_utc)

					# Update this integration's lastUpdated to be the current time in utc
					last_updated_utc = int(datetime.utcnow().timestamp() * 1000)
					ConstellaIntegration.update_integration_property(user_email, integration_name, 'lastUpdated', last_updated_utc)
					all_results.extend(res)
			except Exception as e:
				print(f"Error syncing integration {integration_name}: {e}")
		return all_results
	except Exception as e:
		traceback.print_exc()
		if long_job_id:
			LongJob.update_status(long_job_id, 'completed', [])
	finally:
		if long_job_id:
			LongJob.update_status(long_job_id, 'completed', [])

