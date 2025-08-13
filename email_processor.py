import json
import logging
import os

import numpy as np
import openai
from dotenv import load_dotenv
from pydantic import ValidationError

from bedrock_api import BedrockAPI
from global_state import Category, State, VerificationResult
from mongodb_handler import MongoDBHandler

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

    def classify_email(self, state: State) -> str:
        try:
            system_prompt_doc = self.prompts.get("extract_system")
            user_prompt_doc = self.prompts.get("extract_info")
            if not system_prompt_doc or not user_prompt_doc:
                logger.error("extract_system or extract_info prompt not found")
                state.customer_message.category = Category.INQUIRY
                return "inquiry"

            system_prompt = system_prompt_doc["content"]
            user_prompt = user_prompt_doc["content"].replace("{subject}", state.customer_message.subject).replace("{message}", state.customer_message.body)
            response = openai.chat.completions.create(
                model=os.getenv('OPEN_AI_CHAT_MODEL'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.0,
            )
            extracted_data = json.loads(response.choices[0].message.content.strip())
            
            state.customer_message.first_name = extracted_data.get("first_name", "none")
            state.customer_message.last_name = extracted_data.get("last_name", "none")
            state.customer_message.title = extracted_data.get("title", "none")
            state.customer_message.category = Category[extracted_data.get("category", "unknown").upper()]
            state.customer_message.products_purchase = [json.dumps(item) for item in extracted_data.get("products_purchase", [])]
            state.customer_message.products_inquiry = [json.dumps(item) for item in extracted_data.get("products_inquiry", [])]
            state.customer_message.occasion = extracted_data.get("occasion", "none")
            
            category = extracted_data.get("category", "inquiry")
            return category
        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            state.customer_message.category = Category.INQUIRY
            return "inquiry"

    def verify_email_extraction(self, state: State) -> None:
        try:
            system_prompt_doc = self.prompts.get("extract_system")
            user_prompt_doc = self.prompts.get("extract_info_verification")
            if not system_prompt_doc or not user_prompt_doc:
                logger.error("extract_system or extract_info_verification prompt not found")
                raise ValueError("Missing required prompts")

            system_prompt = system_prompt_doc["content"]
            extracted_info = {
                "first_name": state.customer_message.first_name,
                "last_name": state.customer_message.last_name,
                "title": state.customer_message.title,
                "category": state.customer_message.category.value,
                "products_purchase": [json.loads(item) for item in state.customer_message.products_purchase],
                "products_inquiry": [json.loads(item) for item in state.customer_message.products_inquiry],
                "occasion": state.customer_message.occasion
            }
            user_prompt = user_prompt_doc["content"].replace("{subject}", state.customer_message.subject).replace("{message}", state.customer_message.body).replace("{extracted_info}", json.dumps(extracted_info))
            response = self.bedrock_api.call_bedrock(
                prompt=f"{system_prompt}\n{user_prompt}",
                model_id='amazon.titan-text-express-v1',
                max_token_count=128,
                temperature=0.0
            )
            verification_data = json.loads(response.strip())
            
            # Validate against VerificationResult
            try:
                validated_data = VerificationResult(**verification_data)
                state.verification_result = validated_data
                logger.info("Verification output successfully validated against VerificationResult")
            except ValidationError as ve:
                logger.error(f"Validation error in verification output: {ve}")
                raise ValueError(f"Verification output does not conform to VerificationResult: {ve}")
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error verifying email extraction: {e}")
            state.verification_result = VerificationResult(
                first_name=False,
                last_name=False,
                title=False,
                category=False,
                products_purchase=False,
                products_inquiry=False,
                occasion=False
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying email extraction: {e}")
            state.verification_result = VerificationResult(
                first_name=False,
                last_name=False,
                title=False,
                category=False,
                products_purchase=False,
                products_inquiry=False,
                occasion=False
            )