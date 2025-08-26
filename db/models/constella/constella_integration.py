from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from typing import Any

collection = db['constella_integration']

class Integration:
	def __init__(self, apiKey: str = None, lastUpdated: datetime = None, arcade: dict = None):
		self.apiKey = apiKey
		self.lastUpdated = lastUpdated
		# Arbitrary metadata returned from Arcade (authorization status, token_status, provider, etc.)
		self.arcade = arcade

class ConstellaIntegration:
	def __init__(self, user_email: str, integrations: dict):
		self.user_email = user_email
		self.integrations = {name: Integration(**details.__dict__ if isinstance(details, Integration) else details) for name, details in integrations.items()}

	def save(self):
		# Convert Integration objects to dictionaries for MongoDB storage
		data = {
			"user_email": self.user_email,
			"integrations": {name: integration.__dict__ for name, integration in self.integrations.items()}
		}
		collection.insert_one(data)

	@staticmethod
	def get_by_email(user_email: str):
		data = collection.find_one({"user_email": user_email})
		if data:
			data = parse_json(data)
			# Convert stored data back to ConstellaIntegration object
			integrations = {name: Integration(**details.__dict__ if isinstance(details, Integration) else details) for name, details in data.get("integrations", {}).items()}
			return ConstellaIntegration(user_email=data["user_email"], integrations=integrations)
		return None

	@staticmethod
	def update_integration(user_email: str, integration_name: str, apiKey: str, lastUpdated: datetime = None):
		collection.update_one(
			{"user_email": user_email},
			{"$set": {f"integrations.{integration_name}": {"apiKey": apiKey, "lastUpdated": lastUpdated}}}
		)

	@staticmethod
	def get_all():
		return list(collection.find({}))

	@staticmethod
	def update_integration_property(user_email: str, integration_name: str, property_name: str, property_value: Any):
		# Always update the requested property; also bump lastUpdated unless explicitly setting it
		set_fields = {f"integrations.{integration_name}.{property_name}": property_value}
		if property_name != "lastUpdated":
			set_fields[f"integrations.{integration_name}.lastUpdated"] = datetime.utcnow()

		result = collection.update_one(
			{"user_email": user_email},
			{"$set": set_fields}
		)

		if result.matched_count == 0:
			# Create new integration document for this user/integration
			integration_doc = {property_name: property_value}
			if property_name != "lastUpdated":
				integration_doc["lastUpdated"] = datetime.utcnow()

			new_integration = {
				"user_email": user_email,
				"integrations": {integration_name: integration_doc}
			}
			collection.insert_one(new_integration)

	@staticmethod
	def remove_integration(user_email: str, integration_name: str):
		# Remove a single integration entry for a user
		collection.update_one(
			{"user_email": user_email},
			{"$unset": {f"integrations.{integration_name}": ""}}
		)