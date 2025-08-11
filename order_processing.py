import json
import logging
import os
import random
import string

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

class OrderProcessing:
    def __init__(
        self, api_key, prompts, uri, db, use_saved_product_embeddings: bool = True
    ):
        load_dotenv()
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.db_handler = MongoDBHandler(uri, db)
        OpenAI.api_key = api_key
        self.prompts = prompts
        documents = self.db_handler.find_documents(self.collection_products)
        if not documents:
            logger.error(f"No products found in MongoDB {self.collection_products} collection")
            raise ValueError("No products found in MongoDB")
        self.product_catalog_df = pd.DataFrame(documents)
        self.product_descriptions = (
            self.product_catalog_df.set_index("product_id")[["name", "description"]]
            .apply(lambda x: f"{x['name']} {x['description']}".lower(), axis=1)
            .to_dict()
        )
        self.product_embeddings = (
            self.product_catalog_df["embedding"]
            .apply(lambda x: x if x else None)
            .tolist()
        )
        if use_saved_product_embeddings:
            if None in self.product_embeddings or len(self.product_embeddings) != len(self.product_descriptions):
                logger.warning(
                    f"Missing or mismatched embeddings in MongoDB. Regenerating embeddings."
                )
                self._generate_and_save_embeddings()
            else:
                self.product_embeddings = np.array(self.product_embeddings)
        else:
            logger.info("Generating embeddings for OrderProcessing.")
            self._generate_and_save_embeddings()

        norms = [
            np.linalg.norm(emb) for emb in self.product_embeddings if emb is not None
        ]
        if not norms:
            raise ValueError("No valid embeddings found in MongoDB")
        logger.info(
            f"Order processing embedding norms: min={min(norms)}, max={max(norms)}, mean={np.mean(norms)}"
        )

    def _generate_and_save_embeddings(self):
        self.product_embeddings = [
            self.embed_product_description(desc) if not self.product_catalog_df.iloc[idx]["embedding"]
            else self.product_catalog_df.iloc[idx]["embedding"]
            for idx, desc in enumerate(self.product_descriptions.values())
        ]
        for idx, (product_id, embedding) in enumerate(zip(self.product_descriptions.keys(), self.product_embeddings)):
            if embedding is not None and not self.product_catalog_df.iloc[idx]["embedding"]:
                self.db_handler.update_document(
                    self.collection_products,
                    {"product_id": product_id},
                    {"embedding": embedding}
                )
        self.product_embeddings = np.array(self.product_embeddings)
        logger.info(f"Updated {len(self.product_embeddings)} embeddings in MongoDB")

    def embed_product_description(self, description):
        try:
            response = OpenAI.embeddings.create(
                input=description, model="text-embedding-ada-002"
            )
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            logger.error(f"Error embedding description: {e}")
            return None

    def extract_order_details(self, email_content):
        prompt_doc = self.prompts.get("order_extract")
        if not prompt_doc:
            logger.error("order_extract prompt not found")
            return []
        prompt = prompt_doc["content"].replace("{email_content}", email_content)
        try:
            response = OpenAI.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            order_details_json = response.choices[0].message.content
            order_details = json.loads(order_details_json)
            items = []
            for item in order_details:
                product_id = item.get("Product ID", "").replace(" ", "")
                description = item.get("Product description", "")
                quantity = item.get("Quantity", 1)
                if len(product_id) != 7 or not self.vector_store_has_product(product_id):
                    product_id = self.find_product_id_by_description(description)
                if len(product_id) == 7 and quantity > 0:
                    stock_available = self.check_stock_level(product_id)
                    if quantity == 1000:
                        quantity = stock_available
                    current_item = {
                        "product_id": product_id,
                        "description": description,
                        "quantity": quantity,
                        "stock_available": stock_available,
                    }
                    items.append(current_item)
            return items
        except Exception as e:
            logger.error(f"Error extracting order details: {e}")
            return []

    def find_product_id_by_description(self, description, exclude_product_ids=None):
        normalized_description = description.strip().lower()
        embedding = self.embed_product_description(normalized_description)
        if embedding is None:
            logger.error(f"Failed to generate embedding for description: {description}")
            return None
        product_ids, _, _ = self.db_handler.vector_search(
            self.collection_products, embedding, k=1, exclude_product_ids=exclude_product_ids
        )
        return product_ids[0] if product_ids else None

    def vector_store_has_product(self, product_id):
        return bool(self.db_handler.find_documents(self.collection_products, {"product_id": product_id}))

    def check_stock_level(self, product_id):
        try:
            products = self.db_handler.find_documents(self.collection_products, {"product_id": product_id})
            if products:
                product = products[0]
                logger.debug(f"Found stock for product_id {product_id}: {product['stock']}")
                return product["stock"]
            logger.warning(f"No product found for product_id: {product_id}")
            return 0
        except Exception as e:
            logger.error(f"Error checking stock for product_id {product_id}: {e}")
            return 0

    def process_order(self, order_details):
        order_summary = {}
        for item in order_details:
            product_id = item["product_id"]
            requested_quantity = item["quantity"]
            stock_available = item["stock_available"]
            logger.info(
                f"Product ID: {product_id}, Product Description: {item['description']}, Requested Quantity: {requested_quantity}, Stock Available: {stock_available}"
            )
            quantity_filled = min(requested_quantity, stock_available)
            quantity_unfilled = requested_quantity - quantity_filled
            new_stock_level = stock_available # - quantity_filled
            self.db_handler.update_document(
                self.collection_products,
                {"product_id": product_id},
                {"stock": new_stock_level}
            )
            self.product_catalog_df.loc[
                self.product_catalog_df["product_id"] == product_id, "stock"
            ] = new_stock_level
            order_summary[product_id] = (quantity_filled, quantity_unfilled)
        formatted_summary = self.prepare_order_summary_for_chatgpt(order_summary)
        return formatted_summary

    def prepare_order_summary_for_chatgpt(self, order_summary):
        formatted_summary = []
        for product_id, (quantity_filled, quantity_unfilled) in order_summary.items():
            product_info = f"{{Product ID: {product_id}, quantity filled = {quantity_filled}, quantity unfilled = {quantity_unfilled}}}"
            formatted_summary.append(product_info)
        summary_string = ", ".join(formatted_summary)
        return summary_string

    def generate_order_response(self, summary_string, email_content, order_details):
        prompt_extract_doc = self.prompts.get("order_extract_mentions")
        if not prompt_extract_doc:
            logger.error("order_extract_mentions prompt not found")
            extracted_products = []
        else:
            prompt_extract = prompt_extract_doc["content"].replace("{email_content}", email_content)
            try:
                response_extract = OpenAI.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt_extract}],
                    max_tokens=1000,
                    temperature=0.1,
                )
                extracted_products = json.loads(
                    response_extract.choices[0].message.content
                )
            except Exception as e:
                logger.error(f"Error extracting product mentions: {e}")
                extracted_products = []

        ordered_product_ids = [item["product_id"] for item in order_details]
        similar_items = []
        for product in extracted_products:
            product_desc = product.get("Product description", "")
            product_embedding = self.embed_product_description(product_desc)
            if product_embedding is not None:
                product_ids, _, _ = self.db_handler.vector_search(
                    self.collection_products, product_embedding, k=1, exclude_product_ids=ordered_product_ids
                )
                product_id = product_ids[0] if product_ids else None
                if product_id:
                    product_info = self.db_handler.find_documents(self.collection_products, {"product_id": product_id})
                    if product_info:
                        product_name = product_info[0]["name"]
                        product_description = product_info[0]["description"]
                        concise_description = " ".join(product_description.split()[:50])
                        similar_items.append(f"{product_name} ({product_id}): {concise_description}")
                    else:
                        logger.warning(f"No product info found for ID: {product_id}")
                        similar_items.append(product_id)

        # Extract verify_category prompt and call Bedrock
        verify_category_doc = self.prompts.get("verify_category")
        if not verify_category_doc:
            return "We encountered an issue while validating products. Please contact us again."
        verify_prompt = verify_category_doc["content"].replace("{email}", email_content).replace("{similar_items}", ", ".join(similar_items))
        bedrock_response = self.bedrock_api.call_bedrock(verify_prompt)
        try:
            filtered_results = json.loads(bedrock_response)
            good_alternatives = filtered_results.get("Good Alternative", [])
        except Exception as e:
            logger.error(f"Error parsing Bedrock response: {e}")
            good_alternatives = []

        similar_items = "\n".join(good_alternatives) if good_alternatives else ""

        response_prompt_doc = self.prompts.get("order_response")
        if not response_prompt_doc:
            return "An error occurred while generating the response."
        
        random_code = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
        response_prompt = response_prompt_doc["content"].replace("{summary_string}", summary_string).replace("{email_content}", email_content).replace("{similar_items}", similar_items).replace("{code}", random_code)

        try:
            response = OpenAI.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": response_prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            final_response = response.choices[0].message.content
        except Exception as e:
            final_response = "An error occurred while generating the response."

        return final_response