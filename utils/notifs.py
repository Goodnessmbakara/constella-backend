import firebase_admin
from firebase_admin import credentials, messaging

"""
Example code:
fcm_token = "cOdi_HEClE2GrD1UCfJjvd:APA91bEsCrIbbFkAqKh82ApL00IOKfqAwrK_wAfg6Ob27dhtX0OXgVxa6r8OW-vUXuPBL6QnWJ5yWJtC5TBWyWsXMWnHcOkftEjCp9XAu6TFJdqaO7hIcEI"
send_ios_image_notification(
	token=fcm_token,
	title="Nik Spotted",
	body="Remember to talk to him about Project X you mentioned",
	image_url="https://pwhvpbacbyksnoeh.public.blob.vercel-storage.com/test/test.jpeg",
	link="https://web.constella.app/app/680ec2b1674ca28fe8c59c99"
)
"""

def initialize_firebase(service_account_path):
	"""
	Initialize Firebase Admin SDK with the service account file.
	
	Args:
		service_account_path: Path to the service account JSON file
	"""
	try:
		if not firebase_admin._apps:
			cred = credentials.Certificate(service_account_path)
			firebase_admin.initialize_app(cred)
		print("Firebase initialized")
	except Exception as e:
		print(f"Error initializing Firebase: {e}")
		raise e

def send_notification(token, title, body, data=None, click_action=None, link=None):
	"""
	Send a notification to a device using FCM.
	
	Args:
		token: The FCM registration token of the target device
		title: Notification title
		body: Notification body
		data: Optional dictionary of data to send with the notification
		click_action: Optional action identifier for Android (activity to open)
		link: Optional URL to open when notification is clicked
	
	Returns:
		The message ID as a string if successful, None otherwise
	"""
	# Set up the notification
	notification = messaging.Notification(
		title=title,
		body=body
	)
	
	# Set up the data payload (if provided)
	if data is None:
		data = {}
	
	# Add link to data if provided
	if link:
		data["link"] = link
	
	# Set up platform-specific configurations
	android_config = None
	apns_config = None
	webpush_config = None
	
	# Configure Android-specific options
	if click_action or link:
		android_config = messaging.AndroidConfig(
			notification=messaging.AndroidNotification(
				click_action=click_action
			)
		)
	
	# Configure APNS (iOS) options
	if link:
		apns_config = messaging.APNSConfig(
			payload=messaging.APNSPayload(
				aps=messaging.Aps(
					# Enable background fetching of notification content
					content_available=True
				),
				custom_data={
					"link": link
				}
			)
		)

	
	# Create the message with platform-specific configurations
	message = messaging.Message(
		notification=notification,
		data=data,
		token=token,
		android=android_config,
		apns=apns_config,
		# webpush=webpush_config
	)
	
	try:
		# Send the message
		response = messaging.send(message)
		return response  # Returns the message ID
	except Exception as e:
		print(f"Failed to send notification: {e}")
		return None

def send_ios_image_notification(token, title, body, image_url, image_data=None, data=None, link=None):
	"""
	Send a notification with an image to an iOS device using FCM.
	
	Args:
		token: The FCM registration token of the target device
		title: Notification title
		body: Notification body
		image_url: URL of the image to display in the notification
		image_data: Optional dictionary of additional image-related data
		data: Optional dictionary of additional data to send with the notification
		link: Optional URL to open when notification is clicked
	
	Returns:
		The message ID as a string if successful, None otherwise
	"""
	# Set up the data payload (if provided)
	if data is None:
		data = {
			"image": image_url
		}
	
	# Add link to data if provided
	if link:
		data["link"] = link
	
	# If image data is provided, add it to the data payload
	if image_data is not None:
		data.update(image_data)
	
	# Configure iOS-specific options
	# For iOS, we'll handle the notification entirely through APNS config
	# and not use the generic notification object to avoid duplicates
	apns = messaging.APNSConfig(
		payload=messaging.APNSPayload(
			aps=messaging.Aps(
				alert=messaging.ApsAlert(
					title=title,
					body=body
				),
				mutable_content=True,  # Required for modifying notification content with image
				content_available=True  # Enable background processing for the notification
			),
			# Custom APNS headers can be added here
			custom_data=data
		),
		fcm_options=messaging.APNSFCMOptions(
			image=image_url  # This sets the image URL for iOS rich notification
		)
	)
	
	# Configure Android-specific options with image
	android_config = messaging.AndroidConfig(
		notification=messaging.AndroidNotification(
			title=title,
			body=body,
			image=image_url
		),
		data=data
	)
	
	# Create the message with platform-specific configuration
	# Note: We're not setting the notification field to avoid duplicates on iOS
	message = messaging.Message(
		data=data,
		token=token,
		apns=apns,
		# android=android_config
	)
	
	try:
		# Send the message
		response = messaging.send(message)
		print(f"Successfully sent iOS image notification: {response}")
		return response
	except Exception as e:
		print(f"Failed to send iOS image notification: {e}")
		return None

def send_multicast_notification(tokens, title, body, data=None):
	"""
	Send a notification to multiple devices using FCM.
	
	Args:
		tokens: List of FCM registration tokens
		title: Notification title
		body: Notification body
		data: Optional dictionary of data to send with the notification
	
	Returns:
		A MulticastMessage response if successful
	"""
	if data is None:
		data = {}
	
	# Create the multicast message
	message = messaging.MulticastMessage(
		notification=messaging.Notification(
			title=title,
			body=body
		),
		data=data,
		tokens=tokens
	)
	
	try:
		# Send the multicast message
		response = messaging.send_multicast(message)
		print(f"Successfully sent message to {response.success_count} devices.")
		return response
	except Exception as e:
		print(f"Failed to send multicast notification: {e}")
		return None

def send_topic_notification(topic, title, body, data=None):
	"""
	Send a notification to devices subscribed to a topic.
	
	Args:
		topic: The topic name to send to
		title: Notification title
		body: Notification body
		data: Optional dictionary of data to send with the notification
	
	Returns:
		The message ID as a string if successful, None otherwise
	"""
	if data is None:
		data = {}
	
	# Create the message
	message = messaging.Message(
		notification=messaging.Notification(
			title=title,
			body=body
		),
		data=data,
		topic=topic
	)
	
	try:
		# Send the message
		response = messaging.send(message)
		return response
	except Exception as e:
		print(f"Failed to send topic notification: {e}")
		return None
