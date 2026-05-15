import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

class MongoDBService:
    """
    Service for MongoDB persistence. 
    Handles account login history for geo-velocity checks and audit log storage.
    """
    def __init__(self, uri: str, db_name: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        # Collections
        self.logins = self.db["account_logins"]
        self.decisions = self.db["transaction_decisions"]
        self.compliance = self.db["compliance_records"]

    async def get_last_login(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent login metadata for an account."""
        try:
            return await self.logins.find_one(
                {"account_id": account_id},
                sort=[("timestamp", -1)]
            )
        except PyMongoError as e:
            logger.error(f"Failed to fetch login history for {account_id}: {e}")
            return None

    async def record_login(self, account_id: str, country: str, lat: float, lng: float, timestamp: Optional[datetime] = None, name: Optional[str] = None):
        """Update or insert the latest login location for an account, incrementing login count."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        try:
            update: Dict[str, Any] = {
                "$set": {
                    "country": country,
                    "lat": lat,
                    "lng": lng,
                    "timestamp": timestamp,
                },
                "$inc": {"login_count": 1},
                "$setOnInsert": {"account_id": account_id},
            }
            if name:
                update["$set"]["name"] = name
            await self.logins.update_one(
                {"account_id": account_id},
                update,
                upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Failed to record login for {account_id}: {e}")

    async def get_account_profile(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Fetch display name and login count for an account."""
        try:
            doc = await self.logins.find_one({"account_id": account_id}, {"name": 1, "login_count": 1, "_id": 0})
            return doc
        except PyMongoError as e:
            logger.error(f"Failed to fetch profile for {account_id}: {e}")
            return None

    async def store_decision(self, result: Dict[str, Any]):
        """Persist a full transaction decision result."""
        try:
            result["created_at"] = datetime.now(timezone.utc)
            await self.decisions.insert_one(result)
        except PyMongoError as e:
            logger.error(f"Failed to store transaction decision: {e}")

    async def get_recent_decisions(self, limit: int = 40) -> List[Dict[str, Any]]:
        """Fetch the most recent transaction decisions for the dashboard feed."""
        try:
            cursor = self.decisions.find().sort("created_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except PyMongoError as e:
            logger.error(f"Failed to fetch recent decisions: {e}")
            return []

    async def close(self):
        """Close the MongoDB connection."""
        self.client.close()
