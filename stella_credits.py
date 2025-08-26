from datetime import datetime
from db.models.constella.constella_subscription import ConstellaSubscription
from fastapi import HTTPException

def add_credits_to_active_subscriptions():
	try:
		# Get all subscriptions
		all_subscriptions = ConstellaSubscription.get_all()
		
		# Track results
		updated_count = 0
		skipped_count = 0
		
		# Process each subscription
		for sub in all_subscriptions:
			# Skip if no period_end
			if not sub.get('period_end'):
				skipped_count += 1
				continue
				
			# Convert period_end string to datetime if needed
			if isinstance(sub['period_end'], str):
				period_end = datetime.strptime(sub['period_end'], "%Y-%m-%dT%H:%M:%SZ")
			else:
				period_end = sub['period_end']
				
			# Check if subscription is active
			if period_end > datetime.now():
				# Check if plan is empty or null and update to pro_monthly if needed
				plan_name = sub.get('plan_name')
				if plan_name is None or plan_name == '':
					print('updating empty plan to pro_monthly for: ', sub['email'])
					ConstellaSubscription.update_plan(str(sub['_id']), "pro_monthly")
					updated_count += 1
					continue
			else:
				skipped_count += 1
				
		return {
			"status": "success",
			"updated_subscriptions": updated_count,
			"skipped_subscriptions": skipped_count
		}
		
	except Exception as e:
		print(f"Error updating credits: {str(e)}")
		raise HTTPException(status_code=500, detail="Failed to update credits")

