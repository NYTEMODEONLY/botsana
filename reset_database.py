#!/usr/bin/env python3
"""
Secure database reset script for Botsana.
This script can only be run by the developer and is not accessible via Discord.

Usage:
    python reset_database.py

This will:
1. Connect to the database using environment variables
2. Drop all existing tables
3. Recreate tables with correct schema (BIGINT for Discord IDs)
4. Log the operation

WARNING: This permanently deletes all data in the database!
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def confirm_action():
    """Get user confirmation before proceeding."""
    print("⚠️  WARNING: This will DELETE ALL DATA in the database!")
    print("This action cannot be undone.")
    print()
    print("What will be lost:")
    print("• Guild configurations")
    print("• Error logs")
    print("• Audit settings")
    print("• All stored data")
    print()
    print("What will be fixed:")
    print("• Database schema updated to BIGINT for Discord IDs")
    print("• All tables recreated with correct field types")
    print("• Foreign key constraints properly set up")
    print()

    while True:
        response = input("Type 'YES DELETE ALL DATA' to confirm: ").strip()
        if response == "YES DELETE ALL DATA":
            return True
        elif response.lower() in ['no', 'cancel', 'quit']:
            return False
        else:
            print("Please type exactly 'YES DELETE ALL DATA' or 'no' to cancel.")

def reset_database():
    """Reset the database with correct schema."""
    try:
        # Import database components
        from database import db_manager, Base

        print("🔄 Connecting to database...")
        # The db_manager initialization will connect to the database

        if not confirm_action():
            print("❌ Database reset cancelled.")
            return False

        print("🗑️  Dropping all existing tables...")

        # Drop all tables in correct order (to handle foreign keys)
        Base.metadata.drop_all(bind=db_manager.engine)

        print("⏳ Waiting for tables to be fully dropped...")
        import time
        time.sleep(2)  # Give it time to complete

        print("🏗️  Creating new tables with correct schema...")

        # Recreate all tables with correct BIGINT schema
        Base.metadata.create_all(bind=db_manager.engine)

        print("✅ Database reset complete!")
        print()
        print("📋 What was fixed:")
        print("• Database schema updated to BIGINT for Discord IDs")
        print("• All tables recreated with correct field types")
        print("• Foreign key constraints properly set up")
        print()
        print("🔄 Next steps:")
        print("• The bot will automatically recreate tables as needed")
        print("• Run bot commands to reconfigure settings")

        return True

    except Exception as e:
        print(f"❌ Database reset failed: {e}")
        return False

def main():
    """Main function."""
    print("🤖 Botsana Database Reset Tool")
    print("=" * 40)

    # Check if we're in the right environment
    if not os.getenv('DATABASE_URL'):
        print("❌ No DATABASE_URL found. Make sure you're running this with proper environment variables.")
        print("This script should be run in the Heroku environment or with .env file containing DATABASE_URL.")
        sys.exit(1)

    print(f"🕒 Starting database reset at {datetime.now()}")
    print()

    success = reset_database()

    if success:
        print()
        print("🎉 Database reset completed successfully!")
        print("The bot should now work without database errors.")
    else:
        print()
        print("💥 Database reset failed or was cancelled.")
        sys.exit(1)

if __name__ == "__main__":
    main()
