import os
from utils.constella.files.file_base64 import get_mime_type_from_file_type, mime_to_extension


cloudfront_url_prefix = 'https://d29f4v4r8cofie.cloudfront.net/'



def get_s3_path_for_tenant(tenant_name: str, file_name: str, file_type: str, slug: str = ''):
	"""
	Slug should have a / at the end if provided
	"""
	file_extension = mime_to_extension[get_mime_type_from_file_type(file_type)]
	print("File extension: ", file_extension)
	# using this name to avoid people guessing
	return f'constella/heytenants/{tenant_name}/{slug}{file_name}.{file_extension}'

def create_directories_if_not_there(path_name: str):
    """
    For downloading any path name, create the directories if they don't exist
    """
    # split path_name into directories
    path_name = os.path.dirname(path_name)

    if not os.path.exists(path_name):
        os.makedirs(path_name)
    return path_name

def get_temp_download_location(file_name: str):
    """
    Keep all downloads under downloads/
    """
    temp_path = 'downloads/' + file_name

    # remove https://aicc-library.b-cdn.net/
    temp_path = temp_path.replace('https://aicc-library.b-cdn.net/', '')

    # remove duplicate downloads/
    temp_path = temp_path.replace('downloads/downloads/', 'downloads/')

    # create directory locally here to avoid errors
    create_directories_if_not_there(temp_path)

    return temp_path
    

def get_cleaned_file_name(file_name: str):
    """
    Remove the cloudfront url if it exists
    """
    if cloudfront_url_prefix in file_name:
        return file_name.replace(cloudfront_url_prefix, '')
    return file_name

def delete_file_locally_after_download(file_path: str):
    """
    Delete the file after it has been downloaded
    """
    try:
        os.remove(file_path)
    except:
        pass

def delete_all_downloaded_files(file_paths: list[str]):
    """
    Delete all the files in the list
    """
    for file_path in file_paths:
        if file_path:
            delete_file_locally_after_download(file_path)

