ultra_stella_credits = 500
starter_stella_credits = 20

# Stripe product ids
stripe_ultra_yearly_price_id = 'price_1R1aQGG7vtlDH12t1RVUm4Yb'
stripe_ultra_monthly_price_id = 'price_1R1aPYG7vtlDH12tVRxvzHb4'
stripe_starter_yearly_price_id = 'price_1R1aVQG7vtlDH12tOual041C'
stripe_starter_monthly_price_id = 'price_1R1aUxG7vtlDH12tGx0pOcgx'
# New Horizon plan price id -> maps to Ultra monthly plan
stripe_horizon_monthly_price_id = 'price_1Rjs7UG7vtlDH12tethFAbrA'


def get_plan_name(revenuecat_product_id: str = '', stripe_product_id: str = ''):
	if 'yearly' in revenuecat_product_id or 'yearly' in stripe_product_id:
		if 'base' in revenuecat_product_id or 'base' in stripe_product_id or 'starter' in revenuecat_product_id or 'starter' in stripe_product_id:
			return 'starter_yearly'
		else:
			return 'ultra_yearly'
	elif 'base' in revenuecat_product_id or 'base' in stripe_product_id or 'starter' in revenuecat_product_id or 'starter' in stripe_product_id:
		return 'starter_monthly'
	elif 'ultra' in revenuecat_product_id or 'ultra' in stripe_product_id:
		return 'ultra_monthly'
	else:
		return 'starter_monthly'

def get_plan_name_from_stripe_price_id(stripe_price_id: str):
	if stripe_price_id == stripe_ultra_yearly_price_id:
		return 'ultra_yearly'
	elif stripe_price_id == stripe_ultra_monthly_price_id or stripe_price_id == stripe_horizon_monthly_price_id:
		return 'ultra_monthly'
	elif stripe_price_id == stripe_starter_yearly_price_id:
		return 'starter_yearly'
	elif stripe_price_id == stripe_starter_monthly_price_id:
		return 'starter_monthly'
	else:
		return 'pro_monthly'

def get_stella_credits(plan_name: str):
	if 'starter' in plan_name:
		return starter_stella_credits
	elif 'ultra' in plan_name:
		return ultra_stella_credits
	else:
		return starter_stella_credits

def get_stella_credits_from_stripe_price_id(stripe_price_id: str):
	"""
	Get the stella credits from the stripe price id
	"""
	try:
		if stripe_price_id == stripe_ultra_yearly_price_id or stripe_price_id == stripe_ultra_monthly_price_id or stripe_price_id == stripe_horizon_monthly_price_id:
			return ultra_stella_credits
		else:
			return starter_stella_credits
	except Exception as e:
		print(f"Error getting stella credits from stripe product id: {e}")
		return starter_stella_credits