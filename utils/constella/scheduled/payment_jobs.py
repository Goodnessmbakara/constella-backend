from datetime import datetime
from db.models.constella.constella_subscription import ConstellaSubscription

def distribute_monthly_credits():
    """
    Scheduled job to distribute monthly credits to yearly subscribers
    """
    try:
        print(f"Starting monthly credit distribution at {datetime.now()}")
        ConstellaSubscription.distribute_monthly_credits_to_yearly()
        print(f"Completed monthly credit distribution at {datetime.now()}")
    except Exception as e:
        print(f"Error in monthly credit distribution job: {e}")