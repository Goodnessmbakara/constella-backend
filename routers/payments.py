from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import traceback
import os
from typing import Optional
from datetime import datetime, timedelta
from fastapi import Request
import stripe
from db.models.constella.constella_subscription import ConstellaSubscription
from utils.constella.financials.upgrading import upgrade_constella_subscription_to_ultra
from utils.loops import (create_loops_contact, get_loops_contact, send_transactional_email,
	update_contact_property)
from utils.constella.financials.subscriptions import (get_plan_name_from_stripe_price_id,
	get_stella_credits_from_stripe_price_id)

stripe.api_key = os.getenv('STRIPE_API_KEY') 
stripe_endpoint_secret = os.getenv('STRIPE_ENDPOINT_SECRET')

router = APIRouter(
	prefix="/payments",
)

class GetSubscriptionReq(BaseModel):
	email: Optional[str] = None
	auth_user_id: Optional[str] = None
	license_key: Optional[str] = None
	display_name: Optional[str] = None
	from_horizon: Optional[bool] = False

def create_subscription(email, auth_user_id, display_name=None, from_horizon=False):
	# Set plan name and period end for Horizon users
	plan_name = None
	period_end = None
	# if from_horizon:
	# 	plan_name = "ultra_monthly"
	# 	period_end = datetime.now() + timedelta(days=90)  # 3 months from now

	sub = ConstellaSubscription.create_subscription('', email, period_end=period_end, auth_user_id=auth_user_id, plan_name=plan_name)
	if display_name == '':
		display_name = None
	create_loops_contact(email=email, user_id=sub['_id'], first_name=display_name, auth_user_id=auth_user_id, from_horizon=from_horizon, call_for_horizon=True)
	return sub

@router.post("/get-subscription")
def get_subscription(req: GetSubscriptionReq):
	try:
		# get subscription if it exists
		subscription = ConstellaSubscription.get_user_info(req.email, req.auth_user_id, req.license_key)
		if subscription:
			# Check if auth_user_id is not in subscription and it's provided in the request
			if 'auth_user_id' not in subscription and req.auth_user_id:
				ConstellaSubscription.update_auth_user_id(subscription['_id'], req.auth_user_id)
			
			print("subscription: ", subscription)
			# TODO: here can do plan name setting via stripe product names to map to starter / ultra
			return {"subscription": subscription}
		else:
			# Otherwise, create a new subscription
			sub = create_subscription(req.email, req.auth_user_id, req.display_name, req.from_horizon)
			return {"subscription": sub}
	except Exception as e:
		traceback.print_exc()

class GetOrCreateSubscriptionReq(BaseModel):
	email: str
	auth_user_id: Optional[str] = ''
	display_name: Optional[str] = None
	from_horizon: Optional[bool] = False

@router.post("/get-or-create-subscription")
def get_or_create_subscription(req: GetOrCreateSubscriptionReq):
	try:
		# check if subscription exists
		subscription = ConstellaSubscription.get_user_info(req.email)
		if subscription:
			return {"subscription": subscription}
		
		# create subscription
		sub = create_subscription(req.email, req.auth_user_id, req.display_name, req.from_horizon)
		return {"subscription": sub}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

class GetLicenseKeyReq(BaseModel):
	checkout_session_id: str

@router.post("/get-constella-license-key")
def get_license_key(req: GetLicenseKeyReq):
	try:
		checkout_session = stripe.checkout.Session.retrieve(req.checkout_session_id)
		customer = stripe.Customer.retrieve(checkout_session.customer)
		
		# look up subscription model in DB and its license key
		license_key = ConstellaSubscription.get_license_key(customer.id)
		
		# update contact properties with stripe customer id & license key
		update_contact_property(customer.email, "stripeCustomerId", customer.id)
		update_contact_property(customer.email, "licenseKey", license_key)

		if not license_key:
			raise HTTPException(status_code=422, detail="License key not found")


		return {"license_key": license_key}
	except:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to get license key")

class VerifyLicenseKeyReq(BaseModel):
	license_key: str

@router.post("/verify-constella-license-key")
def verify_license_key(req: VerifyLicenseKeyReq):
	try:
		req.license_key = req.license_key.strip()
		
		# look up subscription model in DB and its license key
		subscription = ConstellaSubscription.get_subscription_by_license_key(req.license_key)

		if not subscription:
			print("License key not found")
			raise HTTPException(status_code=422, detail="License key not found")
				
		# check if subscription is active
		period_end = subscription.get('period_end')
		period_end = datetime.strptime(period_end, "%Y-%m-%dT%H:%M:%SZ")

		if period_end < datetime.now():
			print("License key expired")
			raise HTTPException(status_code=422, detail="License key expired")

		return_data = {
			"status": "success",
			"email": subscription.get('email'),
		}
		
		if subscription.get('is_early_og'):
			return_data['is_early_og'] = True

		return return_data
	except:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to verify license key")

class CheckEarlyOGReq(BaseModel):
	email: str

@router.post("/check-early-og")
def check_early_og(req: CheckEarlyOGReq):
	try:
		contact = get_loops_contact(req.email)

		user_group = contact.get('userGroup', None)

		if not user_group or user_group == 'early_og':
			return {"status": 'success'}
		else:
			return {"status": 'false'}

	except:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to check early OG")

class IncrementStellaCreditsReq(BaseModel):
	subscription_id: str 
	credits: float
	email: Optional[str] = None
	auth_user_id: Optional[str] = None

@router.post("/increment-stella-credits")
def increment_stella_credits(req: IncrementStellaCreditsReq):
	try:
		# Get subscription if email or user_id is provided
		if not req.subscription_id:
			subscription = ConstellaSubscription.get_user_info(req.email, req.auth_user_id, '')
			if not subscription:
				raise HTTPException(status_code=422, detail="Subscription not found")
			req.subscription_id = subscription['_id']

		ConstellaSubscription.increment_stella_credits(req.subscription_id, req.credits)
		return {"status": "success"}
	except:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to increment Stella credits")


## ********** Stripe Webhook ********** ##

# Define the Stripe webhook endpoint
@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
	payload = await request.body()
	sig_header = request.headers.get('stripe-signature')

	try:
		event = stripe.Webhook.construct_event(
			payload, sig_header, stripe_endpoint_secret
		)
	except ValueError as e:
		# Invalid payload
		print('Invalid payload')
		raise HTTPException(status_code=400, detail="Invalid payload")
	except stripe.error.SignatureVerificationError as e:
		# Invalid signature
		print('Invalid signature')
		raise HTTPException(status_code=400, detail="Invalid signature")

	# Handle the events

	try:
		## INVOICE PAID
		if event['type'] == 'invoice.paid':
			invoice = event['data']['object']
			stripe_id = invoice.get('customer')
			email = invoice.get('customer_email')
			customer_name = invoice.get('customer_name', '')
			lines_data = invoice.get('lines').get('data')
			# get first line item
			line_data = lines_data[0]

			# Get payment intent from invoice
			payment_intent = invoice.get('payment_intent')

			user_email = ""
			user_id = ""

			# Get sessions and get user_email from metadata
			try:
				sessions = stripe.checkout.Session.list(payment_intent=payment_intent)
			except Exception as e:
				print(f"STRIPE WEBHOOK ERROR: No sessions found for invoice: {invoice['id']}")
				sessions = None

			print("STRIPE WEBHOOK: Sessions: ")
			print(sessions)

			if sessions and sessions.data:
				# Loop through sessions and get metadata
				for session in sessions.data:
					print('SESSION: ', session)
					if session.client_reference_id:
						user_id = session.client_reference_id
						break
					if session.metadata.get('userEmail'):
						user_email = session.metadata['userEmail']
						break

			# If no user email & id was found, use email in invoice + log error
			if not user_email and not user_id:
				print(f"INVOICE PAID: No user email nor id found for sessions: {invoice['id']}")
				user_email = email  # Using the email from the invoice

			# subscription id
			subscription_id = line_data.get('subscription')
			
			# get product id
			product_id = line_data.get('price').get('product')

			# get period end
			period_end = line_data.get('period').get('end')
			# convert to datetime
			period_end = datetime.fromtimestamp(period_end)

			# get price id
			price_id = line_data.get('price').get('id')

			# get plan name
			plan_name = get_plan_name_from_stripe_price_id(price_id)

			stella_credits_grant = get_stella_credits_from_stripe_price_id(price_id)

			print("Updating user id: ", user_id)
			print("Updating stripe id: ", stripe_id)
			print("Updating user email: ", user_email)
			print("Updating period end: ", period_end)
			print("Updating subscription id: ", subscription_id)
			print("Updating product id: ", product_id)
			print("Updating plan name: ", plan_name)

			# Create or update an existing subscription
			ConstellaSubscription.create_or_update_subscription_v2(user_id, stripe_id, user_email, period_end, subscription_id, product_id, stella_credits_grant=stella_credits_grant, plan_name=plan_name, auth_user_id=user_id)
			update_contact_property(email, "subscriptionStatus", "subscribed")
			if customer_name:
				update_contact_property(email, "firstName", customer_name)

			return {"status": "success"}
		elif event['type'] == "invoice.payment_failed":
			# handle payment failed
			failed_invoice_data = event['data']['object']
			failed_customer_id = failed_invoice_data['customer']
			failed_customer_email = failed_invoice_data.get('customer_email')

			# retrieve customer object if not found
			if not failed_customer_email:
				try:
					customer = stripe.Customer.retrieve(failed_customer_id)
					failed_customer_email = customer['email']
				except Exception as err:
					print(f"STRIPE WEBHOOK ERROR: {err}")

			# if has email, send loops transactional to get them to update payment
			if failed_customer_email:
				send_transactional_email(failed_customer_email, "cm2njbbeq00ksuudn5oz8z5gk")
				update_contact_property(failed_customer_email, "subscriptionStatus", "payment_failed")

		elif event['type'] == "customer.subscription.deleted":
			# handle subscription cancelled
			data = event['data']['object']
			cus_id = data['customer']

			print(f"STRIPE WEBHOOK: Subscription Cancelled: {cus_id}")

			cancelled_user_email = ""

			# get customer from Stripe using customer id and set email
			try:
				customer = stripe.Customer.retrieve(cus_id)
				cancelled_user_email = customer['email']
				if not cancelled_user_email:
					print(f"STRIPE WEBHOOK ERROR: No user email found for customer: {cus_id}")
			except Exception as err:
				print(f"STRIPE WEBHOOK ERROR: {err}")

			try:
				# see if any active subscriptions (not cancelled or returned), in which case skip
				subscription = stripe.Subscription.list(customer=cus_id)
				# has subscription
				if subscription['data']:
					print(f"Cancelling user already has subscription, returning: {subscription}")
					return {"status": "success"}
			except Exception as err:
				print(f"STRIPE WEBHOOK ERROR: {err}")

			current_subscription_end = data['current_period_end']
			subscription_end_date = datetime.fromtimestamp(current_subscription_end)
			print(f"Subscription will end on: {subscription_end_date.isoformat()}")

			if cancelled_user_email:
				update_contact_property(cancelled_user_email, "subscriptionStatus", "cancelled")

			
	except:
		print('stripe webhook error!!')
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to process event")

	return {"status": "success"}

class UpgradeToUltraReq(BaseModel):
	subscription_id: Optional[str] = None
	email: Optional[str] = None
	auth_user_id: Optional[str] = None
	license_key: Optional[str] = None
	is_yearly: bool = False

@router.post("/upgrade-to-ultra")
def upgrade_to_ultra_route(req: UpgradeToUltraReq):
	try:

		# Get user subscription info
		subscription = ConstellaSubscription.get_user_info(req.email, req.auth_user_id, req.license_key)
		
		if not subscription:
			if req.subscription_id:
				# Try to find by direct subscription_id if provided
				try:
					subscription = ConstellaSubscription.get_by_id(req.subscription_id)
				except:
					pass
					
		if not subscription:
			# Make them go to web portal
			return {"success": False, "errorType": "no_subscription"}
			
		# Extract necessary information from subscription
		subscription_id = req.subscription_id or str(subscription.get("_id"))
		stripe_customer_id = subscription.get("stripe_customer_id")
		
		if not stripe_customer_id:
			# Make them go to web portal + if subscribed via app store --> cancel on there
			return {"success": False, "errorType": "no_stripe_customer_id"}
		
		result = upgrade_constella_subscription_to_ultra(
			subscription_id,
			stripe_customer_id,
			req.is_yearly
		)
		
		if not result.get("success", False):
			raise HTTPException(
				status_code=500, 
				detail=result.get("error", "Failed to upgrade subscription to Ultra")
			)
			
		return result
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))




class CancelSubscriptionReq(BaseModel):
	email: Optional[str] = None
	auth_user_id: Optional[str] = None

@router.post("/cancel")
def cancel_subscription(req: CancelSubscriptionReq):
	try:
		# Get ALL subscriptions for the user, not just the best one
		query = {"$or": []}
		if req.email:
			query["$or"].append({"email": req.email})
		if req.auth_user_id:
			query["$or"].append({"auth_user_id": req.auth_user_id})

		if not query["$or"]:
			raise HTTPException(status_code=400, detail="Email or auth_user_id required")

		# Get all subscriptions for this user
		from db.mongodb import db
		collection = db['constella_subscriptions']
		all_subscriptions = list(collection.find(query))
		
		if not all_subscriptions:
			raise HTTPException(status_code=404, detail="No subscriptions found")

		cancelled_count = 0
		immediately_cancelled_count = 0
		errors = []

		# Cancel all Stripe subscriptions for each customer ID found
		for subscription in all_subscriptions:
			stripe_customer_id = subscription.get('stripe_customer_id')
			if not stripe_customer_id:
				continue

			try:
				# Get all active Stripe subscriptions for this customer
				stripe_subscriptions = stripe.Subscription.list(customer=stripe_customer_id)
				
				# Check each subscription and handle based on status
				for stripe_sub in stripe_subscriptions.data:
					if stripe_sub.status == 'trialing':
						# For trialing subscriptions, cancel immediately in our database
						ConstellaSubscription.cancel_immediately_user_subscription(str(subscription['_id']))
						immediately_cancelled_count += 1
						print(f"Immediately cancelled trialing subscription in database: {subscription['_id']}")
						
						# Still cancel in Stripe as well
						stripe.Subscription.delete(stripe_sub.id)
						print(f"Cancelled trialing Stripe subscription: {stripe_sub.id}")
					else:
						# For active subscriptions, just cancel in Stripe (let webhook handle database updates)
						stripe.Subscription.delete(stripe_sub.id)
						cancelled_count += 1
						print(f"Cancelled active Stripe subscription: {stripe_sub.id} for customer: {stripe_customer_id}")

			except Exception as e:
				error_msg = f"Failed to cancel subscriptions for customer {stripe_customer_id}: {str(e)}"
				print(error_msg)
				errors.append(error_msg)

		# Update contact property in loops
		if req.email:
			update_contact_property(req.email, "subscriptionStatus", "cancelled")

		result = {
			"status": "success",
			"cancelled_subscriptions": cancelled_count,
			"immediately_cancelled_subscriptions": immediately_cancelled_count,
		}
		
		if errors:
			result["errors"] = errors

		return result

	except HTTPException:
		raise
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

class GiveCouponReq(BaseModel):
	email: Optional[str] = None
	auth_user_id: Optional[str] = None
	coupon_id: str

@router.post("/give-coupon")
def give_coupon(req: GiveCouponReq):
	try:
		# Get the best subscription using the existing method
		subscription = ConstellaSubscription.get_user_info(req.email, req.auth_user_id)
		
		if not subscription:
			raise HTTPException(status_code=404, detail="No subscription found")

		stripe_customer_id = subscription.get('stripe_customer_id')
		if not stripe_customer_id:
			raise HTTPException(status_code=400, detail="No Stripe customer ID found")

		# Get the active Stripe subscription for this customer
		stripe_subscriptions = stripe.Subscription.list(customer=stripe_customer_id)

		# Check if there are any active or trialing subscriptions
		active_or_trialing_subscriptions = [sub for sub in stripe_subscriptions.data if sub.status in ['active', 'trialing']]
		if not active_or_trialing_subscriptions:
			return {"error": "none active"}
		
		if not stripe_subscriptions.data:
			raise HTTPException(status_code=404, detail="No active Stripe subscription found")

		# Apply coupon to the first active subscription
		stripe_subscription = stripe_subscriptions.data[0]
		
		# Update the subscription with the coupon
		updated_subscription = stripe.Subscription.modify(
			stripe_subscription.id,
			coupon=req.coupon_id
		)

		# Update contact property in loops
		if req.email:
			update_contact_property(req.email, "appliedCoupon", req.coupon_id)

		return {
			"status": "success",
			"subscription_id": updated_subscription.id,
			"coupon_applied": req.coupon_id
		}

	except HTTPException:
		raise
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

class GiveExtraTrialReq(BaseModel):
	email: Optional[str] = None
	auth_user_id: Optional[str] = None
	duration: int = 30  # days

@router.post("/give-extra-trial")
def give_extra_trial(req: GiveExtraTrialReq):
	try:
		# Get the best subscription using the existing method
		subscription = ConstellaSubscription.get_user_info(req.email, req.auth_user_id)
		
		if not subscription:
			raise HTTPException(status_code=404, detail="No subscription found")

		# Calculate new trial end date
		current_period_end = subscription.get('period_end')
		if current_period_end:
			if isinstance(current_period_end, str):
				current_period_end = datetime.strptime(current_period_end, "%Y-%m-%dT%H:%M:%SZ")
			new_trial_end = current_period_end + timedelta(days=req.duration)
		else:
			new_trial_end = datetime.now() + timedelta(days=req.duration)

		# Update the subscription in our database using the new method
		success = ConstellaSubscription.update_period_end(subscription['_id'], new_trial_end)
		if not success:
			raise HTTPException(status_code=500, detail="Failed to update subscription period")

		# If there's a Stripe customer ID and active subscription, update Stripe too
		stripe_customer_id = subscription.get('stripe_customer_id')
		if stripe_customer_id:
			try:
				stripe_subscriptions = stripe.Subscription.list(customer=stripe_customer_id)

				# Check if there are any active or trialing subscriptions
				active_or_trialing_subscriptions = [sub for sub in stripe_subscriptions.data if sub.status in ['active', 'trialing']]
				if not active_or_trialing_subscriptions:
					return {"error": "none active"}
		
				if stripe_subscriptions.data:
					# Get the most recently active subscription (last one in the list)
					stripe_subscription = stripe_subscriptions.data[-1]
					# Convert to timestamp for Stripe
					trial_end_timestamp = int(new_trial_end.timestamp())
					stripe.Subscription.modify(
						stripe_subscription.id,
						trial_end=trial_end_timestamp
					)
			except Exception as e:
				print(f"Failed to update Stripe trial end: {str(e)}")
				# Continue anyway since we updated our database

		# Update contact property in loops
		if req.email:
			update_contact_property(req.email, "trialExtended", req.duration)

		return {
			"status": "success",
			"new_trial_end": new_trial_end.isoformat(),
			"extended_days": req.duration
		}

	except HTTPException:
		raise
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))