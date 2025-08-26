import base64
import openai
import time
import os
from ai.openai_setup import openai_client
from constants import is_dev
from ai.vision.images import image_to_text
import requests
import json

mock_embedding = [-0.01659369, 0.0025756848, 0.026280126, -0.092003696, -0.01076206, -0.021756688, 0.01623321, -0.022768356, 0.048187982, 0.013209833, 0.053444006, -0.010994627, 0.0064828186, 0.017058825, 0.023617227, 0.07502627, -0.10046915, -0.0040990016, -0.08586391, 0.0613513, 0.060653597, 0.041024905, 0.06711897, -0.07316573, 0.05804884, -0.032861784, -0.023489315, 0.017837925, 0.05242071, -0.06981675, 0.09879466, -0.048513576, -0.0022922433, -0.06507238, 0.0927014, 0.0069537675, 0.03960624, 0.03167569, -0.0095236385, -0.0066630584, -0.069630705, -0.07563094, 0.019070534, 0.045792535, 0.05042063, -0.031559408, -0.05776976, -0.06497935, 0.08149164, 0.046815835, -0.05339749, -0.0046687922, 0.08102651, 0.117958225, 0.03246642, 0.04018766, -0.059118655, 0.03346646, 0.031164043, 0.008965476, -0.003857713, -0.031652432, 0.06451422, 0.009250372, -0.053723086, -0.10093428, 0.020558964, 0.052885845, 0.0007387651, 0.036164243, 0.07716589, 0.019965919, -0.02152412, 0.028140664, 0.01466338, 0.033582743, 0.004535066, 0.03060588, 0.024489356, -0.013523798, 0.03395485, 0.01845423, -0.033024583, 0.016105298, 0.052374195, -0.021617146, -0.15209913, 0.010500422, 0.011587675, -0.061304785, -0.018779824, -0.005988613, 0.025721963, 0.0868407, 0.03921088, -0.0461879, -0.0042850557, -0.030210515, 0.0040931874, -0.012186536, 0.01752396, 0.016337866, -0.002283522, 0.030117488, 0.037745703, 0.031350095, -0.053257953, 0.039629497, -0.020965958, 0.05586271, -0.009855047, -0.034629297, -0.029489556, 0.04949036, 0.07516581, 0.025373112, 0.18447252, -0.17396048, 0.057025544, -0.11981876, 0.045955334, 0.05125787, 0.021070613, -0.038373634, 0.05311841, -0.035327, -0.010180641, -0.01587273, -0.038513176, 0.00014662652, -0.053304467, 0.00829103, 0.055537112, 0.016082041, -0.01816352, -0.0140121905, -0.04225751, 0.0075642574, -0.098515585, 0.06986327, 0.019000763, 0.0403272, 0.010715546, 0.0008510516, -0.027280165, -0.04742051, -0.028233692, 0.06767713, 0.038280606, 0.047373995, -0.019279843, 0.009488753, -0.0134424, 0.0061746663, -0.090189666, -0.063444406, -0.026512692, -0.03297807, -0.052606765, -0.0028852902, 0.040652797, -0.008384057, 0.018989135, -0.042722646, -0.042931955, 0.01444244, -0.013244718, -0.029396528, -0.0885617, 0.032396648, 0.04483901, 0.026070815, 0.022907896, -0.020849675, -0.034629297, 0.0403272, -0.037652675, 0.017442562, -0.037582904, 0.0034739766, -0.0337688, 0.085352264, -0.042931955, 0.03167569, 0.025489395, -0.09935283, 0.04062954, 0.008971291, 0.005064157, -0.023233492, -0.010174827, -0.015779704, 0.049071737, 0.06414211, 0.046466984, -0.1299587, 0.0310245, 0.05186255, -0.022849755, 0.06846786, -0.05907214, -0.00497113, 0.01724488, -0.0193031, 0.025466138, 0.022873012, -0.040210918, 0.079072945, -0.029233731, -0.041955173, 0.11721401, -0.00236056, -0.003261759, 0.004921709, -0.009209672, 0.012709812, 0.08553832, 0.02124504, -0.014768035, 0.10260877, -0.013570312, 0.016965797, 0.14754081, 0.020570593, -0.017151851, 0.14037773, 0.018814709, -0.023838166, 0.002331489, -0.09484102, -0.07214243, 0.030140745, 0.012849353, -0.0071049365, -0.040071376, 0.043885484, -0.056327842, -0.007000281, -0.058700033, -0.08660813, -0.06316533, 0.015965758, -0.049815953, -0.065816596, -0.03483861, -0.0218846, 0.041676093, -0.016151812, 0.04311801, 0.02553591, 0.00876198, -0.06302579, -0.06293276, -0.11572558, 0.045885563, -0.017675128, 0.042792417, 0.0041920287, 0.035164203, -0.013651711, -0.08600345, -0.0060758255, -0.0713517, -0.083677776, -0.111074224, 0.008750351, 0.049257793, -0.023954451, 0.02252416, -0.07465416, -0.011169053, 0.025419625, 0.031210555, -0.035210717, -0.052467223, 0.06930511, -0.0020465937, 0.031791974, 0.043583144, 0.04497855, -0.071305186, -0.022779984, -0.00822126, -0.04786239, -0.01895425, 0.04055977, 0.018419344, -0.07702635, 0.012058624, 0.102329694, -0.021512492, -0.018256547, 0.0021803202, 0.055304546, 0.027187139, 0.03848992, 0.034071136, -0.06730503, 0.00089029735, -0.09609688, 0.053164925, 0.050653197, 0.008936405, 0.047722846, -0.01573319, 0.076142594, 0.023152092, -0.013430771, 0.0061455956, -0.027977867, 0.0140587045, 0.033024583, -0.0013699678, 0.012605158, 0.024303302, -0.085584834, -0.02224508, 0.09628294, 0.060560573, -0.03816432, 0.0210241, -0.038001526, 0.057258114, 0.0544673, -0.026140584, -0.004514716, 0.0025713241, -0.04504832, 0.02402422, 0.055723168, -0.1602855, -0.04697863, -0.005939192, -0.014361042, 0.059397735, 0.05418822, 0.015535507, 0.093120016, -0.009837604, 0.07009584, -0.11256266, 0.01902402, -0.00481124, -0.020303141, 0.07730543, 0.038024783, 0.07595654, -0.04039697, 0.05176952, 0.023838166, 0.072375, 0.017826296, -0.0037472434, 0.036140986, 0.03611773, -0.085491806, -0.028140664, 0.025070773, 0.05469987, -0.003014656, 0.023710255, 0.07223546, 0.07577048, 0.01730302, 0.07870083, 0.033489715, -0.044652957, -0.01908216, -0.024419585, 0.0015669233, 0.017430933, 0.05828141, 0.0765147, 0.02888488, -0.05828141, 0.051304385, 0.07186335, 0.11665585, 0.038815513, 0.07688681, 0.047676332, 0.016279723, 0.059165165, -0.018558884] + [0.0] * (1024 - 384)  # Pad to 1024 dimensions

image_file_types = [
	'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'tiff', 'bmp', 'ico',
	'image/png', 'image/jpg', 'image/jpeg', 'image/gif', 'image/webp',
	'image/svg+xml', 'image/tiff', 'image/bmp', 'image/x-icon'
]

doc_file_types = [
	'pdf', 
	'doc', 
	'docx',
	'application/pdf',
	'application/msword',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
]

embedding_max_tokens = 10000
our_embedding_dimension = 1024

def create_our_embedding(text, is_query: bool = False) -> list:
	"""Create an embedding using the custom Jina embedder service"""
	try:
		# if is query (retrieval vector needed to do vector search), need instruction prefix for optimal results as per Qwen3 Docs
		processed_text = text[:embedding_max_tokens] if len(text) > embedding_max_tokens else text
		if is_query:
			processed_text = f'Instruct: Given a user search query on their notes, retrieve relevant notes that answer the query\nQuery:{processed_text}'
		
		url = "https://constella--embedding-model-embed.modal.run"
		payload = {
			"texts": [processed_text]
		}
		headers = {
			"Authorization": "Bearer zu2k56uh4ut_A8aAaaBEd4sPjmmQ7ulu5ZBcKUn90AzHZAfJHF1e-HBmREeUZbRclnbe_vVpHaAm6ToG1_Yn5Q==",
			"Content-Type": "application/json"
		}
		
		response = requests.post(url, headers=headers, data=json.dumps(payload))
		response.raise_for_status()
		
		result = response.json()
		if not result.get('embeddings'):
			print(f"No embeddings returned for text: {processed_text}")
			return [0] * our_embedding_dimension
		return result.get('embeddings')[0]
		
	except Exception as e:
		print(f"Our embedding error: {e}")
		# return mock_embedding


def create_our_embeddings(texts, is_query: bool = False) -> list:
	"""Create an embedding using the custom Jina embedder service"""
	try:
		# Process each text in the list
		processed_texts = []
		for text in texts:
			# if is query (retrieval vector needed to do vector search), need instruction prefix for optimal results as per Qwen3 Docs
			processed_text = text[:embedding_max_tokens] if len(text) > embedding_max_tokens else text
			if is_query:
				processed_text = f'Instruct: Given a user search query on their notes, retrieve relevant notes that answer the query\nQuery:{processed_text}'
			processed_texts.append(processed_text)
		url = "https://constella--embedding-model-embed.modal.run"
		payload = {
			"texts": processed_texts
		}
		headers = {
			"Authorization": "Bearer zu2k56uh4ut_A8aAaaBEd4sPjmmQ7ulu5ZBcKUn90AzHZAfJHF1e-HBmREeUZbRclnbe_vVpHaAm6ToG1_Yn5Q==",
			"Content-Type": "application/json"
		}
		
		response = requests.post(url, headers=headers, data=json.dumps(payload))
		response.raise_for_status()
		
		result = response.json()
		return result.get('embeddings', [[0] * our_embedding_dimension] * len(processed_texts))
		
	except Exception as e:
		print(f"Our embedding error: {e}")
		# return mock_embedding


def create_embedding(text, use_our_embedding: bool = False) -> list:
	"""Create an embedding with text-embedding-3-small using the OpenAI SDK"""
	if use_our_embedding:
		return create_our_embedding(text)
	
	# if is_dev:
	# 	return mock_embedding
	try:
		num_retries = 10
		for attempt in range(num_retries):
			backoff = 2 ** (attempt + 2)
			try:
				return openai_client.embeddings.create(
					model="text-embedding-3-small",
					input=text[:embedding_max_tokens] if len(text) > embedding_max_tokens else text,
					encoding_format="float",
					dimensions=384
				).data[0].embedding
			except openai.RateLimitError:
				pass
			except openai.APIError as e:
				# * NOTE: we can add a better sleeping logic here, this blocks the thread!!
				raise
			if attempt == num_retries - 1:
				raise
			time.sleep(backoff)
	except Exception as e:
		print("OPENAI ERROR: ", e)
		return create_jina_embedding(text)

def create_file_embedding(file_data: str, file_type:str, text = "", record: dict = None, is_mobile: bool = False):
	if file_type in image_file_types:
		# Do image to text for image file if no text passed in
		if not text:
			text = image_to_text(file_data)
			
			# Set file text to the image's text if no file text exists
			if record and text and not record.get('fileText'):
				record['fileText'] = text
			
			if is_mobile:
				record['title'] = f'<IMAGE-NOTE:> {text}'
				record['imageCaption'] = text

			if text == "Image":
				print("FAILED TO CONVERT IMAGE TO TEXT for file type: ", file_type)
		return create_embedding(text)
	elif file_type in doc_file_types:
		return create_embedding(text[:embedding_max_tokens] if len(text) > embedding_max_tokens else text)
	else: 
		print('returning mock embedding')
		# TODO: implement other file types
		return mock_embedding

def get_image_to_text(file_data: str):
	try:
		text = image_to_text(file_data)
		return text
	except Exception as err:
		raise Exception(f"Failed to convert image to text: {err}") from err

def create_jina_embedding(text: str) -> list:
	"""Create an embedding using the Jina API"""
	try:
		url = "https://api.jina.ai/v1/embeddings"
		headers = {
			"Content-Type": "application/json",
			"Authorization": f"Bearer {os.getenv('JINA_API_KEY', '')}"
		}
		data = {
			"model": "jina-embeddings-v3",
			"task": "text-matching", 
			"late_chunking": False,
			"dimensions": "1024",
			"embedding_type": "float",
			"input": [text]
		}

		response = requests.post(url, headers=headers, json=data)
		if response.status_code != 200:
			raise Exception(f"Failed to create embedding: {response.text}")
			
		return response.json()["data"][0]["embedding"]
	except Exception as e:
		return create_hf_embedding(text)

def create_hf_embedding(text: str) -> list:
	try:
		API_URL = "https://api-inference.huggingface.co/models/BAAI/bge-small-en-v1.5"
		headers = {"Authorization": f"Bearer {os.getenv('HUGGINGFACE_API_KEY', '')}"}

		def query(payload):
			response = requests.post(API_URL, headers=headers, json=payload)
			return response.json()
			
		output = query({
			"inputs": text
		})

		return output
	except Exception as e:
		raise Exception(f"Failed to create embedding: {e}") from e
	