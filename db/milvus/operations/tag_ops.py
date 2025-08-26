from db.milvus.milvus_client import client as milvus_client
import traceback

"""
Tag specific operations for Milvus
"""

def get_all_tags(tenant_name):
    """
    Get all tag records for a specific tenant from Milvus.
    
    :param tenant_name: The tenant name to query tags for
    :return: List of tag records
    """
    try:
        results = milvus_client.client.query(
            collection_name=milvus_client.collection_name,
            filter=f'tenantName == "{tenant_name}" and recordType == "tag"',
            limit=10000,
            output_fields=["*"]
        )
        
        return results
        
    except Exception as e:
        print(f'Error in Milvus get_all_tags: {e}')
        traceback.print_exc()
        return [] 