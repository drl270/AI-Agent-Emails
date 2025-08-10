import logging
import os

from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_all_databases_and_documents():
    try:
        handler = MongoDBHandler()
        db_names = handler.client.list_database_names()
        all_documents = {}
        for db_name in db_names:
            if db_name not in ['admin', 'config', 'local']:
                db = handler.client[db_name]
                collections = db.list_collection_names()
                all_documents[db_name] = {}
                for collection_name in collections:
                    handler.collection = db[collection_name]
                    documents = handler.find_documents()
                    all_documents[db_name][collection_name] = documents
        handler.close()
        return all_documents
    except Exception as e:
        logger.error(f"Error reading databases and documents: {e}")
        raise
    

load_dotenv()
result = read_all_databases_and_documents()
for db_name, collections in result.items():
    print(f"Database: {db_name}")
    for collection_name, docs in collections.items():
        print(f"  Collection: {collection_name}")
        print(f"    Documents: {docs}")