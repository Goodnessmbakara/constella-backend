from pymongo import MongoClient
from db.mongodb import db
from datetime import datetime
from utils.json import parse_json


def get_collection():
    """Get the collection with lazy initialization"""
    if db is None:
        raise RuntimeError("MongoDB database is not initialized")
    return db['constella_signup']


class ConstellaSignup:
    def __init__(self, email: str):
        self.email = email

    def save(self):
        get_collection().insert_one(self.__dict__)

    @staticmethod
    def get_user_info(email: str):
        return parse_json(get_collection().find_one({"email": email}))

    @staticmethod
    def add_platform(email: str, platform: str):
        get_collection().update_one({"email": email}, {
            "$set": {"platform": platform}})

    @staticmethod
    def get_all():
        return list(get_collection().find({}))

    @staticmethod
    def delete_all():
        get_collection().delete_many({})

    @staticmethod
    def update_user_info(email: str, update_data: dict):
        """
        Update user information by email
        """
        # Add email to update_data if not present
        if "email" not in update_data:
            update_data["email"] = email

        get_collection().update_one(
            {"email": email},
            {"$set": update_data},
            upsert=True  # Create document if it doesn't exist
        )

    @staticmethod
    def get_user_bio(email: str):
        """
        Get user bio information
        """
        user_info = get_collection().find_one({"email": email})
        if user_info:
            return {
                "bio": user_info.get("bio"),
                "display_name": user_info.get("display_name"),
                "avatar_url": user_info.get("avatar_url")
            }
        return None
