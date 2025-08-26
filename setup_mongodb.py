#!/usr/bin/env python3
"""
MongoDB Setup and Configuration Script

This script helps you set up a resilient MongoDB connection for handling
replica set issues like "No replica set members match selector Primary()".
"""

import os
import sys
import getpass

def setup_mongodb_uri():
    """Interactive setup for MongoDB URI"""
    print("MongoDB Connection Setup")
    print("=" * 40)
    print()
    
    print("This script will help you configure a resilient MongoDB connection.")
    print("You'll need your MongoDB Atlas connection string.")
    print()
    
    # Check if URI is already set
    current_uri = os.getenv("MONGODB_URI")
    if current_uri:
        print(f"Current MONGODB_URI: {current_uri[:50]}...")
        use_current = input("Use current URI? (y/n): ").lower().strip()
        if use_current == 'y':
            return current_uri
    
    print("\nPlease provide your MongoDB Atlas connection string.")
    print("It should look like: mongodb+srv://username:password@cluster.mongodb.net/database")
    print()
    
    # Get MongoDB URI from user
    mongodb_uri = input("MongoDB URI: ").strip()
    
    if not mongodb_uri:
        print("❌ No URI provided. Exiting.")
        return None
    
    # Basic validation
    if not (mongodb_uri.startswith("mongodb://") or mongodb_uri.startswith("mongodb+srv://")):
        print("❌ Invalid URI format. Should start with 'mongodb://' or 'mongodb+srv://'")
        return None
    
    # Test the connection
    print("\n🔄 Testing connection...")
    success = test_mongodb_connection(mongodb_uri)
    
    if success:
        print("✅ Connection successful!")
        
        # Offer to save to shell profile
        save_permanent = input("\nSave to shell profile for permanent use? (y/n): ").lower().strip()
        if save_permanent == 'y':
            save_to_profile(mongodb_uri)
        else:
            print("\n💡 To use this URI, set it as an environment variable:")
            print(f'export MONGODB_URI="{mongodb_uri}"')
        
        return mongodb_uri
    else:
        print("❌ Connection failed. Please check your URI and try again.")
        return None

def test_mongodb_connection(uri):
    """Test MongoDB connection with the given URI"""
    try:
        # Temporarily set the environment variable
        os.environ["MONGODB_URI"] = uri
        
        # Import and test
        from pymongo import MongoClient
        from pymongo.read_preferences import ReadPreference
        
        client = MongoClient(
            uri,
            read_preference=ReadPreference.SECONDARY_PREFERRED,
            serverSelectionTimeoutMS=10000,  # Shorter timeout for testing
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
        
        # Test ping
        client.admin.command('ping')
        client.close()
        
        return True
        
    except Exception as e:
        print(f"Connection error: {e}")
        return False

def save_to_profile(uri):
    """Save MongoDB URI to shell profile"""
    shell = os.getenv('SHELL', '/bin/bash')
    
    if 'zsh' in shell:
        profile_file = os.path.expanduser('~/.zshrc')
    elif 'bash' in shell:
        profile_file = os.path.expanduser('~/.bashrc')
    else:
        profile_file = os.path.expanduser('~/.profile')
    
    try:
        # Check if URI is already in profile
        if os.path.exists(profile_file):
            with open(profile_file, 'r') as f:
                content = f.read()
                if 'MONGODB_URI' in content:
                    print(f"⚠️  MONGODB_URI already exists in {profile_file}")
                    replace = input("Replace existing entry? (y/n): ").lower().strip()
                    if replace != 'y':
                        return
        
        # Add to profile
        export_line = f'export MONGODB_URI="{uri}"\n'
        
        with open(profile_file, 'a') as f:
            f.write(f'\n# MongoDB Connection\n')
            f.write(export_line)
        
        print(f"✅ Saved to {profile_file}")
        print("🔄 Restart your terminal or run: source " + profile_file)
        
    except Exception as e:
        print(f"❌ Failed to save to profile: {e}")
        print("💡 Manually add this line to your shell profile:")
        print(f'export MONGODB_URI="{uri}"')

def run_resilience_test():
    """Run the full resilience test"""
    print("\n" + "=" * 50)
    print("Running MongoDB Resilience Tests")
    print("=" * 50)
    
    try:
        # Import test function
        from test_mongodb_resilience import test_mongodb_connection, test_retry_mechanism
        
        # Run tests
        connection_ok = test_mongodb_connection()
        retry_ok = test_retry_mechanism()
        
        if connection_ok and retry_ok:
            print("\n🎉 All tests passed! Your MongoDB connection is properly configured.")
        else:
            print("\n⚠️  Some tests failed. Check the output above for details.")
            
    except ImportError as e:
        print(f"❌ Could not import test functions: {e}")
    except Exception as e:
        print(f"❌ Test execution error: {e}")

def show_troubleshooting_info():
    """Show troubleshooting information"""
    print("\n" + "=" * 50)
    print("Troubleshooting Replica Set Issues")
    print("=" * 50)
    print()
    print("If you see 'No replica set members match selector Primary()':")
    print()
    print("1. 🔍 Check Atlas Cluster Status")
    print("   - Log into MongoDB Atlas dashboard")
    print("   - Verify cluster is running (not paused)")
    print("   - Check for maintenance windows")
    print()
    print("2. ⏱️  Wait for Primary Election")
    print("   - Replica set elections usually complete within 30 seconds")
    print("   - Try your operation again after a brief wait")
    print()
    print("3. 🔧 Use Resilient Read Preferences")
    print("   - Our code now uses SECONDARY_PREFERRED by default")
    print("   - This allows reading from secondaries when primary is unavailable")
    print()
    print("4. 📊 Monitor Connection Health")
    print("   - Use: from utils.mongodb_health import log_mongodb_health_summary")
    print("   - Run: log_mongodb_health_summary(client)")
    print()
    print("5. 🆙 Consider Cluster Upgrade")
    print("   - Higher tier Atlas clusters have better availability")
    print("   - Consider dedicated clusters for production")

def main():
    """Main setup flow"""
    print("🔧 MongoDB Resilience Setup Wizard")
    print("=" * 40)
    print()
    
    while True:
        print("What would you like to do?")
        print("1. Configure MongoDB connection")
        print("2. Test current connection")
        print("3. Show troubleshooting info")
        print("4. Exit")
        print()
        
        choice = input("Enter choice (1-4): ").strip()
        
        if choice == "1":
            uri = setup_mongodb_uri()
            if uri:
                run_test = input("\nRun resilience tests now? (y/n): ").lower().strip()
                if run_test == 'y':
                    run_resilience_test()
        
        elif choice == "2":
            current_uri = os.getenv("MONGODB_URI")
            if current_uri:
                print(f"Testing connection with: {current_uri[:50]}...")
                success = test_mongodb_connection(current_uri)
                if success:
                    print("✅ Connection successful!")
                    run_resilience_test()
                else:
                    print("❌ Connection failed.")
            else:
                print("❌ MONGODB_URI not set. Use option 1 to configure.")
        
        elif choice == "3":
            show_troubleshooting_info()
        
        elif choice == "4":
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice. Please enter 1-4.")
        
        print()

if __name__ == "__main__":
    main() 