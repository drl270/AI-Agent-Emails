import json
import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from bedrock_api import BedrockAPI
from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

class ProductInquiry:
    def __init__(self, product_catalog_df, catalog_embeddings, api_key, prompts, uri, db):
        load_dotenv()
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.db_handler = MongoDBHandler(uri, db)
        self.product_catalog_df = product_catalog_df
        self.catalog_embeddings = catalog_embeddings
        self.client = OpenAI(api_key=api_key)
        self.prompts = prompts
        self.bedrock_api = BedrockAPI()

    def embed_product_description(self, description):
        try:
            response = self.client.embeddings.create(
                input=description, model="text-embedding-ada-002"
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
        if not indices:
            logger.warning("No products found in vector search")
            return pd.DataFrame()
        closest_products = self.product_catalog_df.iloc[indices[0]].copy()
        closest_products["distance"] = distances[0]
        logger.debug(f"Distances: {distances[0].tolist()}")
        if distance_threshold is not None:
            closest_products = closest_products[
                closest_products["distance"] <= distance_threshold
            ]
            logger.debug(
                f"After distance threshold {distance_threshold}, {len(closest_products)} products remain"
            )
        if filter_features:
            for feature, value in filter_features.items():
                if feature in closest_products.columns:
                    closest_products = closest_products[
                        closest_products[feature] >= value
                    ]
        if closest_products.empty:
            logger.warning("No products found after filtering")
            return pd.DataFrame()
        return closest_products

    def generate_inquiry_response(self, email_content, k=5):
        prompt_extract_doc = self.prompts.get("inquiry_extract")
        if not prompt_extract_doc:
            return "We encountered an issue while processing your inquiry. Please contact us again."
        prompt_extract = prompt_extract_doc["content"].replace("{email_content}", email_content)
        try:
            response_extract = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt_extract}],
                max_tokens=1000,
                temperature=0.2,
            )
            inquiry_details = json.loads(response_extract.choices[0].message.content)
        except Exception as e:
            logger.error(f"Error extracting inquiry details: {e}")
            return "We encountered an issue while processing your inquiry. Please contact us again."

        customer_name = inquiry_details.get("customer_name", "Customer")
        products_of_interest = inquiry_details.get("products_of_interest", [])
        questions = inquiry_details.get("questions", "General inquiry")

        if not products_of_interest:
            return f"Dear {customer_name},\n\nWe couldn't identify the product of interest from your inquiry. Please provide more details or specify a product you'd like information about."

        closest_products = []
        for product_desc in products_of_interest:
            product_embedding = self.embed_product_description(product_desc)
            if product_embedding is None:
                continue
            available_products = self.find_closest_products(
                product_embedding, k, distance_threshold=0.5
            )
            for _, product in available_products.iterrows():
                closest_products.append(
                    {
                        "name": product["name"],
                        "stock": product["stock"],
                        "price": product["price"],
                        "description": product["description"],
                        "distance": product["distance"],
                    }
                )

        if not closest_products:
            return f"Dear {customer_name},\n\nUnfortunately, we don't currently have products matching your inquiry. Please feel free to reach out if you have any other questions."

        closest_products_str = "\n".join(
            [
                f"{p['name']} (Stock: {p['stock']}, Price: {p['price']}, Similarity Distance: {p['distance']:.4f})"
                for p in closest_products
            ]
        )

        # Extract verify_category prompt and call Bedrock
        verify_category_doc = self.prompts.get("verify_category")
        if not verify_category_doc:
            return "We encountered an issue while validating products. Please contact us again."
        verify_prompt = verify_category_doc["content"].replace("{email}", email_content).replace("{similar_items}", closest_products_str)
        bedrock_response = self.bedrock_api.call_bedrock(verify_prompt)
        try:
            filtered_results = json.loads(bedrock_response)
            good_alternatives = filtered_results.get("Good Alternative", [])
        except Exception as e:
            logger.error(f"Error parsing Bedrock response: {e}")
            good_alternatives = []

        # Set closest_products_str: use good_alternatives if non-empty, else empty string
        closest_products_str = "\n".join(good_alternatives) if good_alternatives else ""

        response_prompt_doc = self.prompts.get("inquiry_response")
        if not response_prompt_doc:
            return "We encountered an issue while generating the response. Please contact us again."

        response_prompt = response_prompt_doc["content"].replace("{customer_name}", customer_name).replace("{products_of_interest}", ", ".join(products_of_interest)).replace("{questions}", questions).replace("{closest_products_str}", closest_products_str)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": response_prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            final_response = response.choices[0].message.content
        except Exception as e:
            return "We encountered an issue while generating the response. Please contact us again."

        return final_response