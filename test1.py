import json
import os

from bson import ObjectId
from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler


# Custom JSON encoder to handle ObjectId
class MongoDBJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

if __name__ == "__main__":
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    db = os.getenv('MONGO_DB_NAME')
    handler = MongoDBHandler(uri, db)

    # Fetch all documents from Prompts collection
    documents = handler.find_documents(collection_name="Prompts", query={})

    # Print documents
    if documents:
        print("Documents in Prompts collection:")
        for doc in documents:
            print(json.dumps(doc, cls=MongoDBJSONEncoder, indent=2))
    else:
        print("No documents found in Prompts collection.")

    handler.close()