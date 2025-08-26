import time
import traceback
from typing import Dict, List, Optional
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure
from pymongo.read_preferences import ReadPreference

def check_mongodb_health(client) -> Dict[str, any]:
    """
    Check MongoDB connection health and return detailed status
    """
    health_status = {
        'healthy': False,
        'primary_available': False,
        'secondaries_available': False,
        'replica_set_status': 'unknown',
        'errors': [],
        'topology_description': None,
        'server_descriptions': []
    }
    
    try:
        # Test basic connectivity
        client.admin.command('ping')
        health_status['healthy'] = True
        
        # Get replica set status
        try:
            rs_status = client.admin.command('replSetGetStatus')
            health_status['replica_set_status'] = 'available'
            
            # Check member states
            members = rs_status.get('members', [])
            for member in members:
                state = member.get('stateStr', 'UNKNOWN')
                if state == 'PRIMARY':
                    health_status['primary_available'] = True
                elif state == 'SECONDARY':
                    health_status['secondaries_available'] = True
                    
            health_status['server_descriptions'] = [
                {
                    'name': member.get('name'),
                    'state': member.get('stateStr'),
                    'health': member.get('health'),
                    'uptime': member.get('uptime')
                }
                for member in members
            ]
            
        except Exception as rs_error:
            health_status['errors'].append(f"Replica set status error: {rs_error}")
            health_status['replica_set_status'] = 'error'
            
        # Get topology description if available
        try:
            if hasattr(client, 'topology_description'):
                td = client.topology_description
                health_status['topology_description'] = {
                    'topology_type': str(td.topology_type) if hasattr(td, 'topology_type') else 'unknown',
                    'server_descriptions': [
                        {
                            'address': str(sd.address),
                            'server_type': str(sd.server_type) if hasattr(sd, 'server_type') else 'unknown',
                            'round_trip_time': getattr(sd, 'round_trip_time', None)
                        }
                        for sd in td.server_descriptions()
                    ] if hasattr(td, 'server_descriptions') else []
                }
        except Exception as td_error:
            health_status['errors'].append(f"Topology description error: {td_error}")
            
    except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
        health_status['errors'].append(f"MongoDB connection error: {mongo_error}")
        health_status['healthy'] = False
        
    except Exception as e:
        health_status['errors'].append(f"Unexpected error: {e}")
        health_status['healthy'] = False
        
    return health_status

def wait_for_mongodb_recovery(client, max_wait_time=120, check_interval=5) -> bool:
    """
    Wait for MongoDB to recover from replica set issues
    
    Args:
        client: MongoDB client
        max_wait_time: Maximum time to wait in seconds
        check_interval: Time between checks in seconds
        
    Returns:
        bool: True if MongoDB recovered, False if timeout
    """
    start_time = time.time()
    
    print(f"Waiting for MongoDB recovery (max {max_wait_time}s)...")
    
    while time.time() - start_time < max_wait_time:
        try:
            health = check_mongodb_health(client)
            
            if health['healthy']:
                if health['primary_available'] or health['secondaries_available']:
                    print(f"MongoDB recovered after {time.time() - start_time:.1f}s")
                    print(f"Primary available: {health['primary_available']}")
                    print(f"Secondaries available: {health['secondaries_available']}")
                    return True
                    
            print(f"MongoDB still recovering... (elapsed: {time.time() - start_time:.1f}s)")
            if health['errors']:
                print(f"Current errors: {health['errors']}")
                
        except Exception as e:
            print(f"Error during recovery check: {e}")
            
        time.sleep(check_interval)
        
    print(f"MongoDB recovery timeout after {max_wait_time}s")
    return False

def get_safe_mongodb_operation(client, operation_func, *args, **kwargs):
    """
    Execute a MongoDB operation with automatic retry and fallback handling
    
    Args:
        client: MongoDB client
        operation_func: Function to execute
        *args, **kwargs: Arguments to pass to the function
        
    Returns:
        Result of the operation or None if all retries failed
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            return operation_func(*args, **kwargs)
            
        except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
            print(f"MongoDB connection error (attempt {attempt + 1}/{max_retries}): {mongo_error}")
            
            if attempt < max_retries - 1:
                # Wait for potential recovery
                if wait_for_mongodb_recovery(client, max_wait_time=30):
                    continue
                else:
                    # If recovery failed, try with different read preference
                    if hasattr(client, 'read_preference') and client.read_preference != ReadPreference.NEAREST:
                        print("Trying with NEAREST read preference as fallback")
                        original_pref = client.read_preference
                        try:
                            client.read_preference = ReadPreference.NEAREST
                            return operation_func(*args, **kwargs)
                        except:
                            client.read_preference = original_pref
                            raise
            else:
                print("All MongoDB operation retries failed")
                raise
                
        except Exception as e:
            print(f"Non-connection error in MongoDB operation: {e}")
            raise
            
    return None

def log_mongodb_health_summary(client):
    """Log a summary of MongoDB health for debugging"""
    try:
        health = check_mongodb_health(client)
        
        print("=== MongoDB Health Summary ===")
        print(f"Overall healthy: {health['healthy']}")
        print(f"Primary available: {health['primary_available']}")
        print(f"Secondaries available: {health['secondaries_available']}")
        print(f"Replica set status: {health['replica_set_status']}")
        
        if health['errors']:
            print("Errors:")
            for error in health['errors']:
                print(f"  - {error}")
                
        if health['server_descriptions']:
            print("Server descriptions:")
            for server in health['server_descriptions']:
                print(f"  - {server['name']}: {server['state']} (health: {server['health']})")
                
        print("==============================")
        
    except Exception as e:
        print(f"Error generating MongoDB health summary: {e}")
        traceback.print_exc() 