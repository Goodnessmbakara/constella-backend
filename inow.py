import sys
import requests
import json

# Example run: python3 inow.py https://www.constella.app

def index_now(url):
    # IndexNow API endpoint
    api_url = "https://api.indexnow.org/IndexNow"

    # Your website details
    host = "www.constella.app"
    key = "4295dc42ceec4b4bb625a68aebdaacb5"
    key_location = f"https://{host}/{key}.txt"

    # Prepare the payload
    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": [url]
    }

    # Send the POST request
    headers = {"Content-Type": "application/json; charset=utf-8"}
    response = requests.post(api_url, data=json.dumps(payload), headers=headers)

    # Check the response
    if response.status_code == 200:
        print(f"Successfully submitted {url} to IndexNow")
    else:
        print(f"Failed to submit {url}. Status code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python index_now.py <url>")
        sys.exit(1)

    url_to_index = sys.argv[1]
    index_now(url_to_index)