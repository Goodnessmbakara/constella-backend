import traceback
from ai.embeddings import create_embedding, create_our_embedding, our_embedding_dimension
from db.weaviate.weaviate_client import client as weaviate_client
from db.weaviate.weaviate_client import nodes_collection
import time
import numpy as np
import json, os

# Add Weaviate imports for target instance
import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, VectorDistances, Property, DataType as WeaviateDataType, Tokenization
from weaviate.classes.tenants import Tenant
from tqdm import tqdm
from datetime import datetime, timedelta
import random
import uuid

from db.milvus.milvus_client import client as milvus_client
from db.milvus.operations.general import query_by_vector
from db.models.constella.constella_subscription import collection as subscription_collection

PROGRESS_FILE = "migration_progress.json"

def _load_progress():
	if os.path.exists(PROGRESS_FILE):
		with open(PROGRESS_FILE) as f:
			return json.load(f).get("last_index", -1)
	return -1

def _save_progress(idx):
	with open(PROGRESS_FILE, "w") as f:
		json.dump({"last_index": idx}, f)

def query_milvus_records(tenant_id: str, query_vector: list, limit: int = 10):
	"""
	Query records from Milvus collection using vector similarity search
	
	Args:
		tenant_id (str): Tenant ID to filter results
		query_vector (list): Query vector to find similar vectors
		limit (int): Maximum number of results to return
		
	Returns:
		List of matching records with scores
	"""
	try:
		# Search with filter
		results = milvus_client.search(
			collection_name=milvus_client.collection_name,
			data=[query_vector],
			filter=f'tenant_name == "{tenant_id}"',
			limit=limit,
			output_fields=["id", "tenant_name", "title", "lastModified", "type"]
		)
		
		return results[0] if results else []
		
	except Exception as e:
		print(f"Error querying Milvus records: {e}")
		return []


def benchmark_milvus_query(tenant_id: str, num_queries: int = 100, limit: int = 10):
	"""
	Benchmark Milvus query performance
	
	Args:
		tenant_id (str): Tenant ID to use for queries
		num_queries (int): Number of queries to run
		limit (int): Number of results per query
		
	Returns:
		Dictionary with benchmark results
	"""
	print(f"\nStarting Milvus benchmark for tenant: {tenant_id}")
	print(f"Running {num_queries} queries with limit {limit}")
	
	# Generate random query vectors
	query_vectors = [np.random.rand(384).tolist() for _ in range(num_queries)]
	
	# Warm up
	print("Warming up...")
	for i in range(5):
		query_milvus_records(tenant_id, query_vectors[0], limit)
	
	# Run benchmark
	print("Running benchmark...")
	latencies = []
	successful_queries = 0
	
	start_time = time.time()
	
	for i, query_vector in enumerate(query_vectors):
		query_start = time.time()
		results = query_milvus_records(tenant_id, query_vector, limit)
		query_end = time.time()
		
		latency = (query_end - query_start) * 1000  # Convert to milliseconds
		latencies.append(latency)
		
		if results:
			successful_queries += 1
		
		if (i + 1) % 10 == 0:
			print(f"Completed {i + 1}/{num_queries} queries")
	
	end_time = time.time()
	total_time = end_time - start_time
	
	# Calculate statistics
	latencies_sorted = sorted(latencies)
	
	results = {
		"total_queries": num_queries,
		"successful_queries": successful_queries,
		"total_time_seconds": total_time,
		"queries_per_second": num_queries / total_time,
		"avg_latency_ms": np.mean(latencies),
		"min_latency_ms": min(latencies),
		"max_latency_ms": max(latencies),
		"p50_latency_ms": latencies_sorted[len(latencies_sorted) // 2],
		"p95_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.95)],
		"p99_latency_ms": latencies_sorted[int(len(latencies_sorted) * 0.99)]
	}
	
	print("\n=== Milvus Benchmark Results ===")
	for key, value in results.items():
		if isinstance(value, float):
			print(f"{key}: {value:.2f}")
		else:
			print(f"{key}: {value}")
	
	return results


def migrate_records_to_milvus(tenant_id: str, days_back: int = 30, batch_size: int = 10):
	"""
	Migrates records from Weaviate to Milvus for a given tenant, preserving all properties.
	
	Args:
		tenant_id (str): The tenant ID to migrate records for
		days_back (int): Number of days back to fetch records from (unused with iterator)
		batch_size (int): Size of each batch to process
	"""
	print(f"Starting migration for tenant: {tenant_id}")
	
	# Get the tenant-specific collection
	try:
		collection_src_tenant = nodes_collection.with_tenant(tenant_id)
	except Exception as e:
		print(f"Error getting tenant collection for {tenant_id}: {e}")
		return 0
	
	total_records = 0
	data_batch = []
	skipped_count = 0
	
	# Helper functions to safely convert values
	def safe_str(value, default=""):
		if value is None:
			return default
		return str(value)
	
	def safe_int(value, default=0):
		if value is None:
			return default
		try:
			return int(value)
		except (ValueError, TypeError):
			return default
	
	def safe_array(value, default=None):
		if value is None:
			return default
		if isinstance(value, list):
			return [str(item) for item in value if item is not None]
		return default
	
	def safe_json_str(value, default=""):
		if value is None:
			return default
		if isinstance(value, (dict, list)):
			try:
				return json.dumps(value)
			except:
				return default
		return str(value)
	
	
	try:
		# Use iterator approach like in migration.py
		skip_count = 7000 if tenant_id == '5DhtfcFQ6kc5rdbJf88kLZjsdhu1' else 67_250 if tenant_id == 'vl3B4KUHuZMnQ7AxVfNLGYgqFTD2' else 0  # Skip the first 2.5k records
		for idx, record in enumerate(tqdm(collection_src_tenant.iterator(include_vector=True))):
			if idx < skip_count:
				continue
			# Get unique ID
			unique_id = str(record.uuid) if hasattr(record, 'uuid') else None
			if not unique_id:
				skipped_count += 1
				continue
			
			# Get properties
			properties = record.properties if hasattr(record, 'properties') else {}
			
			# Build the data record by applying safe functions to all properties
			milvus_record = {
				"uniqueid": unique_id,
				"tenantName": tenant_id,
			}
			
			# Process all properties with appropriate conversion functions based on value type
			for key, value in properties.items():
				# if key = created and it's not int then make it current int timestamp
				if key == 'created' and not isinstance(value, int):
					milvus_record[key] = int(time.time() * 1000)
				
				# if key = content and greater than 100k chars, truncate to 100k chars
				if key == 'content' and value and len(value) > 100000:
					milvus_record[key] = value[:100000]
				
				# if title more than 4.5k chars, 
				if key == 'title' and value and len(value) > 4500:
					milvus_record[key] = value[:4500]

				# Tags in Weaviate are a list of dicts but in Milvus they are a JSON string
				if key == 'tags':
					milvus_record[key] = safe_json_str(value)
				elif value is None:
					milvus_record[key] = safe_str(value)  # Will return default empty string
				elif isinstance(value, (int, float)):
					milvus_record[key] = safe_int(value)
				elif isinstance(value, list):
					milvus_record[key] = safe_array(value) or []
				elif isinstance(value, dict):
					milvus_record[key] = safe_json_str(value)
				else:
					# Default to string for all other types (str, bool, etc.)
					milvus_record[key] = safe_str(value)
			
			# Add missing properties
			if not "text" in milvus_record:
				milvus_record["text"] = ""
			
			# Now we need our new Qwen3 embedding
			# Determine text to embed based on priority: title -> fileText (first 1k chars) -> content
			text_to_embed = ""
			if milvus_record.get("title"):
				text_to_embed = milvus_record["title"]
			elif milvus_record.get("fileText"):
				text_to_embed = milvus_record["fileText"][:3000]
			elif milvus_record.get("content"):
				text_to_embed = milvus_record["content"][:3000]
		
			# Create embedding using our Qwen3 embedding service
			if text_to_embed:
				milvus_record["vector"] = create_our_embedding(text_to_embed)
			else:
				# if nothing to embed, add empty default vector
				milvus_record["vector"] = [0] * our_embedding_dimension

			data_batch.append(milvus_record)
			total_records += 1
			
			# Insert batch when it reaches the specified size
			if len(data_batch) >= batch_size:
				try:
					milvus_client.client.upsert(
						collection_name=milvus_client.collection_name,
						data=data_batch
					)
					print(f"Inserted batch of {len(data_batch)} records into Milvus. Total: {total_records}")
					data_batch = []
				except Exception as e:
					print(f"Error inserting batch into Milvus: {e}")
					# Log first few records for debugging
					print(f"Sample data that failed:")
					for i, d in enumerate(data_batch):
						print("Vector dimension: ", len(d.get('vector')))
					data_batch = []  # Clear the batch to continue
		
		# Insert any remaining records in the final batch
		if data_batch:
			try:
				milvus_client.client.upsert(
					collection_name=milvus_client.collection_name,
					data=data_batch,
				)
            
				print(f"Inserted final batch of {len(data_batch)} records into Milvus")
			except Exception as e:
				print(f"Error inserting final batch into Milvus: {e}")
		
	except Exception as e:
		print(f"Error during migration: {e}")
		traceback.print_exc()
		return total_records
	
	print(f"Migration completed for tenant {tenant_id}. Total records migrated: {total_records}, skipped: {skipped_count}")
	return total_records

def test_query(tenant_id: str, query: str):
	query_vector = create_our_embedding(query, is_query=True)
	results = query_by_vector(tenant_id, query_vector, top_k=10)
	print(f"***{query}")
	for i, result in enumerate(results.get('results', []), 1):
		title = result.get('title', 'No title')
		content = result.get('content', '')[:500]
		file_text = result.get('fileText', '')[:500]
		print(f"{i}. {title} - {content} - {file_text}")

def insert_custom_test_records(tenant_id: str, num_records: int = 10):
	"""
	Insert custom test records with predefined titles and content into Milvus
	for testing purposes.
	"""
	
	# Sample test data with meaningful titles and content
	test_records = [
		{
			"title": "confusing",
			"content": "confusing"
		},
		{
			"title": "working on list",
			"content": "working on list"
		},
		{
			"title": "doubt",
			"content": ""
		},
		{
			"title": "self confusion",
			"content": ""
		}
	]
	
	try:
		data_batch = []
		total_inserted = 0
		
		# Generate the requested number of records, cycling through test data if needed
		for i in range(num_records):
			test_record = test_records[i % len(test_records)]
			
			# Create embedding for the content
			combined_text = f"{test_record['title']} {test_record['content']}"
			vector = create_our_embedding(combined_text, is_query=False)
			
			# Generate unique ID
			unique_id = f"test_{tenant_id}_{i}_{int(time.time())}"
			
			# Create Milvus record
			milvus_record = {
				"uniqueid": unique_id,
				"vector": vector,
				"tenantName": tenant_id,
				"recordType": "note",
				"title": f"{test_record['title']}",
				"content": test_record['content'],
				"created": int(time.time() * 1000),
				"lastModified": int(time.time() * 1000),
				"fileText": "",
				"metadata": f'{{"test_record": true, "batch": {i//10 + 1}}}'
			}
			
			data_batch.append(milvus_record)
			
			# Insert in batches of 5
			if len(data_batch) >= 5:
				try:
					milvus_client.client.upsert(
						collection_name=milvus_client.collection_name,
						data=data_batch
					)
					total_inserted += len(data_batch)
					print(f"Inserted batch of {len(data_batch)} test records. Total: {total_inserted}")
					data_batch = []
				except Exception as e:
					print(f"Error inserting test batch: {e}")
					data_batch = []
		
		# Insert remaining records
		if data_batch:
			try:
				milvus_client.client.upsert(
					collection_name=milvus_client.collection_name,
					data=data_batch
				)
				total_inserted += len(data_batch)
				print(f"Inserted final batch of {len(data_batch)} test records")
			except Exception as e:
				print(f"Error inserting final test batch: {e}")
		
		print(f"Successfully inserted {total_inserted} custom test records for tenant {tenant_id}")
		return total_inserted
		
	except Exception as e:
		print(f"Error inserting custom test records: {e}")
		traceback.print_exc()
		return 0


def migrate_all_tenants_to_milvus(days_back: int = 10):
	"""
	Migrate tenants whose subscriptions have a period_end within the last
	`days_back` days. Tenant IDs are taken from the `auth_user_id` field of
	each subscription document.
	"""
	total_migrated, total_failed = 0, 0
	try:
		cutoff_date = datetime.now() - timedelta(days=days_back)

		# Get distinct auth_user_id values for subscriptions that are still active
		tenants = subscription_collection.distinct(
			"auth_user_id",
			{
				"period_end": {"$gte": cutoff_date},
				"auth_user_id": {"$nin": [None, ""]}
			}
		)

		# Remove any None/empty values and sort for deterministic processing order
		tenants = sorted({t for t in tenants if t})

		# Print tenants
		print(f"Migrating {len(tenants)} tenants")

		last_done = _load_progress()
		for i, tenant_id in enumerate(tenants):
			if i <= last_done:
				continue

			print(f"--- Migrating tenant {i+1}/{len(tenants)}: {tenant_id} ---")
			try:
				migrate_records_to_milvus(tenant_id)
				total_migrated += 1
				_save_progress(i)
			except Exception:
				total_failed += 1
				traceback.print_exc()
				with open("failed_tenants_milvus.txt", "a") as fh:
					fh.write(f"{tenant_id}\n")

		# Clean up the progress file when done
		if os.path.exists(PROGRESS_FILE):
			os.remove(PROGRESS_FILE)

	except Exception:
		traceback.print_exc()

	print(f"Done. migrated={total_migrated}, failed={total_failed}")



# Main execution for all three database benchmarks
if __name__ == "__main__":
	# Define tenant IDs for multilingual testing with timestamps to ensure uniqueness
	import time
	timestamp = str(int(time.time()))
	target_tenant = "afHxmvo6xCYutelTP0QLhCmLCe52"

	# insert_custom_test_records(target_tenant)

	# Get all tenants from the source collection and migrate each one
	
	# migrate_records_to_milvus(target_tenant)

	migrate_all_tenants_to_milvus()

	# Example 4: Migrate ALL tenants to target Weaviate
	# print("\n" + "="*80)
	# print("MIGRATING ALL TENANTS TO TARGET WEAVIATE")
	# print("="*80)
	# migration_results_weaviate = migrate_everything_to_weaviate(
	# 	days_back=300,
	# 	batch_size=100,
	# 	max_records_per_tenant=100000
	# )

	# Query philosophy notes
	# test_query(target_tenant, "confusions")
	# test_query(target_tenant, "constella content idea")
	# test_query(target_tenant, "constella marketing idea")
	# test_query(target_tenant, "how to improve myself")


	# print(f"Successfully migrated {num_migrated_weaviate} records to target Weaviate")
	
	
