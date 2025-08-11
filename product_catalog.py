import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

class ProductCatalogProcessor:
    def __init__(self, api_key, uri, db):
        load_dotenv()
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.db_handler = MongoDBHandler(uri, db)
        self.client = OpenAI(api_key=api_key)
        self.product_catalog_df = None
        self.embeddings = None

    def embed_product_description(self, description):
        try:
            if not description:
                logger.warning("Empty product description, skipping embedding.")
                return None
            response = self.client.embeddings.create(
                input=description, model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error embedding product description: {e}")
            return None

    def process_catalog(self):
        documents = self.db_handler.find_documents(self.collection_products)
        if not documents:
            raise ValueError(f"No products found in MongoDB {self.collection_products} collection")

        self.product_catalog_df = pd.DataFrame(documents)
        
        self.embeddings = []
        for idx, row in self.product_catalog_df.iterrows():
            if not row['embedding']:
                embedding = self.embed_product_description(row['description'])
                if embedding:
                    self.db_handler.update_document(
                        self.collection_products,
                        {"_id": row['_id']},
                        {"embedding": embedding}
                    )
                    self.embeddings.append(embedding)
                else:
                    self.embeddings.append([])
            else:
                self.embeddings.append(row['embedding'])
        
        self.product_catalog_df['embedding'] = self.embeddings
        
        norms = [np.linalg.norm(emb) for emb in self.embeddings if emb]
        if not norms:
            raise ValueError("No valid embeddings found or generated")

    def get_product_catalog(self):
        return self.product_catalog_df