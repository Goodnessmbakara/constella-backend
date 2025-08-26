import os
import stripe
from db.models.constella.constella_subscription import ConstellaSubscription
from utils.constella.financials.subscriptions import stripe_ultra_yearly_price_id, stripe_ultra_monthly_price_id
stripe.api_key = os.getenv('STRIPE_API_KEY') 


def upgrade_to_ultra(subscription: dict, stripe_customer_id: str, is_yearly: bool):
	"""
	Upgrades a subscription to the Ultra plan (either monthly or yearly).
	Immediately charges the customer for the prorated amount.
	
	Args:
		subscription: The Stripe subscription object
		stripe_customer_id: The Stripe customer ID
		is_yearly: If True, upgrade to yearly Ultra plan; otherwise, upgrade to monthly Ultra plan
	
	Returns:
		The updated subscription object
	"""
	try:		
		# Determine which Ultra price ID to use
		new_price_id = stripe_ultra_yearly_price_id if is_yearly else stripe_ultra_monthly_price_id
		
		# Find the subscription item ID (assuming single item subscription)
		if not subscription.get('items') or not subscription['items'].get('data'):
			raise ValueError("No subscription items found")
		
		subscription_item_id = subscription['items']['data'][0]['id']
		
		# Update the subscription with the new price and immediate proration
		updated_subscription = stripe.Subscription.modify(
			subscription['id'],
			items=[{
				'id': subscription_item_id,
				'price': new_price_id,
			}],
			proration_behavior='always_invoice',  # Immediately charge for prorated amount
		)
		
		return updated_subscription
	except Exception as e:
		# If error + because it's cancelled -> create subscription
		if 'canceled subscription can only update' in str(e).lower():
			# Get the customer's payment methods
			payment_methods = stripe.PaymentMethod.list(
				customer=stripe_customer_id,
				type="card"
			)
			
			# If there are payment methods, set the first one as default
			if payment_methods and payment_methods.data:
				default_payment_method = payment_methods.data[0].id
				
				# Update the customer with the default payment method
				stripe.Customer.modify(
					stripe_customer_id,
					invoice_settings={
						"default_payment_method": default_payment_method
					}
				)
			else:
				raise Exception("No payment methods found for customer")
			
			new_sub = stripe.Subscription.create(
				customer=stripe_customer_id,
				items=[{"price": new_price_id}],
			)
			return new_sub
		print(f"Error upgrading subscription to Ultra: {e}")
		raise
	
def upgrade_constella_subscription_to_ultra(constella_subscription_id: str, stripe_customer_id: str, is_yearly: bool):
	"""
	Upgrades a customer's subscription to the Ultra plan and updates both Stripe and the database.
	
	Args:
		constella_subscription_id: The ID of the subscription in the constella_subscriptions collection
		stripe_customer_id: The Stripe customer ID
		is_yearly: If True, upgrade to yearly Ultra plan; otherwise, upgrade to monthly Ultra plan
	
	Returns:
		dict: Contains 'success' boolean and either 'subscription' data or 'error' message
	"""	
	try:
		# Step 1: Get the customer's subscriptions from Stripe
		stripe_subscriptions = stripe.Subscription.list(customer=stripe_customer_id, status='all')
		
		if not stripe_subscriptions.data:
			return {"success": False, "error": "No active subscriptions found for customer"}
		
		# First try to find active subscriptions
		active_subscriptions = [sub for sub in stripe_subscriptions.data if sub.status == 'active']
		
		if active_subscriptions:
			# Sort by created date (newest first) and take the first one
			subscription = sorted(active_subscriptions, key=lambda x: x.created, reverse=True)[0]
		else:
			# If no active subscriptions, take the most recent one
			subscription = sorted(stripe_subscriptions.data, key=lambda x: x.created, reverse=True)[0]
		
		# Step 2: Upgrade the subscription in Stripe
		updated_subscription = upgrade_to_ultra(subscription, stripe_customer_id, is_yearly)
		
		# Step 3: Update the plan name and other details in the database
		plan_name = 'ultra_yearly' if is_yearly else 'ultra_monthly'
		success = ConstellaSubscription.update_after_plan_change(
			constella_subscription_id, 
			updated_subscription, 
			plan_name
		)
		
		if not success:
			return {
				"success": False, 
				"error": f"Failed to update subscription in database, but Stripe was updated. ID: {constella_subscription_id}"
			}
		
		return {
			"success": True,
			"subscription": updated_subscription
		}
		
	except Exception as e:
		error_message = f"Error upgrading subscription to Ultra: {str(e)}"
		print(error_message)
		return {"success": False, "error": error_message}