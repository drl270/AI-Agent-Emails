import os

from bson import ObjectId
from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler

load_dotenv()
uri = os.getenv("MONGODB_URI")
db_name = os.getenv("MONGO_DB_NAME")

db_handler = MongoDBHandler(uri, db_name)
result = db_handler.delete_document("Prompts", {"_id": "689bdc588d6aca3409d27f43"})
if result == 0:
    result = db_handler.delete_document("Prompts", {"_id": ObjectId("689bdc588d6aca3409d27f43")})
print(f"Deleted {result} document")