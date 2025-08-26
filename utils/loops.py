import requests
import os

loops_api_key = os.getenv('LOOPS_API_KEY')
horizon_loops_api_key = "a766b69a59aacb2f610f6b397f5e0fc8"

def get_loops_contact(email: str, api_key: str = None, call_for_horizon: bool = False):
	try:
		# Use provided api_key or default to loops_api_key
		if api_key is None:
			api_key = loops_api_key
			
		url = "https://app.loops.so/api/v1/contacts/find?email=" + email
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		response = requests.request("GET", url, headers=headers)
		contacts = response.json()
		contact = contacts[0]
		
		# Call again with horizon API key if requested and not already using it
		if call_for_horizon and api_key != horizon_loops_api_key:
			get_loops_contact(email, horizon_loops_api_key, False)
			
		return contact
	except Exception as e:
		print(f"Error getting loops contact: {e}")
		return None


def create_loops_contact(email: str, user_id: str, first_name: str = None, source="organic", auth_user_id: str = None, mailing_lists = [], from_horizon: bool = False, api_key: str = None, call_for_horizon: bool = False):
	try:
		# Use provided api_key or default to loops_api_key
		if api_key is None:
			api_key = loops_api_key
			
		url = "https://app.loops.so/api/v1/contacts/create"
		payload = {
			"email": email,
			"source": source,
			"subscribed": True,
			"userGroup": "post1k",
			"userId": user_id,
			"mailingLists": {} if not mailing_lists else {list_name: True for list_name in mailing_lists},
			"fromHorizon": from_horizon
		}
		if first_name:
			payload["firstName"] = first_name
		if auth_user_id:
			payload["authUserId"] = auth_user_id
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		response = requests.request("POST", url, json=payload, headers=headers)
		
		try:
			# If already on list and mailing_lists is not empty, call add to mailing list
			if 'message' in response.json() and 'already on list' in response.json()['message']\
				and mailing_lists:
				update_contact_property(email, 'mailingLists', {list_name: True for list_name in mailing_lists}, api_key)
			
			# Call again with horizon API key if requested and not already using it
			if call_for_horizon and api_key != horizon_loops_api_key:
				create_loops_contact(email, user_id, first_name, source, auth_user_id, mailing_lists, from_horizon, horizon_loops_api_key, False)
				
			return False
		except Exception as e:
			print(f"Error adding to mailing list: {e}")
			return False
	except Exception as e:
		print(f"Error creating loops contact: {e}")
		return False


def update_contact_property(email: str, property_name: str, property_value: str, api_key: str = None, call_for_horizon: bool = False):
	try:
		# Use provided api_key or default to loops_api_key
		if api_key is None:
			api_key = loops_api_key
			
		url = "https://app.loops.so/api/v1/contacts/update"

		payload = {
			"email": email,
			property_name: property_value
		}
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}

		response = requests.request("PUT", url, json=payload, headers=headers)
		
		# Call again with horizon API key if requested and not already using it
		if call_for_horizon and api_key != horizon_loops_api_key:
			update_contact_property(email, property_name, property_value, horizon_loops_api_key, False)
			
	except Exception as e:
		print(f"Error updating contact property: {e}")


def send_transactional_email(email: str, transactional_id: str, data_variables: dict = {}, api_key: str = None, call_for_horizon: bool = False):
	try:
		# Use provided api_key or default to loops_api_key
		if api_key is None:
			api_key = loops_api_key
			
		url = "https://app.loops.so/api/v1/transactional"
		payload = {
			"email": email,
			"transactionalId": transactional_id,
			"dataVariables": data_variables,
			"attachments": []
		}
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		response = requests.request("POST", url, json=payload, headers=headers)
		print(response.text)
		
		# Call again with horizon API key if requested and not already using it
		if call_for_horizon and api_key != horizon_loops_api_key:
			send_transactional_email(email, transactional_id, data_variables, horizon_loops_api_key, False)
			
	except Exception as e:
		print(f"Error sending transactional email: {e}")


def send_event(email: str, event_name: str, user_id='', event_properties: dict = {}, mailing_lists: dict = {}, api_key: str = None, call_for_horizon: bool = False):
	try:
		# Use provided api_key or default to loops_api_key
		if api_key is None:
			api_key = loops_api_key
			
		url = "https://app.loops.so/api/v1/events/send"
		payload = {
			"email": email,
			"userId": user_id,
			"eventName": event_name,
			"eventProperties": event_properties,
			"mailingLists": mailing_lists
		}
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		response = requests.request("POST", url, json=payload, headers=headers)
		
		# Call again with horizon API key if requested and not already using it
		if call_for_horizon and api_key != horizon_loops_api_key:
			send_event(email, event_name, user_id, event_properties, mailing_lists, horizon_loops_api_key, False)
			
	except Exception as e:
		print(f"Error sending event: {e}")



