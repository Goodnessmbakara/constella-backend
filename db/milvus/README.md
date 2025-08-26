## Weaviate -> Milvus Migration

So all the routers in the routes as well as the backend operations need to be changed.
All the routes need to make it so that they use the new Milvus operations.

What we can do is... make the routers keep using the same existing code but for each operation in Weaviate, call the Milvus one as well.

1. Create full migration script
2. Create Milvus equivalent operation routes of the Weaviate ones
   2b. Make the Milvus insert / upsert use the new embedder
3. Ensure Beam.Cloud is running and reliable
4. Test migration script

-   Migrate my main account tenant fully
-   Do all operations and see if they work well
-   Benchmark search queries
-   If all good to go then full migration

## Full Migration

1. Run the full migration script while Weaviate is currently added to
2. Test everything out on variety of users
3. Then migrate all the data from Weaviate -> Milvus that was added during the time
4. Then switch all the queries and main operations to use Milvus
5. If over the next week, all is good, then stop using Weaviate entirely
