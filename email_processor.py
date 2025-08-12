import json
import logging
import os

import numpy as np
import openai
from dotenv import load_dotenv

from global_state import Category, State
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
            prompt_doc = self.prompts.get("classify_email")
            if not prompt_doc:
                logger.error("classify_email prompt not found")
                return "product inquiry"
            prompt = prompt_doc["content"].replace("{subject}", state.customer_message.subject).replace("{message}", state.customer_message.body)
            response = openai.chat.completions.create(
                model=os.getenv('OPEN_AI_CHAT_MODEL'),
                messages=[{"role": prompt_doc.get("role", "user"), "content": prompt}],
                max_tokens=10,
                temperature=0.0,
            )
            classification = response.choices[0].message.content.strip().lower()
            category = "order request" if "order" in classification else "product inquiry"
            state.customer_message.category = Category[category.upper().replace(" ", "_")]
            return category
        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            state.customer_message.category = Category.INQUIRY
            return "product inquiry"