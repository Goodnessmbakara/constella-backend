import os
import time
import traceback
from pymongo import MongoClient
from pymongo.read_preferences import ReadPreference
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure

# Get client string from .env file
connection_string = os.getenv("MONGODB_URI")


# Global variables for lazy initialization
_client = None
_db = None

# Export db and client for direct import (will be initialized at end of file)
db = None
client = None


def get_client():
    """Lazy initialization of MongoDB client"""
    global _client
    if _client is None:
        if connection_string:
            try:
                _client = create_mongodb_client()
                print('MongoDB client created successfully')
            except Exception as e:
                print(f'Critical MongoDB connection error: {e}')
                print(
                    'Application may not function properly without MongoDB connection.')
                _client = None
        else:
            print("WARNING: MONGODB_URI environment variable not set.")
            _client = None
    return _client


def get_db():
    """Lazy initialization of MongoDB database"""
    global _db
    if _db is None:
        client = get_client()
        if client:
            try:
                _db = get_database_with_retry(client)
                print('MongoDB database connection established')
            except Exception as e:
                print(f'Database connection failed: {e}')
                _db = None
        else:
            _db = None
    return _db


def create_mongodb_client():
    """Create a MongoDB client with robust configuration for replica set issues"""

    # Check if MongoDB URI is configured
    if not connection_string:
        raise ValueError(
            "MONGODB_URI environment variable is not set. "
            "Please set it to your MongoDB Atlas connection string. "
            "Example: export MONGODB_URI='mongodb+srv://username:password@cluster.mongodb.net/dbname'"
        )

    print(f"Connecting to MongoDB with URI: {connection_string[:50]}...")

    try:
        client = MongoClient(
            connection_string,
            # Read preference settings for replica set resilience
            read_preference=ReadPreference.SECONDARY_PREFERRED,

            # Connection timeout and retry settings - increased for DNS issues
            serverSelectionTimeoutMS=60000,  # 60 seconds
            connectTimeoutMS=30000,  # 30 seconds
            socketTimeoutMS=30000,   # 30 seconds

            # Connection pool settings
            maxPoolSize=10,  # Reduced for better stability
            minPoolSize=1,
            maxIdleTimeMS=300000,  # 5 minutes

            # Retry settings
            retryWrites=True,
            retryReads=True,

            # Heartbeat settings for faster detection of changes
            heartbeatFrequencyMS=10000,  # 10 seconds (default is 10s)

            # Use majority write concern for consistency
            w='majority',
            wtimeoutMS=10000,  # 10 seconds

            # Additional resilience options
            directConnection=False,  # Allow discovery of replica set members

            # DNS resolution settings - removed invalid option
        )

        # Test the connection
        client.admin.command('ping')
        print('Connected to MongoDB Main DB with resilient configuration')
        return client

    except Exception as e:
        print(f'Initial MongoDB connection failed: {e}')
        print('Retrying with degraded configuration...')

        # Fallback configuration with more permissive settings
        try:
            client = MongoClient(
                connection_string,
                read_preference=ReadPreference.NEAREST,  # Most permissive
                serverSelectionTimeoutMS=60000,  # Longer timeout
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                retryWrites=True,
                retryReads=True,
                directConnection=False,
            )

            # Test the connection
            client.admin.command('ping')
            print('Connected to MongoDB with fallback configuration')
            return client

        except Exception as fallback_error:
            print(f'Fallback MongoDB connection also failed: {fallback_error}')

            # Provide specific guidance for common error types
            if "ServerSelectionTimeoutError" in str(fallback_error) or "No replica set members match selector" in str(fallback_error):
                print("\n" + "="*60)
                print("REPLICA SET CONNECTION ISSUE DETECTED")
                print("="*60)
                print("This error indicates your MongoDB Atlas cluster is experiencing")
                print("replica set issues where no primary member is available.")
                print("\nThis commonly happens due to:")
                print("1. Atlas cluster maintenance or upgrades")
                print("2. Network connectivity issues")
                print("3. High load causing primary election delays")
                print("4. Atlas cluster paused/stopped")
                print("\nTo resolve:")
                print(
                    "1. Check your Atlas cluster status in the MongoDB Atlas dashboard")
                print("2. Verify the cluster is not paused")
                print(
                    "3. Try again in a few minutes as elections usually resolve quickly")
                print(
                    "4. Consider upgrading to a higher tier cluster for better reliability")
                print("="*60)

            raise


def get_database_with_retry(client, database_name='main', max_retries=3, delay=2):
    """Get database with retry logic for handling connection issues"""
    for attempt in range(max_retries):
        try:
            db = client[database_name]
            # Test database access
            db.command('ping')
            return db
        except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as e:
            if attempt < max_retries - 1:
                print(f'Database access attempt {attempt + 1} failed: {e}')
                print(f'Retrying in {delay} seconds...')
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print(f'All database access attempts failed. Last error: {e}')
                raise


# Initialize MongoDB connection at module level (after all functions are defined)
def initialize_mongodb():
    """Initialize MongoDB connection at module level"""
    global _client, _db, db, client
    try:
        if connection_string:
            _client = create_mongodb_client()
            _db = get_database_with_retry(_client)
            print('MongoDB setup completed successfully')
        else:
            print("WARNING: MONGODB_URI environment variable not set.")
            print("MongoDB connection will not be available.")
            print("Please set MONGODB_URI to your MongoDB Atlas connection string.")
            _client = None
            _db = None
    except Exception as e:
        print(f'Critical MongoDB connection error: {e}')
        print('Application may not function properly without MongoDB connection.')
        _client = None
        _db = None

    # Update the exported variables
    db = _db
    client = _client


# Initialize MongoDB connection with error handling
try:
    initialize_mongodb()
except Exception as e:
    print(f'Failed to initialize MongoDB during module import: {e}')
    print('Setting db and client to None to allow application to start...')
    db = None
    client = None
