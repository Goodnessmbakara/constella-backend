# MongoDB Connection Setup Guide

This guide helps you configure a resilient MongoDB connection that can handle replica set issues like "No replica set members match selector Primary()".

## Quick Setup

### 1. Set Environment Variable

Add your MongoDB Atlas connection string as an environment variable:

```bash
export MONGODB_URI="mongodb+srv://username:password@your-cluster.mongodb.net/your-database"
```

Or add it to your shell profile file (`.bashrc`, `.zshrc`, etc.):

```bash
echo 'export MONGODB_URI="mongodb+srv://username:password@your-cluster.mongodb.net/your-database"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Test Connection

Run the test script to verify everything is working:

```bash
python3 test_mongodb_resilience.py
```

## Understanding the Replica Set Error

The error "No replica set members match selector Primary()" occurs when:

1. **Atlas Maintenance**: MongoDB Atlas is performing maintenance or upgrades
2. **Primary Election**: The replica set is electing a new primary member
3. **Network Issues**: Connectivity problems between your app and Atlas
4. **Cluster Paused**: Your Atlas cluster is paused or stopped
5. **High Load**: Heavy load causing replica set instability

## Solutions Implemented

### 1. Resilient Connection Configuration

The updated `db/mongodb.py` now includes:

-   **SECONDARY_PREFERRED read preference**: Allows reading from secondary members when primary is unavailable
-   **Extended timeouts**: More time for replica set operations to complete
-   **Automatic retries**: Built-in retry logic with exponential backoff
-   **Fallback configurations**: Multiple connection strategies

### 2. Error Handling in Operations

Key files updated with MongoDB error handling:

-   `utils/constella/retry_queue.py`: Retry queue processing with connection error handling
-   `db/milvus/operations/general.py`: Deleted records operations with fallback logic

### 3. Health Monitoring

New utilities in `utils/mongodb_health.py`:

-   Real-time health checking
-   Recovery waiting mechanisms
-   Detailed status reporting

## Connection Options Explained

### Read Preferences

```python
# SECONDARY_PREFERRED: Prefer secondary, fallback to primary
read_preference=ReadPreference.SECONDARY_PREFERRED

# NEAREST: Use any available member (most resilient)
read_preference=ReadPreference.NEAREST
```

### Timeout Settings

```python
serverSelectionTimeoutMS=30000,  # 30s to find a suitable server
connectTimeoutMS=20000,          # 20s to establish connection
socketTimeoutMS=20000,           # 20s for socket operations
```

### Retry Settings

```python
retryWrites=True,     # Automatically retry failed writes
retryReads=True,      # Automatically retry failed reads
```

## Troubleshooting

### 1. Check Atlas Cluster Status

1. Log into MongoDB Atlas dashboard
2. Navigate to your cluster
3. Check if cluster is:
    - Running (not paused)
    - Not under maintenance
    - Showing green status for all members

### 2. Test Connection String

```bash
# Test with mongo shell if available
mongosh "mongodb+srv://username:password@your-cluster.mongodb.net/your-database"
```

### 3. Check Network Connectivity

```bash
# Test DNS resolution
nslookup your-cluster.mongodb.net

# Test port connectivity
telnet your-cluster.mongodb.net 27017
```

### 4. Monitor Connection Health

```python
from utils.mongodb_health import log_mongodb_health_summary
from db.mongodb import client

log_mongodb_health_summary(client)
```

## Environment-Specific Configuration

### Development

```bash
export MONGODB_URI="mongodb+srv://dev-user:password@dev-cluster.mongodb.net/dev-database"
```

### Production

For production, consider:

1. **Dedicated clusters**: Use dedicated Atlas clusters instead of shared
2. **Multiple regions**: Enable cross-region replica sets
3. **Connection pooling**: Adjust pool sizes based on load
4. **Monitoring**: Set up Atlas monitoring and alerts

## Best Practices

### 1. Connection String Security

-   Never commit connection strings to code
-   Use environment variables or secret management
-   Rotate passwords regularly
-   Use IP whitelisting in Atlas

### 2. Error Handling

-   Always handle MongoDB connection errors gracefully
-   Implement retry logic with exponential backoff
-   Log errors for debugging but don't expose sensitive details
-   Have fallback mechanisms for critical operations

### 3. Performance Optimization

-   Use connection pooling appropriately
-   Set read preferences based on consistency requirements
-   Monitor connection metrics
-   Use indexes effectively to reduce load

## Common Issues and Solutions

| Issue                   | Cause                      | Solution                           |
| ----------------------- | -------------------------- | ---------------------------------- |
| "Connection refused"    | Wrong URI or cluster down  | Check Atlas dashboard, verify URI  |
| "Authentication failed" | Wrong credentials          | Update username/password in URI    |
| "No primary available"  | Replica set election       | Wait or use SECONDARY_PREFERRED    |
| "Timeout"               | Network/performance issues | Increase timeouts, check network   |
| "SSL/TLS errors"        | Certificate issues         | Update PyMongo, check SSL settings |

## Testing Your Setup

Run the test script to verify your configuration:

```bash
python3 test_mongodb_resilience.py
```

This script tests:

-   Basic connectivity
-   Replica set handling
-   Error recovery mechanisms
-   Retry queue operations

## Support

If you continue experiencing issues:

1. Check MongoDB Atlas status page
2. Review Atlas cluster metrics
3. Contact Atlas support if cluster issues persist
4. Consider upgrading cluster tier for better reliability
