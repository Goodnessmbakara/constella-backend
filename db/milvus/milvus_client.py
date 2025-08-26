from pymilvus import MilvusClient, DataType
import json
from typing import List, Dict, Any, Optional
import os
from ai.embeddings import our_embedding_dimension

collection_name = "nodes_collection_prod"

class MilvusDBClient:
	def __init__(self, cluster_endpoint: str = None, token: str = None, collection_name: str = None):
		"""
		Initialize Milvus client with cluster endpoint and token
		"""
		self.cluster_endpoint = cluster_endpoint or os.getenv("MILVUS_CLUSTER_ENDPOINT")
		self.token = token or os.getenv("MILVUS_CLUSTER_TOKEN")
		
		if not self.cluster_endpoint or not self.token:
			raise ValueError("Cluster endpoint and token must be provided either as parameters or environment variables")
		
		self.client = MilvusClient(
			uri=self.cluster_endpoint,
			token=self.token
		)
		self.collection_name = collection_name or "nodes_collection"
		
	def create_collection_schema(self):
		"""
		Create schema with all properties from Weaviate collection
		uniqueid as primary key, with dynamic field enabled
		"""
		# Create schema with dynamic field enabled
		schema = self.client.create_schema(
			auto_id=False,
			enable_dynamic_field=True,
		)
		
		# Primary key field
		schema.add_field(
			field_name="uniqueid", 
			datatype=DataType.VARCHAR, 
			is_primary=True,
			max_length=1000
		)
		
		# Required vector field for Milvus (you can adjust the dimension as needed)
		schema.add_field(
			field_name="vector", 
			datatype=DataType.FLOAT_VECTOR, 
			dim=our_embedding_dimension
		)
		
		# Base properties from GeneralWeaviateRecord
		schema.add_field(field_name="created", datatype=DataType.INT64, nullable=True)
		schema.add_field(field_name="lastModified", datatype=DataType.INT64, nullable=True)
		schema.add_field(field_name="recordType", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		schema.add_field(field_name="lastUpdateDevice", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="lastUpdateDeviceId", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		
		# Note properties
		schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=5000, nullable=True)
		schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=200000, nullable=True)
		schema.add_field(field_name="filePath", datatype=DataType.VARCHAR, max_length=2000, nullable=True)
		
		# For complex types like arrays and objects, we'll store as JSON strings
		# and use dynamic fields for flexibility
		#NOTE: tags must be converted to a string before inserting into Milvus (json.dumps(tags))
		schema.add_field(field_name="tags", datatype=DataType.VARCHAR, nullable=True, max_length=65000)  # JSON string
		schema.add_field(field_name="incomingConnections", datatype=DataType.ARRAY, element_type=DataType.VARCHAR, nullable=True, max_length=10000, max_capacity=4096)  # JSON array
		schema.add_field(field_name="outgoingConnections", datatype=DataType.ARRAY, element_type=DataType.VARCHAR, nullable=True, max_length=10000, max_capacity=4096)  # JSON array
		schema.add_field(field_name="tagIds", datatype=DataType.ARRAY, element_type=DataType.VARCHAR, nullable=True, max_length=5000, max_capacity=4096)  # JSON array
		
		schema.add_field(field_name="fileData", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="fileType", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		schema.add_field(field_name="fileText", datatype=DataType.VARCHAR, max_length=200000, nullable=True)
		schema.add_field(field_name="noteType", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		
		# NoteBody properties
		schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=5535, nullable=True)
		schema.add_field(field_name="referenceId", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="referenceTitle", datatype=DataType.VARCHAR, max_length=5000, nullable=True)
		schema.add_field(field_name="type", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		schema.add_field(field_name="position", datatype=DataType.INT64, nullable=True)
		schema.add_field(field_name="journalDate", datatype=DataType.INT64, nullable=True)
		
		# Tag properties
		schema.add_field(field_name="color", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		schema.add_field(field_name="name", datatype=DataType.VARCHAR, max_length=2000, nullable=True)
		
		# DailyNote properties
		schema.add_field(field_name="date", datatype=DataType.VARCHAR, max_length=500, nullable=True)
		
		# Misc properties
		schema.add_field(field_name="foreignId", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="miscData", datatype=DataType.VARCHAR, max_length=65535, nullable=True)
		schema.add_field(field_name="startId", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="startData", datatype=DataType.VARCHAR, max_length=10000, nullable=True)
		schema.add_field(field_name="endId", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
		schema.add_field(field_name="endData", datatype=DataType.VARCHAR, max_length=10000, nullable=True)

		# Tenant name partition key
		schema.add_field(  
			field_name="tenantName",   
			datatype=DataType.VARCHAR,   
			max_length=512,  
			is_partition_key=True,  
		)  
		
		return schema
	
	def create_index_params(self):
		"""
		Create index parameters for the collection
		"""
		index_params = self.client.prepare_index_params()
		
		# Vector search index
		index_params.add_index(
			field_name="vector",
			index_type="AUTOINDEX",
			metric_type="COSINE" 
		)
		
		# Add indexes for commonly searched fields
		index_params.add_index(
			field_name="recordType",
			index_type="BITMAP"
		)
		
		index_params.add_index(
			field_name="title",
			index_type="", # Leave empty for auto index
		)
		
		index_params.add_index(
			field_name="noteType",
			index_type="BITMAP"
		)
		
		index_params.add_index(
			field_name="fileType",
			index_type="BITMAP"
		)
		
		index_params.add_index(
			field_name="name",
			index_type="BITMAP"
		)

		# The "tagIds" array field is frequently filtered via contains operations, so add a bitmap index for quick membership checks
		index_params.add_index(
			field_name="tagIds",
			index_type=""
		)

		# Frequently queried when fetching note bodies linked to other notes
		index_params.add_index(
			field_name="referenceId",
			index_type=""
		)

		# Timestamps are commonly used for sorting and range queries during syncing
		index_params.add_index(
			field_name="created",
			index_type="STL_SORT"
		)
		index_params.add_index(
			field_name="lastModified",
			index_type="STL_SORT"
		)
		
		return index_params
	
	def create_collection(self, drop_existing: bool = False):
		"""
		Create the collection with the defined schema and indexes
		"""
		# Drop existing collection if requested
		if drop_existing and self.client.has_collection(collection_name=self.collection_name):
			self.client.drop_collection(collection_name=self.collection_name)
		
		# Check if collection already exists
		if self.client.has_collection(collection_name=self.collection_name):
			print(f"Collection '{self.collection_name}' already exists")
			return
		
		# Create schema and index parameters
		schema = self.create_collection_schema()
		index_params = self.create_index_params()
		
		# Create collection
		self.client.create_collection(
			collection_name=self.collection_name,
			schema=schema,
			index_params=index_params,
			properties={"partitionkey.isolation": True}  
		)
		
		print(f"Collection '{self.collection_name}' created successfully")
		
		# Check load state
		load_state = self.client.get_load_state(collection_name=self.collection_name)
		print(f"Collection load state: {load_state}")

		
# Initialize client
client = MilvusDBClient(
	cluster_endpoint=os.getenv("MILVUS_CLUSTER_ENDPOINT"),
	token=os.getenv("MILVUS_CLUSTER_TOKEN"),
	collection_name=collection_name
)
	
# Create collection
client.create_collection(drop_existing=False)