
# From a fileType to base64 type (including base64 type -> base64 type)
# The base64type -> base64 type is there to prevent errors where fileType is
# in base64 type but the base64 string does not contain the prefix (due to mobile parsing)
mime_types = {
	'png': 'image/png',
	'jpg': 'image/jpeg',
	'jpeg': 'image/jpeg',
	'gif': 'image/gif',
	'image/png': 'image/png',
	'image/jpg': 'image/jpeg',
	'image/jpeg': 'image/jpeg',
	'image/gif': 'image/gif',
	'image/webp': 'image/webp',
	'webp': 'image/webp',
	'svg': 'image/svg+xml',
	'image/svg+xml': 'image/svg+xml',
	'tiff': 'image/tiff',
	'image/tiff': 'image/tiff',
	'bmp': 'image/bmp',
	'image/bmp': 'image/bmp',
	'ico': 'image/x-icon',
	'image/x-icon': 'image/x-icon',
	'pdf': 'application/pdf',
	'application/pdf': 'application/pdf',
	'txt': 'text/plain',
	'application/msword': 'application/msword',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'doc': 'application/msword',
	'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

# From a MIME type to file extension
mime_to_extension = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp',
    'image/svg+xml': 'svg',
    'image/tiff': 'tiff',
    'image/bmp': 'bmp',
    'image/x-icon': 'ico',
    'application/pdf': 'pdf',
    'text/plain': 'txt',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/octet-stream': 'bin'
}


def get_mime_type_from_file_type(file_type: str) -> str:
	print("Getting mime type from file type: ", file_type)
	if file_type in mime_types:
		return mime_types[file_type]
	else:
		print("File type not found in mime types: ", file_type)
		return 'application/octet-stream'

def clean_base64(base64_string: str, file_type: str = "") -> str:
	"""
	Adds the appropriate 'data:...;base64,' prefix to a base64 string if it's not already present.

	Args:
	base64_string (str): The base64 encoded string.
	file_type (str): The type of the file (e.g., 'png', 'jpeg', 'pdf').

	Returns:
	str: The base64 string with the appropriate prefix.
	"""
	# Dictionary mapping file types to MIME types
 
	# Check if the base64 string already has a prefix or if file type not specified
	if base64_string.startswith('data:') or not file_type:
		return base64_string

	# Get the MIME type for the file type
	mime_type = mime_types.get(file_type.lower(), 'application/octet-stream')

	# Construct the prefix
	prefix = f'data:{mime_type};base64,'

	# Add the prefix to the base64 string
	return prefix + base64_string


def remove_base64_prefix(base64_string: str) -> str:
	"""
	Removes the base64 prefix from a base64 string.

	Args:
	base64_string (str): The base64 string with the prefix.

	Returns:
	str: The base64 string without the prefix.
	"""
	if ';base64,' in base64_string:
		return base64_string.split(';base64,')[1]
	return base64_string