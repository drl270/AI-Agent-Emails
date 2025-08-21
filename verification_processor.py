import json
import logging
import os

import openai

from global_state import Category, CustomerMessage, State, VerificationResult

logger = logging.getLogger(__name__)

class VerificationProcessor:
    def __init__(self, api_key, prompts, db_handler=None):
        self.api_key = api_key
        self.prompts = prompts
        self.db_handler = db_handler

    def safe_get(self, obj, key, default=None):
        """Safely get value from either Pydantic model or dictionary"""
        if hasattr(obj, key):
            return getattr(obj, key)
        elif isinstance(obj, dict):
            return obj.get(key, default)
        return default

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

    def verify_category(self, state: State) -> dict:
        try:
            system_prompt_doc = self.prompts.get("verify_customer_message_system")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'verify_customer_message_system' with role 'system' not found")
                return {"verification_result": VerificationResult(category=False)}

            user_prompt_doc = self.prompts.get("verify_category")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'verify_category' with role 'user' not found")
                return {"verification_result": VerificationResult(category=False)}

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return {"verification_result": VerificationResult(category=False)}
            
            extracted_info = {"category": customer_message.category.value}
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body).replace("{extracted_info}", json.dumps(extracted_info))
            
            verification_data = self._call_openai(system_prompt, user_prompt)
            if verification_data and isinstance(verification_data, dict) and "category" in verification_data:
                logger.info("Category verification successful")
                return {"verification_result": VerificationResult(category=verification_data["category"])}
            else:
                logger.error("Invalid or missing category verification data in OpenAI response")
                return {"verification_result": VerificationResult(category=False)}
                
        except Exception as e:
            logger.error(f"Unexpected error in verify_category: {e}")
            return {"verification_result": VerificationResult(category=False)}

    def verify_remaining_extracted_data(self, state: State) -> dict:
        try:
            system_prompt_doc = self.prompts.get("verify_customer_message_system")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'verify_customer_message_system' with role 'system' not found")
                return self._get_default_verification_result()

            user_prompt_doc = self.prompts.get("verify_remaining_extracted_data")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'verify_remaining_extracted_data' with role 'user' not found")
                return self._get_default_verification_result()

            system_prompt = system_prompt_doc["content"]
            customer_message = state.get("customer_message", CustomerMessage())
            subject = self.safe_get(customer_message, "subject", "")
            body = self.safe_get(customer_message, "body", "")
            
            if body == "":
                return self._get_default_verification_result()
            
            # Convert Pydantic models to JSON-serializable dictionaries
            extracted_info = {
                "first_name": customer_message.first_name,
                "last_name": customer_message.last_name,
                "title": customer_message.title,
                "occasion": customer_message.occasion,
                "products_purchase": [item.model_dump() for item in customer_message.products_purchase],  # Use model_dump() instead of dict()
                "products_inquiry": [item.model_dump() for item in customer_message.products_inquiry]     # Use model_dump() instead of dict()
            }
            
            # Use json.dumps with default parameter to handle any remaining serialization issues
            user_prompt = user_prompt_doc["content"].replace("{subject}", subject).replace("{email}", body).replace("{extracted_info}", json.dumps(extracted_info, default=str))
            
            verification_data = self._call_openai(system_prompt, user_prompt)
            if verification_data and isinstance(verification_data, dict) and all(key in verification_data for key in ["first_name", "last_name", "title", "occasion", "products_purchase", "products_inquiry"]):
                logger.info("Remaining extracted data verification successful")
                return {"verification_result": verification_data}
            else:
                logger.error("Invalid or missing verification data in OpenAI response")
                return self._get_default_verification_result()
                
        except Exception as e:
            logger.error(f"Unexpected error in verify_remaining_extracted_data: {e}")
            return self._get_default_verification_result()
            
    def _get_default_verification_result(self):
        """Helper method to return default verification result"""
        return {"verification_result": {
            "first_name": False,
            "last_name": False,
            "title": False,
            "occasion": False,
            "products_purchase": False,
            "products_inquiry": False
        }}