from db.weaviate.weaviate_client import get_tenant_collection, parse_weaviate_results
from weaviate.classes.query import Filter
import traceback

"""
Tag specific operations
"""
def get_all_tags(tenant_name):
	try:
		tenant_collection = get_tenant_collection(tenant_name)
		query_result = tenant_collection.query.fetch_objects(
			filters=Filter.by_property("recordType").equal("tag"),
			limit=10000
		)
		return parse_weaviate_results(query_result.objects)
	except:
		traceback.print_exc()
		return []

