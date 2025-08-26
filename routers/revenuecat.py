from fastapi import APIRouter, Request, HTTPException
import sentry_sdk
from datetime import datetime, timezone, timedelta
from db.models.constella.constella_subscription import ConstellaSubscription, free_stella_credits
import json
from utils.constella.financials.subscriptions import get_plan_name, get_stella_credits
from utils.loops import send_event, update_contact_property

router = APIRouter(
	prefix="/revenuecat"
)

@router.post('/webhook')
async def handle_webhook(request: Request):
	# Verify authorization header
	auth_header = request.headers.get('Authorization')
	if not auth_header or auth_header != 'Bearer soidhfshfs0pehf-hwr':
		raise HTTPException(status_code=401, detail='Unauthorized')

	try:
		webhook_data = await request.json()
		if not webhook_data:
			raise HTTPException(status_code=400, detail='No webhook data')

		event = webhook_data.get('event')
		if not event:
			raise HTTPException(status_code=400, detail='No event data')

		event_type = event.get('type')
		
		# Get the app_user_id which corresponds to auth_user_id in our system
		auth_user_id = event.get('app_user_id')
		if not auth_user_id:
			print("EVENT DATA: ", event)
			try:
				sentry_sdk.set_extra("revenuecat_event", event)
			except Exception as e:
				print(f"Error capturing exception: {e}")
			sentry_sdk.capture_exception(Exception(f"RevenueCat webhook received without app_user_id. Event data: {event}"))
			raise HTTPException(status_code=400, detail='No app_user_id provided')
		
		print("EVENT:", event)

		# Handle different event types
		if event_type in ['INITIAL_PURCHASE', 'RENEWAL', 'PRODUCT_CHANGE']:
			print('handling successful purchase')
			handle_successful_purchase(event)
		elif event_type == 'CANCELLATION':
			print('handling cancellation')
			handle_cancellation(event)
		elif event_type == 'EXPIRATION':
			print('handling expiration')
			handle_expiration(event)
		else:
			print(f"Unhandled event type: {event_type}")
			return {'status': 'ignored'}

		return {'status': 'success'}

	except Exception as e:
		print(f"Error processing RevenueCat webhook: {str(e)}")
		raise HTTPException(status_code=500, detail=str(e)) from e

def handle_successful_purchase(event):
	"""
	Handle successful purchases and renewals
	"""
	try:
		auth_user_id = event.get('app_user_id')
		expiration_at_ms = event.get('expiration_at_ms')
		event_user_email = event.get('subscriber_attributes', {}).get('$email', {}).get('value')

		print('event_user_email', event_user_email)
		print('auth_user_id', auth_user_id)
		print('expiration_at_ms', expiration_at_ms)
		
		# Get existing subscription info
		subscription = ConstellaSubscription.get_user_info(
			email=event_user_email,
			auth_user_id=auth_user_id
		)

		print('existing subscription ', subscription)

		# Convert milliseconds to datetime
		period_end = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc) if expiration_at_ms else None
		
		# Get additional fields
		product_id = event.get('new_product_id') if event.get('type') == 'PRODUCT_CHANGE' else event.get('product_id')
		transaction_id = event.get('transaction_id')

		plan_name = get_plan_name(product_id)
		stella_credits = get_stella_credits(plan_name)


		if subscription:
			print('updating existing subscription')

			# Update existing subscription
			ConstellaSubscription.create_or_update_subscription_v2(
				_id=str(subscription.get('_id')),
				stripe_customer_id=None,
				email=subscription.get('email'),
				period_end=period_end,
				subscription_id=transaction_id,
				product_id=product_id,
				stella_credits_grant=stella_credits,
				plan_name=plan_name,
				auth_user_id=auth_user_id
			)
			
			# Update Loops contact properties if email exists
			if subscription.get('email'):
				update_contact_property(subscription['email'], "subscriptionStatus", "subscribed")
		else:
			print('creating new subscription')
			# Create new subscription
			new_sub = ConstellaSubscription.create_subscription(
				stripe_customer_id=None,
				email=event_user_email,
				period_end=period_end,
				subscription_id=transaction_id,
				product_id=product_id,
				auth_user_id=auth_user_id,
				stella_credits_grant=stella_credits + free_stella_credits,
				plan_name=plan_name
			)
			
			update_contact_property(event_user_email, "subscriptionStatus", "subscribed")


	except Exception as e:
		print(f"Error handling successful purchase: {str(e)}")
		raise

def handle_cancellation(event):
	"""
	Handle subscription cancellations. Only for trials, we want to immediately end access.
	Otherwise, let it expire via the period end automatically.
	"""
	try:
		auth_user_id = event.get('app_user_id')
		period_type = event.get('period_type')
		event_user_email = event.get('subscriber_attributes', {}).get('$email', {}).get('value')

		subscription = ConstellaSubscription.get_user_info(
			email=event_user_email,
			auth_user_id=auth_user_id
		)

		update_contact_property(subscription.get('email', event_user_email), "subscriptionStatus", "cancelled")

		# Only for trials, we want to immediately end access, otherwise let it expire
		# Unless we're overriding the trial (i.e. calling from expired method)
		if period_type != 'TRIAL' or not subscription:
			return

		# For cancellations, we might want to update the period_end
		# to when the subscription will actually end
		expiration_at_ms = event.get('expiration_at_ms')
		period_end = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc) if expiration_at_ms else None

		product_id = event.get('product_id')
		plan_name = get_plan_name(product_id)
		
		# Subtract the credits from this plan
		stella_credits_removal = -1 * get_stella_credits(plan_name) 

		subscription = ConstellaSubscription.get_user_info(
			email=event_user_email,
			auth_user_id=auth_user_id
		)
		
		if subscription:
			ConstellaSubscription.create_or_update_subscription_v2(
				_id=str(subscription.get('_id')),
				stripe_customer_id=None,
				email=subscription.get('email'),
				period_end=None,
				subscription_id=subscription.get('subscription_id'),
				product_id=subscription.get('product_id'),
				stella_credits_grant=stella_credits_removal,
				auth_user_id=auth_user_id
			)

	except Exception as e:
		print(f"Error handling cancellation: {str(e)}")
		raise

def handle_expiration(event):
	"""
	Handle subscription expirations
	"""
	try:
		auth_user_id = event.get('app_user_id')
		event_user_email = event.get('subscriber_attributes', {}).get('$email', {}).get('value')
		
		# No need to do anything for now, let it expire automatically via the period end
		# Now becoming in the past

	except Exception as e:
		print(f"Error handling expiration: {str(e)}")
		raise