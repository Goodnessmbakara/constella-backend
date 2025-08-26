import traceback
import typing
import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, VectorDistances, Property, DataType, Tokenization
from weaviate.classes.init import AdditionalConfig, Timeout
from weaviate.classes.tenants import Tenant
import os
import requests
import json
from db.weaviate.records.general_record import GeneralWeaviateRecord
#from db.models.constella.constella_feature_request import collection
import pytz
from utils.constella.files.s3.s3 import sign_url
from constants import is_dev

try:
	# TODO: use different credentials for production
	# Best practice: store your credentials in environment variables
	wcd_url = os.getenv("WEAVIATE_URL")
	wcd_api_key = os.getenv("WEAVIATE_API_KEY")

	client = weaviate.connect_to_weaviate_cloud(
		cluster_url=wcd_url,                                    # Replace with your Weaviate Cloud URL
		auth_credentials=wvc.init.Auth.api_key(wcd_api_key),    # Replace with your Weaviate Cloud key
		skip_init_checks=True,
	)
except Exception as e:
	print(f"Error connecting to Weaviate Cloud: {e}")
	client = None

nodes_collection = None

try:
	# For all objects
	nodes_collection = client.collections.create(
		name='NodesProd3' if is_dev else "NodesProd3",
		vectorizer_config=wvc.config.Configure.Vectorizer.none(),
		vector_index_config=Configure.VectorIndex.hnsw(
			distance_metric=VectorDistances.COSINE
		),
		# Multi tenancy to separate each user's data
		multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=True, auto_tenant_activation=True),
		inverted_index_config=Configure.inverted_index(
			index_null_state=True,
			index_property_length=True,
			index_timestamps=True
		),
		replication_config=Configure.replication(
			factor=3,
		),
		additional_config=AdditionalConfig(
			timeout=Timeout(init=120, query=120, insert=120)  # Values in seconds
		)
		# Specify some properties beforehand to set right data type (i.e. obj[] instead of string[])
		# properties=[
		# 	Property(
		# 		name="lastUpdateDeviceId",
		# 		data_type=DataType.TEXT,
		# 		skip_vectorization=True,  # Don't vectorize this property
		# 		tokenization=Tokenization.field  # Use "whitespace" tokenization
		# 	),
		# ]
	)
	print('created nodes collection')
except Exception as e:
	try :
		# collection must already exist
		# due to a bug where we didn't match the env and..., this is the collection in PROD
		nodes_collection = client.collections.get('NodesProd3' if is_dev else "NodesProd3")
	except Exception as e2:
		print(f"Unable to get client collection: {e2}")

def create_tenant(name):
	nodes_collection.tenants.create(
		tenants=[
			Tenant(name=name),
		]
	)

def get_tenant_collection(name):
	try:
		return nodes_collection.with_tenant(name)
	except:
		print('creating tenant')
		create_tenant(name)
		return nodes_collection.with_tenant(name)

def delete_tenant(tenant_name):
	try:
		nodes_collection.tenants.remove([tenant_name])
	except Exception as e:
		print(f"Error deleting tenant {tenant_name}: {e}")
		traceback.print_exc()
		raise e


def parse_weaviate_results(results):
	"""
	Converts results into a list[JSON] for easy
	parsing for the frontends
	"""
	parsed_objs = [] 

	for result in results:
		parsed_objs.append(parse_weaviate_result(result))	

	return parsed_objs
 
def parse_weaviate_result(result):
	if result.properties.get('fileData') and 'cloudfront' in result.properties['fileData']:
		result.properties['fileData'] = sign_url(result.properties['fileData'])
	return {
		**result.properties,
		# adding this after unpack to prevent override
		"uniqueid": str(result.uuid),
		"score": result.metadata.distance if hasattr(result.metadata, 'distance') else -1,
		"vector": result.vector,
		"last_updated_utc": result.metadata.last_update_time
	}