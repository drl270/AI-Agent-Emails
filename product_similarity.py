import json
import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from bedrock_api import BedrockAPI
from global_state import Category, CustomerMessage, Product, State
from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

class ProductSimilarity:
    def __init__(self, product_catalog_df, catalog_embeddings, api_key, prompts, db_handler):
        load_dotenv()
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.db_handler = db_handler
        self.product_catalog_df = product_catalog_df
        self.catalog_embeddings = catalog_embeddings
        self.client = OpenAI(api_key=api_key)
        self.prompts = prompts
        self.bedrock_api = BedrockAPI()

    def embed_product_description(self, description):
        try:
            response = self.client.embeddings.create(
                input=description, model=os.getenv('OPEN_AI_EMBEDDING_MODEL')
            )
            embedding = response.data[0].embedding
            norm = np.linalg.norm(embedding)
            logger.debug(f"Query embedding norm: {norm}")
            return embedding
        except Exception as e:
            logger.error(f"Error embedding product description: {e}")
            return None

    def find_closest_products(self, product_embedding, k=5, filter_features=None, distance_threshold=None):
        product_ids, distances, indices = self.db_handler.vector_search(
            self.collection_products, product_embedding, k=k, min_stock=0
        )
        if indices is None or len(indices) == 0:
            logger.warning("No products found in vector search")
            return pd.DataFrame()
        
        closest_products = self.product_catalog_df.iloc[indices[0]].copy()
        closest_products["distance"] = distances[0]
        logger.debug(f"Distances: {distances[0].tolist()}")
        
        if distance_threshold is not None:
            distance_mask = closest_products["distance"] <= distance_threshold
            closest_products = closest_products[distance_mask]
            logger.debug(
                f"After distance threshold {distance_threshold}, {len(closest_products)} products remain"
            )
        
        if filter_features:
            for feature, value in filter_features.items():
                if feature in closest_products.columns:
                    feature_mask = closest_products[feature] >= value
                    closest_products = closest_products[feature_mask]
        
        if closest_products.empty:
            logger.warning("No products found after filtering")
            return pd.DataFrame()
        
        return closest_products

    def generate_similar_products(self, state: State, k: int = 5) -> dict:
        customer_message = state.get("customer_message", CustomerMessage())
        
        existing_ids = {product.product_id for product in customer_message.products_purchase + customer_message.products_inquiry if product.product_id}
        recommendations = []
        
        for product in customer_message.products_purchase + customer_message.products_inquiry:
            if product.product_id:
                product_matches = self.product_catalog_df[self.product_catalog_df['product_id'] == product.product_id]
                if not product_matches.empty:
                    product_idx = product_matches.index[0]
                    product_embedding = self.catalog_embeddings[product_idx]
                    available_products = self.find_closest_products(product_embedding, k=k, distance_threshold=0.5)
                    if not available_products.empty:
                        for _, closest_product in available_products.iterrows():
                            if closest_product['stock'] > 0 and closest_product['product_id'] not in existing_ids:
                                recommendations.append(Product(
                                    product_name=closest_product['name'],
                                    product_description=closest_product['description'],
                                    quantity=1,
                                    product_id=closest_product['product_id'],
                                    price=int(closest_product.get('price', 0))
                                ))
                                existing_ids.add(closest_product['product_id'])
            elif product.product_name or product.product_description:
                description = product.product_name or product.product_description
                product_embedding = self.embed_product_description(description)
                if product_embedding is not None:
                    available_products = self.find_closest_products(product_embedding, k=k, distance_threshold=0.5)
                    if not available_products.empty:
                        for _, closest_product in available_products.iterrows():
                            if closest_product['stock'] > 0 and closest_product['product_id'] not in existing_ids:
                                recommendations.append(Product(
                                    product_name=closest_product['name'],
                                    product_description=closest_product['description'],
                                    quantity=1,
                                    product_id=closest_product['product_id'],
                                    price=int(closest_product.get('price', 0))
                                ))
                                existing_ids.add(closest_product['product_id'])
        
        customer_message = customer_message.model_copy(update={
            "products_recommendations": recommendations
        })
        
        logger.info("Product recommendations generated successfully")
        return {"customer_message": customer_message}