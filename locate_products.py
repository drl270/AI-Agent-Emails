import json
import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from global_state import CustomerMessage, Product, State

logger = logging.getLogger(__name__)

class LocateProductByDescription:
    def __init__(self, api_key, db_handler, product_catalog_df, catalog_embeddings):
        load_dotenv()
        self.api_key = api_key
        self.db_handler = db_handler
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.product_catalog_df = product_catalog_df
        self.catalog_embeddings = catalog_embeddings
        self.client = OpenAI(api_key=api_key)

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

    def find_product_id_by_description(self, description, product_name="none", exclude_product_ids=None):
        normalized_description = description.strip().lower()
        normalized_product_name = product_name.strip().lower() if product_name else "none"

        # First, try lookup by product_name if not "none"
        if normalized_product_name != "none":
            matching_products = self.product_catalog_df[self.product_catalog_df['name'].str.lower() == normalized_product_name]
            if not matching_products.empty:
                product_id = matching_products.iloc[0]['product_id']
                logger.debug(f"Found product by name: {product_name}, product_id: {product_id}")
                if exclude_product_ids is None or product_id not in exclude_product_ids:
                    return product_id

        # Fallback to cosine similarity if no match or product_name is "none"
        embedding = self.embed_product_description(normalized_description)
        if embedding is None:
            logger.error(f"Failed to generate embedding for description: {description}")
            return None
        product_ids, _, _ = self.db_handler.vector_search(
            self.collection_products, embedding, k=1, exclude_product_ids=exclude_product_ids
        )
        product_id = product_ids[0] if product_ids else None
        logger.debug(f"Found product by description: {description}, product_id: {product_id}")
        return product_id

    def locate_product_ids(self, state: State) -> dict:
        try:
            customer_message = state.get("customer_message", CustomerMessage())
            
            seen_ids = set()
            seen_name_desc = set()
            deduplicated_purchase = []
            deduplicated_inquiry = []
            
            for product in customer_message.products_purchase:
                if product.product_id and product.product_id != "none":
                    if product.product_id not in seen_ids:
                        seen_ids.add(product.product_id)
                        deduplicated_purchase.append(product)
                else:
                    key = (product.product_name.lower(), product.product_description.lower())
                    if key not in seen_name_desc:
                        seen_name_desc.add(key)
                        deduplicated_purchase.append(product)
            
            for product in customer_message.products_inquiry:
                if product.product_id and product.product_id != "none":
                    if product.product_id not in seen_ids:
                        seen_ids.add(product.product_id)
                        deduplicated_inquiry.append(product)
                else:
                    key = (product.product_name.lower(), product.product_description.lower())
                    if key not in seen_name_desc:
                        seen_name_desc.add(key)
                        deduplicated_inquiry.append(product)
            
            existing_ids = {product.product_id for product in deduplicated_purchase + deduplicated_inquiry if product.product_id and product.product_id != "none"}
            
            updated_products_purchase = []
            for product in deduplicated_purchase:
                product_id = product.product_id if product.product_id and product.product_id != "none" else self.find_product_id_by_description(
                    description=product.product_description,
                    product_name=product.product_name,
                    exclude_product_ids=existing_ids
                )
                if product_id:
                    product_match = self.product_catalog_df[self.product_catalog_df['product_id'] == product_id]
                    if not product_match.empty:
                        product_data = product_match.iloc[0]
                        updated_dict = {
                            "product_name": product_data['name'],
                            "product_description": product_data['description'],
                            "product_id": product_id,
                            "price": int(product_data.get('price', 0))
                        }
                        if product.quantity > 0:
                            updated_dict["quantity"] = product.quantity
                        else:
                            updated_dict["quantity"] = 1
                        updated_product = product.model_copy(update=updated_dict)
                        existing_ids.add(product_id)
                    else:
                        updated_product = product
                else:
                    updated_product = product
                updated_products_purchase.append(updated_product)
            
            updated_products_inquiry = []
            for product in deduplicated_inquiry:
                product_id = product.product_id if product.product_id and product.product_id != "none" else self.find_product_id_by_description(
                    description=product.product_description,
                    product_name=product.product_name,
                    exclude_product_ids=existing_ids
                )
                if product_id:
                    product_match = self.product_catalog_df[self.product_catalog_df['product_id'] == product_id]
                    if not product_match.empty:
                        product_data = product_match.iloc[0]
                        updated_dict = {
                            "product_name": product_data['name'],
                            "product_description": product_data['description'],
                            "product_id": product_id,
                            "price": int(product_data.get('price', 0))
                        }
                        if product.quantity > 0:
                            updated_dict["quantity"] = product.quantity
                        else:
                            updated_dict["quantity"] = 1
                        updated_product = product.model_copy(update=updated_dict)
                        existing_ids.add(product_id)
                    else:
                        updated_product = product
                else:
                    updated_product = product
                updated_products_inquiry.append(updated_product)
            
            customer_message = customer_message.model_copy(update={
                "products_purchase": updated_products_purchase,
                "products_inquiry": updated_products_inquiry
            })
            
            logger.info("Product IDs updated successfully after deduplication")
            return {"customer_message": customer_message}
            
        except Exception as e:
            logger.error(f"Error updating product IDs: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}