from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from cryptography.hazmat.primitives import serialization, hashes, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from starlette.requests import Request
import base64
import json
import traceback

rsa_private_key = """-----BEGIN PRIVATE KEY-----
MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQCrlgplOrFEp5ny
LddHwEGS704jt/W0PSeHqaU7ELZyFfauKq8UaAqdqD5eCgrsWKaYC8AbboJvuX56
aLcyKqKkAArDhHhoY9qs9fTD29CXbzLiggsjGy19mRF31bXMsZACJh9u5Rp18Izn
VuXgShyjwprUThi6jTWhnfLUH2dYHFps7U8ys/hmqKvs3hKtYSnxnRkOcq7kGdwg
u+g7IbHaHVUdcYCDCd0XkJkmuQ6oyfl1L0yPOxvvQRfOmD7ZME3LAvv8Zvf3AW2M
Ad5yVznmfYVGF6gzFpAazF6H/p3DkXbCGSeYy2h+Q2JQP4aEHs32OSDwGZAkRJpR
M3sCKVyVAgMBAAECggEAAhQe+54epswt+VOqAONDbW4rNj5krQKJpPh+joIzvPA8
V7H02CyGJmXy8szbLYT0aFv0v5BS5wYU/L13LKsnYxEMuv9y6EwqCmraBHkNpEFT
WTrwkMQOmhp9g5lfQAPNpg0EAqH8CajjQsEtfI5WnaWTnmtKHDvDhiSa8WFmV9hO
SlQoXLVRc6PKDXz5eKxKD7jv0W0UJashfE3NuYLnU86i1mZqW/+nE3J5izNwUwmZ
CrlxYh/l7mYdR39u3LpXKXsNa/jqgwVN2xX9t4g5ujv8ig9+TGBB2CeH6eDiSoEs
t4COnHBOX9fuAh0tXooWvnfNCty5AlUPozhuZDpxsQKBgQDxMlc3owb9Vi1FiIbP
MvLWcaC8ZyFitQAn9v0A21+5Yz0ONZb9eDEebGaEH7JhAS1eczj+QoOT8e0IbwKD
IebGe7OjfWUceIJHjsJA+jwA4VERTVu5lvshtOwpkEqgwXAbngzgNWlWQMboIcCg
ZuhBJt4NW46YlCIkRwRMMKHL5QKBgQC2HfxGTmbSnDbRHV2lIjXEit5+xS17V+9w
k6G2cqkPNbnHJjhehoethQSgfCmTWw3y2kBvYgrXFSXyGgBLiAlQw/7KgHTzdOHp
icCo0/8xdJ6KJuNRFJQsFPsHc1I7EAG88q2hKmO3h3i1my7NROpAo6YmlETt0WiT
xpvCZXQi8QKBgQCLYm0WoObcJh35beGCAc5l8LpTxkF72l+huNES2rOh3eCdwohk
KD4yd7BysCKUfmqqh2mrPeLt70PsuMI557CGiVwRodh5sIaRNcW6aSGd3JfNqOfW
A5NTMku75T/LUJ4px5dnRlZ+WubXpRG9YFrds8lk7MEmGYz1a/jm0r/dpQKBgQCr
POqWWOXJpmTMn2YL/Wy9Dy5B2Lj5Pye+nLHzUUCxMn0qSj+6cZhliateEyEskvM8
pAbuNCupLRNu3w/j9Vd8/601Ty+oMwCwjHwAwsUzBUqE8CfRdx4TjO60hLSPIG/h
7/VekvMMAG95ox6Ql/oDKVzy7XsaekpwmNCgKrDWoQKBgQCRiO/4BFz5Pf4NQWqo
QfdgcnmesT+0HZyfD3vVPSnJC2SDOtRdodnzcCH3jMxD2+yM2H83jdqqNA2AQd4F
H+N7ynOfU/HNbg6gCqdwmI/qRA3lOyu9ZcKV3OGB9n83jAfBDBgU7RWckTMUYhwO
dNbjF0azLUmzcMkNNl+z2e/5HQ==
-----END PRIVATE KEY-----"""

def generate_and_save_keys(keys_dir="keys"):
	# Create keys directory if it doesn't exist
	os.makedirs(keys_dir, exist_ok=True)
	
	# Generate key pair
	private_key = rsa.generate_private_key(
		public_exponent=65537,
		key_size=2048
	)

	# Get public key in PEM format
	public_key_pem = private_key.public_key().public_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PublicFormat.SubjectPublicKeyInfo
	)

	# Get private key in PEM format
	private_key_pem = private_key.private_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PrivateFormat.PKCS8,
		encryption_algorithm=serialization.NoEncryption()
	)

	# Save keys to files
	with open(os.path.join(keys_dir, "private_key.pem"), "wb") as f:
		f.write(private_key_pem)
	
	with open(os.path.join(keys_dir, "public_key.pem"), "wb") as f:
		f.write(public_key_pem)

def load_keys(keys_dir="keys"):
	try:
		with open(os.path.join(keys_dir, "private_key.pem"), "rb") as f:
			private_key_pem = f.read()
		
		with open(os.path.join(keys_dir, "public_key.pem"), "rb") as f:
			public_key_pem = f.read()
			
		return private_key_pem, public_key_pem
	except FileNotFoundError:
		print("Keys not found. Generating new keys...")
		generate_and_save_keys(keys_dir)
		return load_keys(keys_dir)


async def decrypt_request(request: Request, call_next):
	# Check if this is a request with selective encryption
	if request.headers.get("x-encryption-type") == "selective" and request.headers.get("content-type") == "application/encrypted+raw":
		# Read the request body
		received_req = await request._receive()

		# Get the body
		old_body = received_req.get("body")
		
		try:
			body = json.loads(old_body)
		except Exception as e:
			print(f"Error parsing body: {str(e)}")
			print(old_body)
			traceback.print_exc()
			return JSONResponse(
				status_code=400,
				content={"error": "Failed to parse request body"}
			)
		try:
			# Get encrypted key and IV from headers
			encrypted_key = base64.b64decode(request.headers.get("x-encrypted-key"))
			encrypted_iv = base64.b64decode(request.headers.get("x-encrypted-iv"))
			
			# Load private key
			private_key = serialization.load_pem_private_key(
				rsa_private_key.encode(),
				password=None
			)
			
			# Decrypt the AES key and IV
			key = private_key.decrypt(
				encrypted_key,
				asym_padding.OAEP(
					mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
					algorithm=hashes.SHA256(),
					label=None
				)
			)
			
			iv = private_key.decrypt(
				encrypted_iv,
				asym_padding.OAEP(
					mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
					algorithm=hashes.SHA256(),
					label=None
				)
			)
			
			# Create AES cipher for decryption
			cipher = Cipher(
				algorithms.AES(key),
				modes.CBC(iv)
			)
			
			# Function to decrypt a single encrypted value
			def decrypt_value(encrypted_value):
				try:
					# Base64 decode
					encrypted_bytes = base64.b64decode(encrypted_value)
					
					# Decrypt using the AES key and IV
					decryptor = cipher.decryptor()
					decrypted_padded = decryptor.update(encrypted_bytes) + decryptor.finalize()
					
					# Remove padding
					unpadder = sym_padding.PKCS7(128).unpadder()
					decrypted_data = unpadder.update(decrypted_padded) + unpadder.finalize()
					
					# Parse the JSON string (we stringify values before encryption)
					return json.loads(decrypted_data.decode('utf-8'))
				except Exception as e:
					print(f"Error decrypting value: {str(e)}")
					return encrypted_value  # Return original if decryption fails
			
			# Function to recursively decrypt sensitive fields in objects
			def decrypt_sensitive_fields(obj):
				if not obj or not isinstance(obj, dict):
					return obj
				
				result = obj.copy()
				
				# Decrypt specific fields
				if 'title' in result and isinstance(result['title'], str):
					result['title'] = decrypt_value(result['title'])
				
				if 'content' in result and isinstance(result['content'], str):
					result['content'] = decrypt_value(result['content'])
				
				# Handle tags array
				if 'tags' in result and isinstance(result['tags'], list):
					for i, tag in enumerate(result['tags']):
						if isinstance(tag, dict) and 'name' in tag:
							result['tags'][i] = tag.copy()
							result['tags'][i]['name'] = decrypt_value(tag['name'])
				
				# Handle tag name
				if 'name' in result and 'uniqueid' in result:
					result['name'] = decrypt_value(result['name'])
				
				return result
		

			# Decrypt fields in record or records
			if 'record' in body and body['record']:
				body['record'] = decrypt_sensitive_fields(body['record'])
			
			if 'note' in body and body['note']:
				body['note'] = decrypt_sensitive_fields(body['note'])
			
			if 'records' in body and isinstance(body['records'], list):
				body['records'] = [decrypt_sensitive_fields(record) for record in body['records']]
			
			# Handle tag or tags at root level
			if 'tag' in body:
				body['tag'] = decrypt_sensitive_fields(body['tag'])
			
			if 'tags' in body and isinstance(body['tags'], list):
				body['tags'] = [decrypt_sensitive_fields(tag) for tag in body['tags']]
			
			
			new_body = json.dumps(body).encode()
			
			# Create a custom receive method that returns the modified body
			async def receive():
				return {"type": "http.request", "body": new_body, "more_body": False}
			
			# Replace the receive method
			request._receive = receive
			
			# Update content type header
			headers = [(k.lower(), v) for k, v in request.headers.items() if k.lower() != "content-type"]
			headers.append(("content-type", "application/json"))
			request.scope["headers"] = [(k.encode() if isinstance(k, str) else k, 
										v.encode() if isinstance(v, str) else v) 
										for k, v in headers]

		except Exception as e:
			print(f"Decryption error: {str(e)}")
			print(body)
			traceback.print_exc()
			return JSONResponse(
				status_code=400,
				content={"error": "Failed to decrypt request fields"}
			)

	# Continue with the request
	response = await call_next(request)
	return response