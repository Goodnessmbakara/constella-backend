from bson import ObjectId
from pymongo import MongoClient
from db.mongodb import db
from datetime import datetime, timedelta
import traceback
from utils.json import parse_json
import uuid
from utils.constella.financials.subscriptions import get_stella_credits


collection = db['constella_subscriptions']

free_stella_credits = 2

class ConstellaSubscription:
	def __init__(self, stripe_customer_id: str):
		self.stripe_customer_id = stripe_customer_id

	def save(self):
		collection.insert_one(self.__dict__)
	
	@staticmethod
	def create_license_key():
		return str(uuid.uuid4())
	
	@staticmethod
	def create_subscription(stripe_customer_id: str, email: str, period_end: datetime = None, subscription_id: str = None, product_id: str = None, auth_user_id: str = None, stella_credits_grant: int = free_stella_credits, plan_name: str = None):
		now = datetime.now()
		sub = {
			"stripe_customer_id": stripe_customer_id,
			"email": email,
			"period_end": period_end,
			"subscription_id": subscription_id,
			"product_id": product_id,
			"created_at": now,
			"license_key": ConstellaSubscription.create_license_key(),
			"auth_user_id": auth_user_id,
			"stella_credits": stella_credits_grant,
			"plan_name": plan_name,
			"next_renewal_date": now + timedelta(days=30) if "yearly" in (plan_name or "") else None
		}
		res = collection.insert_one(sub)
		sub['_id'] = str(res.inserted_id)
		return sub
		
	@staticmethod
	def create_or_update_subscription(stripe_customer_id: str, email: str, period_end: datetime, subscription_id: str, product_id: str, plan_name: str):
		subscription = collection.find_one({"stripe_customer_id": stripe_customer_id})
		if subscription:
			collection.update_one({"stripe_customer_id": stripe_customer_id}, {"$set": {
				"email": email,
				"period_end": period_end,
				"subscription_id": subscription_id,
				"product_id": product_id,
				"updated_at": datetime.now(),
				"plan_name": plan_name
			}})
		else:
			ConstellaSubscription.create_subscription(stripe_customer_id, email, period_end, subscription_id, product_id, plan_name)

	@staticmethod
	def create_or_update_subscription_v2(_id: str, stripe_customer_id: str, email: str, period_end: datetime, subscription_id: str, product_id: str, stella_credits_grant: int = 0, plan_name: str = '', auth_user_id: str = None):
		subscription = None
		
		if _id:
			try:
				subscription = collection.find_one({"_id": ObjectId(_id)})
			except Exception as e:
				if not auth_user_id:
					print(f"Error finding subscription by _id and auth_user_id is not set: {e}")
				subscription = None
		
		if not subscription and stripe_customer_id:
			try:
				subscription = collection.find_one({"stripe_customer_id": stripe_customer_id})
			except Exception as e:
				print(f"Error finding subscription by stripe_customer_id: {e}")
				subscription = None
		
		if not subscription and email:
			try:
				subscription = collection.find_one({"email": email})
			except Exception as e:
				print(f"Error finding subscription by email: {e}")
				subscription = None
		
		if not subscription and auth_user_id:
			try:
				subscription = collection.find_one({"auth_user_id": auth_user_id})
			except Exception as e:
				print(f"Error finding subscription by auth_user_id: {e}")
				subscription = None
		
		
		if subscription:
			try:
				# Check if the user is converting from a trial by seeing if period_end < 15 days from created_at
				try:
					created_at = subscription.get('created_at')
					curr_period_end = subscription.get('period_end')
					
					if created_at and curr_period_end:
						# Directly compare period_end and created_at
						if (curr_period_end - created_at).days < 15:
							print(f"User is converting from trial. Not granting additional credits.")
							stella_credits_grant = 0
				except Exception as e:
					print(f"Error checking if user is converting from trial: {e}")

				next_renewal_date = subscription.get("next_renewal_date", None)

				# To give them their monthly stella credits
				if plan_name and 'yearly' in plan_name:
					next_renewal_date = datetime.now() + timedelta(days=30)

				update_fields = {
					"stripe_customer_id": stripe_customer_id if stripe_customer_id else subscription.get("stripe_customer_id"),
					"period_end": period_end,
					"subscription_id": subscription_id,
					"product_id": product_id if product_id else subscription.get("product_id"),
					"updated_at": datetime.now(),
					"stella_credits": max(0, subscription.get("stella_credits", 0) + stella_credits_grant),
					"plan_name": plan_name if plan_name else subscription.get("plan_name"),
					"next_renewal_date": next_renewal_date if next_renewal_date else subscription.get("next_renewal_date")
				}
				
				# Only update email if not there (otherwise will override user's original login email which could be different)
				if not subscription.get("email"):
					update_fields["email"] = email
					
				collection.update_one({"_id": subscription["_id"]}, {"$set": update_fields})
			except Exception as e:
				print(f"Error updating subscription: {e}")
				traceback.print_exc()
		else:
			try:
				ConstellaSubscription.create_subscription(stripe_customer_id, email, period_end, subscription_id, product_id, auth_user_id=auth_user_id, stella_credits_grant=stella_credits_grant, plan_name=plan_name)
			except Exception as e:
				print(f"Error creating subscription: {e}")

	@staticmethod
	def get_license_key(stripe_customer_id: str):
		try:
			return parse_json(collection.find_one({"stripe_customer_id": stripe_customer_id}, {"license_key": 1})).get('license_key', None)
		except Exception as e:
			return None
	
	@staticmethod
	def get_subscription_by_license_key(license_key: str):
		result = collection.find_one({"license_key": license_key})
		if result is None:
			return None
		return parse_json(result)
	
	@staticmethod
	def _get_best_subscription(results):
		"""
		Helper function that takes a list of subscription results and returns
		the one with period_end, or the last one if none have it.
		"""
		if not results:
			return None
		
		furthest_period_end = None
		furthest_period_end_sub = None
			
		# Try to find one with period_end
		for result in results:
			parsed = parse_json(result)
			if parsed.get('period_end'):
				if not furthest_period_end or parsed.get('period_end') > furthest_period_end:
					furthest_period_end = parsed.get('period_end')
					furthest_period_end_sub = parsed
		
		if furthest_period_end_sub:
			return furthest_period_end_sub
		
		# If none have period_end, return the last one
		return parse_json(results[-1])
		
	@staticmethod
	def get_user_info(email: str, auth_user_id: str = None, license_key: str = None):
		"""
		Tries to get user sub info by checking email, auth_user_id and license_key.
		Combines all matches across fields and returns the one with latest period_end,
		or last one if none have period_end.
		"""
		query = {"$or": []}
		if email:
			query["$or"].append({"email": email})
		if auth_user_id:
			query["$or"].append({"auth_user_id": auth_user_id})
		if license_key:
			query["$or"].append({"license_key": license_key})

		if not query["$or"]:
			return None

		results = list(collection.find(query))
		return ConstellaSubscription._get_best_subscription(results)

	@staticmethod
	def update_auth_user_id(_id: str, auth_user_id: str):
		"""
		Updates the auth_user_id for a subscription based on the _id.
		"""
		try:
			result = collection.update_one(
				{"_id": ObjectId(_id)},
				{"$set": {"auth_user_id": auth_user_id}}
			)
			if result.modified_count == 0:
				print(f"No subscription found for _id: {_id}")
				return False
			return True
		except Exception as e:
			print(f"Error updating auth_user_id: {str(e)}")
			return False

	@staticmethod
	def get_all():
		return list(collection.find({}))

	@staticmethod
	def delete_all():
		collection.delete_many({})

	@staticmethod
	def create_api_key():
		"""
		Creates a unique API key.
		"""
		return f"csk_{str(uuid.uuid4())}"

	@staticmethod
	def add_api_key(subscription_id: str = None, auth_user_id: str = None):
		"""
		Adds an API key to an existing subscription.
		Can find subscription by either subscription_id or auth_user_id.
		Returns the created API key or None if failed.
		"""
		try:
			api_key = ConstellaSubscription.create_api_key()
			
			# Build query based on provided parameters
			query = {}
			if subscription_id:
				query["_id"] = ObjectId(subscription_id)
			elif auth_user_id:
				query["auth_user_id"] = auth_user_id
			else:
				print("Neither subscription_id nor auth_user_id provided")
				return None
			
			result = collection.update_one(
				query,
				{
					"$set": {
						"api_key": api_key,
						"api_key_created_at": datetime.now()
					}
				}
			)
			if result.modified_count == 0:
				print(f"No subscription found for query: {query}")
				return None
			return api_key
		except Exception as e:
			print(f"Error adding API key: {str(e)}")
			return None

	@staticmethod
	def get_subscription_by_api_key(api_key: str):
		"""
		Retrieves a subscription by API key.
		Returns None if not found.
		"""
		try:
			result = collection.find_one({"api_key": api_key})
			if result is None:
				return None
			return parse_json(result)
		except Exception as e:
			print(f"Error getting subscription by API key: {str(e)}")
			return None

	@staticmethod
	def rotate_api_key(subscription_id: str):
		"""
		Generates a new API key for an existing subscription.
		Returns the new API key or None if failed.
		"""
		return ConstellaSubscription.add_api_key(subscription_id)
	
	@staticmethod
	def increment_stella_credits(subscription_id: str, credits: int):
		"""
		Updates the number of credits for a subscription.
		"""
		collection.update_one({"_id": ObjectId(subscription_id)}, {"$inc": {"stella_credits": credits}})

	@staticmethod
	def distribute_monthly_credits_to_yearly():
		"""
		Distributes monthly credits to active yearly subscribers who have reached
		their next renewal date.
		"""
		now = datetime.now()
		
		# Find yearly subscribers whose subscription hasn't expired and need renewal
		yearly_subs = collection.find({
			"plan_name": {"$in": ["starter_yearly", "ultra_yearly"]},
			"period_end": {"$gte": now},
			"next_renewal_date": {"$lte": now}  # Find all subscriptions due for renewal
		})
		
		for sub in yearly_subs:
			try:
				# Get monthly credit amount based on plan
				monthly_credits = get_stella_credits(sub['plan_name'])

				
				# Update subscription with new credits and set next renewal date to 30 days from now
				collection.update_one(
					{"_id": sub["_id"]},
					{
						"$inc": {"stella_credits": monthly_credits},
						"$set": {"next_renewal_date": now + timedelta(days=30)}
					}
				)
				
				print(f"Granted {monthly_credits} credits to subscription {sub['_id']}, next renewal on {(now + timedelta(days=30)).isoformat()}")
			except Exception as e:
				print(f"Error granting monthly credits to subscription {sub['_id']}: {str(e)}")

	@staticmethod
	def update_plan(subscription_id: str, plan_name: str):
		"""
		Updates only the plan name for a subscription.
		
		Args:
			subscription_id: The ID of the subscription to update
			plan_name: The new plan name to set
			
		Returns:
			bool: True if update was successful, False otherwise
		"""
		try:
			result = collection.update_one(
				{"_id": ObjectId(subscription_id)},
				{"$set": {
					"plan_name": plan_name,
					"updated_at": datetime.now()
				}}
			)
			if result.modified_count == 0:
				print(f"No subscription found for ID: {subscription_id}")
				return False
			return True
		except Exception as e:
			print(f"Error updating plan: {str(e)}")
			return False

	@staticmethod
	def update_after_plan_change(subscription_id: str, stripe_subscription: dict, plan_name: str):
		"""
		Updates a subscription after changing the plan, updating both the plan name
		and the period end from Stripe, and granting appropriate stella credits.
		
		Args:
			subscription_id: The ID of the subscription in the constella_subscriptions collection
			stripe_subscription: The Stripe subscription object returned from Stripe.Subscription.modify
			plan_name: The new plan name
			
		Returns:
			bool: True if update was successful, False otherwise
		"""
		try:
			# Get stella credits for the plan
			stella_credits_grant = get_stella_credits(plan_name)
			
			# Get period end from Stripe subscription
			current_period_end = stripe_subscription.get('current_period_end')
			if current_period_end:
				period_end = datetime.fromtimestamp(current_period_end)
			else:
				period_end = None
				
			# Set the next renewal date for yearly plans
			next_renewal_date = None
			if 'yearly' in plan_name:
				next_renewal_date = datetime.now() + timedelta(days=30)
			
			# Update subscription in database
			result = collection.update_one(
				{"_id": ObjectId(subscription_id)},
				{"$set": {
					"plan_name": plan_name,
					"period_end": period_end,
					"stella_credits": stella_credits_grant,
					"next_renewal_date": next_renewal_date,
					"updated_at": datetime.now()
				}}
			)
			
			if result.modified_count == 0:
				print(f"No subscription found for ID: {subscription_id}")
				return False
				
			return True
		except Exception as e:
			print(f"Error updating subscription after plan change: {str(e)}")
			traceback.print_exc()
			return False

	@staticmethod
	def set_embedded_bodies_status(subscription_id: str, status: str):
		"""
		Updates the embedded_bodies_status for a subscription.
		
		Args:
			subscription_id: The ID of the subscription to update
			status: The status to set for embedded bodies
			
		Returns:
			bool: True if update was successful, False otherwise
		"""
		try:
			result = collection.update_one(
				{"_id": ObjectId(subscription_id)},
				{"$set": {
					"embedded_bodies_status": status,
					"updated_at": datetime.now()
				}}
			)
			if result.modified_count == 0:
				print(f"No subscription found for ID: {subscription_id}")
				return False
			return True
		except Exception as e:
			print(f"Error updating embedded bodies status: {str(e)}")
			traceback.print_exc()
			return False

	@staticmethod
	def update_period_end(subscription_id: str, new_period_end: datetime):
		"""
		Updates the period_end for a subscription.
		
		Args:
			subscription_id: The ID of the subscription to update
			new_period_end: The new period end datetime
			
		Returns:
			bool: True if update was successful, False otherwise
		"""
		try:
			result = collection.update_one(
				{"_id": ObjectId(subscription_id)},
				{"$set": {
					"period_end": new_period_end,
					"updated_at": datetime.now()
				}}
			)
			if result.modified_count == 0:
				print(f"No subscription found for ID: {subscription_id}")
				return False
			return True
		except Exception as e:
			print(f"Error updating period end: {str(e)}")
			traceback.print_exc()
			return False

	@staticmethod
	def cancel_immediately_user_subscription(subscription_id: str):
		"""
		Cancels a subscription immediately by setting period_end to null and plan_name to empty string.
		This is typically used for trialing subscriptions.
		
		Args:
			subscription_id: The ID of the subscription to cancel immediately
			
		Returns:
			bool: True if cancellation was successful, False otherwise
		"""
		try:
			result = collection.update_one(
				{"_id": ObjectId(subscription_id)},
				{"$set": {
					"period_end": None,
					"plan_name": "",
					"updated_at": datetime.now()
				}}
			)
			if result.modified_count == 0:
				print(f"No subscription found for ID: {subscription_id}")
				return False
			return True
		except Exception as e:
			print(f"Error canceling subscription immediately: {str(e)}")
			traceback.print_exc()
			return False
