import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, VectorDistances, Property, DataType, Tokenization
from weaviate.classes.tenants import Tenant
from tqdm import tqdm

client_source = None
client_target = None

try:
	# TODO: use different credentials for production
	# Best practice: store your credentials in environment variables
	wcd_url = ''
	wcd_api_key = ''

	client_source = weaviate.connect_to_weaviate_cloud(
		cluster_url=wcd_url,                                    # Replace with your Weaviate Cloud URL
		auth_credentials=wvc.init.Auth.api_key(wcd_api_key),    # Replace with your Weaviate Cloud key
	)
except Exception as e:
	print(f"Error connecting to Weaviate Cloud: {e}")
	client = None

nodes_collection_source = None

try:
	# For all objects
	nodes_collection_source = client_source.collections.create(
		name="Nodes",
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
except:
	try:
		# collection must already exist
		# due to a bug where we didn't match the env and..., this is the collection in PROD
		nodes_collection_source = client_source.collections.get("Nodes")
	except Exception as e:
		print(f"Unable to get client collection: {e}")

try:
	# TODO: use different credentials for production
	# Best practice: store your credentials in environment variables
	wcd_url = ''
	wcd_api_key = ''

	client_target = weaviate.connect_to_weaviate_cloud(
		cluster_url=wcd_url,                                    # Replace with your Weaviate Cloud URL
		auth_credentials=wvc.init.Auth.api_key(wcd_api_key),    # Replace with your Weaviate Cloud key
	)
except Exception as e:
	print(f"Error connecting to Weaviate Cloud: {e}")
	client = None

nodes_collection_target = None

try:
	# For all objects
	nodes_collection_target = client_target.collections.create(
		name="NodesProd",
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
except:
	try:
		# collection must already exist
		# due to a bug where we didn't match the env and..., this is the collection in PROD
		nodes_collection_target = client_target.collections.get("NodesProd")
	except Exception as e:
		print(f"Unable to get client collection: {e}")

tenants_src = nodes_collection_source.tenants.get()
tenants_src_list = list(tenants_src.values())
# Sort the tenants alphabetically
tenants_src_list.sort(key=lambda x: x.name)

# print('Tenants source: ', tenants_src_list)

# try:
#     print('Migrating # of tenants: ', len(tenants_src_list))
#     nodes_collection_target.tenants.create(tenants_src_list)
#     print('migrated tenants successfully')
#     tenants_target = nodes_collection_target.tenants.get()
#     print('Tenants target: ', tenants_target)
#     print('# of tenants target: ', len(tenants_target))
# except Exception as e:
#     print(e)

def migrate_data(collection_src, collection_tgt):
	with collection_tgt.batch.fixed_size(batch_size=100) as batch:
		for q in tqdm(collection_src.iterator(include_vector=True)):
			batch.add_object(
				properties=q.properties,
				vector=q.vector["default"],
				uuid=q.uuid
			)
		if collection_tgt.batch.failed_objects:
			print('!! FAILED OBJECTS: ')
			for failed_object in collection_tgt.batch.failed_objects:
				print(failed_object)
	return True

print('Migrating # of tenants: ', len(tenants_src_list))
i = 0
for tenant in tenants_src_list:
	print('Migrating tenant: ', tenant.name)
	try:
		collection_src_tenant = nodes_collection_source.with_tenant(tenant.name)
		collection_tgt_tenant = nodes_collection_target.with_tenant(tenant.name)
		migrate_data(collection_src_tenant, collection_tgt_tenant)
	except Exception as e:
		print("Error migrating tenant collection: ", tenant)
		print(e)
		# Write failed tenant name to file
		with open('failed_tenants.txt', 'a') as f:
			f.write(f"{tenant.name}\n")
		continue
	i += 1
	print('Migrated tenants up to # ', i)


client_source.close()
client_target.close()
