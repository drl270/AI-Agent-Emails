import json
import logging
import os

import numpy as np
import openai
from dotenv import load_dotenv
from pydantic import ValidationError

from bedrock_api import BedrockAPI
from global_state import (Category, CustomerMessage, OrderStatus, Product,
                          State, VerificationResult)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailProcessor:
    def __init__(self, api_key, prompts, db_handler):
        load_dotenv()
        openai.api_key = api_key
        self.embeddings = None
        self.vector_store = None
        self.db_handler = db_handler
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.prompts = prompts
        self.bedrock_api = BedrockAPI(region=os.getenv('AWS_REGION', 'us-east-1'))

    def safe_get(self, obj, key, default=None):
        if hasattr(obj, key):
            return getattr(obj, key)
        elif isinstance(obj, dict):
            return obj.get(key, default)
        return default

    def embed_email_content(self, content):
        try:
            response = openai.embeddings.create(
                input=content,
                model=os.getenv('OPEN_AI_EMBEDDING_MODEL'),
            )
            embedding = response.data[0].embedding
            norm = np.linalg.norm(embedding)
            logger.debug(f"Email embedding norm: {norm}")
            return embedding
        except Exception as e:
            logger.error(f"Error embedding email content: {e}")
            return None

    def verify_email_extraction(self, state: State) -> dict:
        try:
            system_prompt_doc = self.prompts.get("extract_system_verification")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                system_prompt_doc = None
                logger.error("Prompt 'extract_system_verification' with role 'system' not found")

            user_prompt_doc = self.prompts.get("extract_info_verification")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                user_prompt_doc = None
                logger.error("Prompt 'extract_info_verification' with role 'user' not found")

            if not system_prompt_doc or not user_prompt_doc:
                return {"verification_result": VerificationResult(
                    first_name=False,
                    last_name=False,
                    title=False,
                    category=False,
                    products_purchase=False,
                    products_inquiry=False,
                    occasion=False
                )}

            system_prompt = system_prompt_doc["content"]
            customer_message = state["customer_message"] if state["customer_message"] else CustomerMessage()
            
            extracted_info = {
                "first_name": self.safe_get(customer_message, "first_name", "none"),
                "last_name": self.safe_get(customer_message, "last_name", "none"),
                "title": self.safe_get(customer_message, "title", "none"),
                "category": self.safe_get(customer_message, "category", Category.UNKNOWN).value,
                "products_purchase": [item.dict() for item in self.safe_get(customer_message, "products_purchase", [])],
                "products_inquiry": [item.dict() for item in self.safe_get(customer_message, "products_inquiry", [])],
                "occasion": self.safe_get(customer_message, "occasion", "none")
            }
            
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{message}", body).replace("{extracted_info}", json.dumps(extracted_info))
            
            response = openai.chat.completions.create(
                model=os.getenv('OPEN_AI_CHAT_MODEL'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.0,
            )
            
            logger.info(f"OpenAI API response: {response.choices[0].message.content}")
            verification_data = json.loads(response.choices[0].message.content.strip())
            
            try:
                validated_data = VerificationResult(**verification_data)
                logger.info("Verification output successfully validated against VerificationResult")
                return {"verification_result": validated_data}
            except ValidationError as ve:
                logger.error(f"Validation error in verification output: {ve}")
                return {"verification_result": VerificationResult(
                    first_name=False,
                    last_name=False,
                    title=False,
                    category=False,
                    products_purchase=False,
                    products_inquiry=False,
                    occasion=False
                )}
        
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error verifying email extraction: {e}")
            return {"verification_result": VerificationResult(
                first_name=False,
                last_name=False,
                title=False,
                category=False,
                products_purchase=False,
                products_inquiry=False,
                occasion=False
            )}
        except Exception as e:
            logger.error(f"Unexpected error verifying email extraction: {e}")
            return {"verification_result": VerificationResult(
                first_name=False,
                last_name=False,
                title=False,
                category=False,
                products_purchase=False,
                products_inquiry=False,
                occasion=False
            )}

    def extract_category(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_category")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_category' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            if extracted_data and "category" in extracted_data:
                try:
                    updated_message = customer_message.model_copy(update={"category": Category(extracted_data["category"])})
                    logger.info("Category successfully extracted and validated")
                    return {"customer_message": updated_message}
                except (ValueError, ValidationError) as e:
                    logger.error(f"Invalid category value or validation error: {e}")
                    return {"customer_message": customer_message}
            else:
                logger.error("Invalid or missing category in OpenAI response")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Unexpected error in extract_category: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def extract_name_title(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_name_title")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_name_title' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            if extracted_data and all(key in extracted_data for key in ["first_name", "last_name", "title"]):
                try:
                    updated_message = customer_message.model_copy(update={
                        "first_name": extracted_data["first_name"],
                        "last_name": extracted_data["last_name"],
                        "title": extracted_data["title"]
                    })
                    logger.info("Name and title successfully extracted and validated")
                    return {"customer_message": updated_message}
                except ValidationError as e:
                    logger.error(f"Validation error in name/title extraction: {e}")
                    return {"customer_message": customer_message}
            else:
                logger.error("Invalid or missing name/title data in OpenAI response")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Unexpected error in extract_name_title: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}
        
    def extract_questions(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_questions")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_questions' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            questions = []
            if extracted_data:
                if isinstance(extracted_data, list) and all(isinstance(item, str) for item in extracted_data):
                    questions = extracted_data
                elif isinstance(extracted_data, dict) and "questions" in extracted_data and isinstance(extracted_data["questions"], list) and all(isinstance(item, str) for item in extracted_data["questions"]):
                    questions = extracted_data["questions"]
                else:
                    logger.error("Invalid or missing questions data in OpenAI response")
                    return {"customer_message": customer_message}
            
            try:
                updated_message = customer_message.model_copy(update={"questions": questions})
                logger.info("Questions successfully extracted and validated")
                return {"customer_message": updated_message}
            except ValidationError as e:
                logger.error(f"Validation error in questions extraction: {e}")
                return {"customer_message": customer_message}
                    
        except Exception as e:
            logger.error(f"Unexpected error in extract_questions: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def extract_reason(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_reason")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_reason' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            if extracted_data and "occasion" in extracted_data:
                try:
                    updated_message = customer_message.model_copy(update={"occasion": extracted_data["occasion"]})
                    logger.info("Occasion successfully extracted and validated")
                    return {"customer_message": updated_message}
                except ValidationError as e:
                    logger.error(f"Validation error in occasion extraction: {e}")
                    return {"customer_message": customer_message}
            else:
                logger.error("Invalid or missing occasion in OpenAI response")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Unexpected error in extract_reason: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def extract_orders(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_orders")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_orders' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            products = []
            if extracted_data:
                if isinstance(extracted_data, list):
                    product_list = extracted_data
                elif isinstance(extracted_data, dict):
                    product_list = None
                    for key, value in extracted_data.items():
                        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                            product_list = value
                            break
                    if not product_list:
                        logger.error("No valid product list found in OpenAI response dictionary")
                        return {"customer_message": customer_message}
                else:
                    logger.error("Invalid or missing products_purchase in OpenAI response")
                    return {"customer_message": customer_message}
                
                for item in product_list:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid product purchase item: {item}")
                        continue
                    item_with_defaults = {
                        "product_name": item.get("product_name", ""),
                        "product_description": item.get("product_description", ""),
                        "quantity": item.get("quantity", 0),
                        "product_id": item.get("product_id", ""),
                        "filled": item.get("filled", 0),
                        "unfilled": item.get("unfilled", 0),
                        "order_status": item.get("order_status", OrderStatus.NONE)
                    }
                    try:
                        products.append(Product(**item_with_defaults))
                    except ValidationError as e:
                        logger.error(f"Validation error for product {item}: {e}")
                        continue
            
            updated_message = customer_message.model_copy(update={"products_purchase": products})
            logger.info(f"products content: {[product.dict() for product in products]}")
            logger.info(f"products types: {[type(p) for p in products]}")
            logger.info("Products purchase successfully extracted")
            return {"customer_message": updated_message}
                    
        except Exception as e:
            logger.error(f"Unexpected error in extract_orders: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def extract_inquiries(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_inquiries")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_inquiries' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            products = []
            if extracted_data:
                if isinstance(extracted_data, list):
                    product_list = extracted_data
                elif isinstance(extracted_data, dict) and "products" in extracted_data and isinstance(extracted_data["products"], list):
                    product_list = extracted_data["products"]
                else:
                    logger.error("Invalid or missing products_inquiry in OpenAI response")
                    return {"customer_message": customer_message}
                
                for item in product_list:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid product inquiry item: {item}")
                        continue
                    item_with_defaults = {
                        "product_name": item.get("product_name", ""),
                        "product_description": item.get("product_description", ""),
                        "quantity": item.get("quantity", 0),
                        "product_id": item.get("product_id", ""),
                        "filled": item.get("filled", 0),
                        "unfilled": item.get("unfilled", 0),
                        "order_status": item.get("order_status", OrderStatus.NONE)
                    }
                    try:
                        products.append(Product(**item_with_defaults))
                    except ValidationError as e:
                        logger.error(f"Validation error for product {item}: {e}")
                        continue
            
            updated_message = customer_message.model_copy(update={"products_inquiry": products})
            
            for product in updated_message.products_inquiry:
                print(product)
            
            logger.info("Products inquiry successfully extracted")
            return {"customer_message": updated_message}
                    
        except Exception as e:
            logger.error(f"Unexpected error in extract_inquiries: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def extract_purchase_and_inquiry(self, state):
        try:
            system_prompt_doc = self.prompts.get("extract_system_info")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'extract_system_info' with role 'system' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            user_prompt_doc = self.prompts.get("extract_purchase_and_inquiry")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'extract_purchase_and_inquiry' with role 'user' not found")
                return {"customer_message": state.get("customer_message", CustomerMessage())}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"customer_message": customer_message}
            
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body)
            
            extracted_data = self._call_openai(system_prompt, user_prompt)
            purchase_products = []
            inquiry_products = []
            if extracted_data:
                if isinstance(extracted_data, dict) and all(key in extracted_data for key in ["products_purchase", "products_inquiry"]) and isinstance(extracted_data["products_purchase"], list) and isinstance(extracted_data["products_inquiry"], list):
                    purchase_list = extracted_data["products_purchase"]
                    inquiry_list = extracted_data["products_inquiry"]
                elif isinstance(extracted_data, list):
                    purchase_list = [item for item in extracted_data if item.get("intent") == "purchase"]
                    inquiry_list = [item for item in extracted_data if item.get("intent") == "inquiry"]
                else:
                    logger.error("Invalid or missing products_purchase/products_inquiry in OpenAI response")
                    return {"customer_message": customer_message}
                
                for item in purchase_list:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid product purchase item: {item}")
                        continue
                    item_with_defaults = {
                        "product_name": item.get("product_name", ""),
                        "product_description": item.get("product_description", ""),
                        "quantity": item.get("quantity", 0),
                        "product_id": item.get("product_id", ""),
                        "filled": item.get("filled", 0),
                        "unfilled": item.get("unfilled", 0),
                        "order_status": item.get("order_status", OrderStatus.NONE)
                    }
                    try:
                        purchase_products.append(Product(**item_with_defaults))
                    except ValidationError as e:
                        logger.error(f"Validation error for product purchase {item}: {e}")
                        continue
                
                for item in inquiry_list:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid product inquiry item: {item}")
                        continue
                    item_with_defaults = {
                        "product_name": item.get("product_name", ""),
                        "product_description": item.get("product_description", ""),
                        "quantity": item.get("quantity", 0),
                        "product_id": item.get("product_id", ""),
                        "filled": item.get("filled", 0),
                        "unfilled": item.get("unfilled", 0),
                        "order_status": item.get("order_status", OrderStatus.NONE)
                    }
                    try:
                        inquiry_products.append(Product(**item_with_defaults))
                    except ValidationError as e:
                        logger.error(f"Validation error for product inquiry {item}: {e}")
                        continue
            
            updated_message = customer_message.model_copy(update={
                "products_purchase": purchase_products,
                "products_inquiry": inquiry_products
            })
            logger.info("Products purchase and inquiry successfully extracted")
            return {"customer_message": updated_message}
                    
        except Exception as e:
            logger.error(f"Unexpected error in extract_purchase_and_inquiry: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}

    def _call_openai(self, system_prompt, user_prompt):
        try:
            response = openai.chat.completions.create(
                model=os.getenv('OPEN_AI_CHAT_MODEL'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None
        
    def call_bedrock(self, system_prompt, user_prompt):
        try:
            response = self.bedrock_api.call_bedrock(
                model_id='amazon.titan-text-express-v1',
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_token_count=128,
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None
        
    