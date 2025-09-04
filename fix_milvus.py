import re

def fix_milvus_operations():
    file_path = '/Users/abba/Desktop/constella-backend/db/milvus/operations/general.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Functions that need milvus_client = get_client() added at the beginning
    functions_to_fix = [
        'delete_record',
        'delete_records_by_ids', 
        'delete_all_records',
        'query_by_vector',
        'query_by_vector_with_filter',
        'query_by_keyword',
        'query_by_keyword_with_filter',
        'query_by_filter',
        'query_by_hybrid_with_filter',
        'get_most_recent_records',
        'get_records_by_ids',
        'get_record_by_id',
        'fetch_objects_with_fallback'
    ]
    
    for func_name in functions_to_fix:
        # Pattern to match the function definition and its first executable line
        pattern = rf'(def {func_name}\(.*?\):\s*\n\s*""".*?"""\s*\n)(\s+)(.*)'
        match = re.search(pattern, content, re.DOTALL)
        
        if match and 'milvus_client = get_client()' not in match.group(0):
            # Insert milvus_client = get_client() after docstring
            replacement = f'{match.group(1)}{match.group(2)}milvus_client = get_client()\n{match.group(2)}{match.group(3)}'
            content = content[:match.start()] + replacement + content[match.end():]
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed milvus_client usage in all functions")

if __name__ == '__main__':
    fix_milvus_operations()
