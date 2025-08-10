import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBHandler, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        load_dotenv()
        self.uri = os.getenv("MONGODB_URI")
        self.client = MongoClient(self.uri)
        self.db = self.client[os.getenv('MONGO_DB_NAME')]
        try:
            self.client.admin.command('ping')
            logger.info("MongoDB connection established successfully")
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise

    def create_collection(self, collection_name):
        try:
            self.db.create_collection(collection_name)
            logger.info(f"Collection '{collection_name}' created successfully")
        except Exception as e:
            logger.error(f"Error creating collection '{collection_name}': {e}")
            raise

    def insert(self, collection_name, data):
        try:
            collection = self.db[collection_name]
            if isinstance(data, list):
                return self.insert_documents(collection, data)
            else:
                return self.insert_document(collection, data)
        except Exception as e:
            logger.error(f"Error inserting data into '{collection_name}': {e}")
            raise

    def insert_document(self, collection, document):
        try:
            result = collection.insert_one(document)
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error inserting document: {e}")
            raise

    def insert_documents(self, collection, documents):
        try:
            result = collection.insert_many(documents)
            return result.inserted_ids
        except Exception as e:
            logger.error(f"Error inserting documents: {e}")
            raise

    def find_documents(self, collection_name, query={}, limit=0):
        try:
            collection = self.db[collection_name]
            cursor = collection.find(query).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Error finding documents in '{collection_name}': {e}")
            raise

    def vector_search(self, collection_name, query_embedding, k=1, exclude_product_ids=None, min_stock=0, num_candidates=100):
        query_embedding = np.array(query_embedding).astype("float32")
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm
        logger.debug(f"Normalized query embedding norm: {np.linalg.norm(query_embedding)}")

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "default",
                    "path": "embedding",
                    "queryVector": query_embedding.tolist(),
                    "numCandidates": num_candidates,
                    "limit": k
                }
            },
            {
                "$match": {
                    "stock": {"$gt": min_stock}
                }
            },
            {
                "$project": {
                    "product_id": 1,
                    "score": {"$meta": "vectorSearchScore"},
                    "_id": 1
                }
            }
        ]
        if exclude_product_ids:
            pipeline.insert(1, {
                "$match": {
                    "product_id": {"$nin": exclude_product_ids}
                }
            })
        try:
            collection = self.db[collection_name]
            results = list(collection.aggregate(pipeline))
            if not results:
                logger.warning(f"No products found in vector search in '{collection_name}'")
                return [], [], []
            df = pd.DataFrame(self.find_documents(collection_name))
            df['_id'] = df['_id'].astype(str)
            indices = [df.index[df['_id'] == str(result['_id'])].tolist()[0] for result in results]
            distances = [1 - result['score'] for result in results]
            product_ids = [result['product_id'] for result in results]
            logger.debug(f"Vector search results: {results}")
            return product_ids, np.array([distances]), np.array([indices])
        except Exception as e:
            logger.error(f"Error in vector search in '{collection_name}': {e}")
            return [], [], []

    def update_document(self, collection_name, query, update_data):
        try:
            collection = self.db[collection_name]
            result = collection.update_one(query, {'$set': update_data})
            return result.modified_count
        except Exception as e:
            logger.error(f"Error updating document in '{collection_name}': {e}")
            raise

    def delete_document(self, collection_name, query):
        try:
            collection = self.db[collection_name]
            result = collection.delete_one(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting document in '{collection_name}': {e}")
            raise

    def close(self):
        self.client.close()

