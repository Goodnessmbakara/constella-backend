# Milvus Migration Setup

This document describes the complete Milvus (Zilliz) migration setup that provides equivalent operations to the existing Weaviate database operations.

## Overview

The migration setup ensures **exact data match** between Weaviate and Milvus operations by:

1. Adding `to_milvus_dict()` methods to all record classes
2. Creating equivalent Milvus operations for all Weaviate operations
3. Integrating Milvus calls into existing Weaviate operations

## Architecture

### Record Classes Enhancement

All Weaviate record classes now have a `to_milvus_dict(tenant_name: str)` method that converts the record to a flat dictionary suitable for Milvus operations:

-   `GeneralWeaviateRecord.to_milvus_dict()`
-   `WeaviateNote.to_milvus_dict()`
-   `WeaviateTag.to_milvus_dict()`
-   `WeaviateMisc.to_milvus_dict()`
-   `WeaviateNoteBody.to_milvus_dict()`
-   `WeaviateDailyNote.to_milvus_dict()`

### Milvus Operations

Located in `db/milvus/operations/general.py`, these operations mirror the Weaviate operations exactly:

#### Insertion Operations

-   `insert_record(tenant_name, record)`
-   `upsert_records(tenant_name, records, type, long_job_id, last_update_device, last_update_device_id)`

#### Update Operations

-   `update_record_vector(tenant_name, unique_id, new_vector, metadata_updates)`
-   `update_record_metadata(tenant_name, unique_id, metadata_updates)`

#### Deletion Operations

-   `delete_record(tenant_name, unique_id, record_type, s3_path)`
-   `delete_records_by_ids(tenant_name, id_list, record_type, s3_paths)`
-   `delete_all_records(tenant_name)`

#### Query Operations

-   `query_by_vector(tenant_name, query_vector, top_k, similarity_setting, include_vector)`
-   `query_by_keyword(tenant_name, keyword, top_k, include_metadata)`
-   `query_by_filter(tenant_name, filter_expr, top_k, get_connected_results)`
-   `get_most_recent_records(tenant_name, limit)`
-   `get_records_by_ids(tenant_name, ids)`
-   `get_record_by_id(tenant_name, record_id)`
-   `sync_by_last_modified(tenant_name, last_sync_datetime, curr_device_id, limit, offset)`

### Weaviate Integration

The existing Weaviate operations in `db/weaviate/operations/general.py` have been enhanced to automatically call the corresponding Milvus operations:

-   **Write Operations**: Milvus operations are called after successful Weaviate operations
-   **Read Operations**: Milvus operations are available but commented out to avoid performance impact

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements_milvus.txt
```

### 2. Environment Variables

Set the following environment variables for Milvus connection:

```bash
export MILVUS_CLUSTER_ENDPOINT="your-milvus-endpoint"
export MILVUS_CLUSTER_TOKEN="your-milvus-token"
```

### 3. Create Milvus Collection

The collection will be created automatically when the client is initialized. The schema includes:

-   All fields from Weaviate records
-   Tenant-based partitioning
-   Optimized indexes for common queries
-   Vector similarity search capabilities

### 4. Verify Setup

Run the test script to verify everything is working:

```bash
python3 test_milvus_migration.py
```

## Usage Examples

### Basic Record Operations

```python
from db.weaviate.records.note import WeaviateNote
from db.milvus.operations import general as milvus_general

# Create a note
note = WeaviateNote(
    uniqueid="note-123",
    vector=[0.1] * 384,
    title="My Note",
    content="Note content",
    # ... other fields
)

# Convert to Milvus format
milvus_dict = note.to_milvus_dict("my-tenant")

# Insert into Milvus
milvus_general.insert_record("my-tenant", note)
```

### Automatic Dual Operations

When using existing Weaviate operations, Milvus operations are automatically called:

```python
from db.weaviate.operations import general as weaviate_general

# This will update both Weaviate AND Milvus
weaviate_general.insert_record("my-tenant", note)
```

## Data Consistency

The migration ensures exact data match by:

1. **Same Parameters**: All Milvus operations use identical parameters to Weaviate operations
2. **Proper Conversion**: Record classes handle the conversion from Weaviate format to Milvus format
3. **Error Handling**: Milvus operations have separate error handling to not interfere with Weaviate operations
4. **Field Mapping**: All Weaviate fields are properly mapped to Milvus fields

## Schema Mapping

| Weaviate Field   | Milvus Field | Type         | Notes                    |
| ---------------- | ------------ | ------------ | ------------------------ |
| uniqueid         | uniqueid     | VARCHAR      | Primary key              |
| vector           | vector       | FLOAT_VECTOR | 768 dimensions           |
| tenant (implied) | tenantName   | VARCHAR      | Partition key            |
| properties.\*    | \*           | Various      | Flattened into main dict |

## Performance Considerations

-   **Write Operations**: Slight overhead due to dual writes
-   **Read Operations**: Milvus queries are commented out by default
-   **Batch Operations**: Optimized for bulk operations
-   **Error Isolation**: Milvus errors don't affect Weaviate operations

## Monitoring and Debugging

Enable Milvus operation logging by uncommenting the debug lines in the Weaviate operations:

```python
# Uncomment these lines in query functions for comparison
# try:
#     milvus_results = milvus_general.query_by_vector(...)
#     print(f"Milvus results count: {len(milvus_results.get('results', []))}")
# except Exception as milvus_e:
#     print(f"Error querying Milvus: {milvus_e}")
```

## Migration Strategy

1. **Phase 1**: Setup (Complete)

    - Install dependencies
    - Configure environment
    - Create collection

2. **Phase 2**: Dual Write

    - All write operations go to both systems
    - Read operations continue from Weaviate

3. **Phase 3**: Data Sync

    - Bulk migrate existing data
    - Verify data consistency

4. **Phase 4**: Read Migration

    - Gradually switch read operations to Milvus
    - Performance testing and optimization

5. **Phase 5**: Full Migration
    - All operations use Milvus
    - Weaviate operations kept for rollback

## Troubleshooting

### Common Issues

1. **Import Errors**: Install `pymilvus` dependency
2. **Connection Errors**: Check environment variables
3. **Schema Errors**: Verify collection creation
4. **Performance Issues**: Monitor dual-write overhead

### Testing

The test script `test_milvus_migration.py` checks:

-   All imports work correctly
-   Record conversion functions properly
-   All Milvus operations are available
-   Integration with Weaviate operations

## Files Modified/Created

### New Files

-   `db/milvus/operations/general.py` - Milvus operations
-   `requirements_milvus.txt` - Dependencies
-   `test_milvus_migration.py` - Test script
-   `MILVUS_MIGRATION_README.md` - This documentation

### Modified Files

-   `db/weaviate/records/general_record.py` - Added `to_milvus_dict()`
-   `db/weaviate/records/note.py` - Added `to_milvus_dict()`
-   `db/weaviate/records/tag.py` - Added `to_milvus_dict()`
-   `db/weaviate/records/misc.py` - Added `to_milvus_dict()`
-   `db/weaviate/records/note_body.py` - Added `to_milvus_dict()`
-   `db/weaviate/records/daily_note.py` - Added `to_milvus_dict()`
-   `db/weaviate/operations/general.py` - Added Milvus operation calls

## Support

For issues with the migration setup, check:

1. Environment variables are set correctly
2. Milvus/Zilliz cluster is accessible
3. All dependencies are installed
4. Collection schema matches expectations
