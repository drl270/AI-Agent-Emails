import json
import logging
import os

import numpy as np
import openai
from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailProcessor:
    def __init__(self, api_key, prompts, uri, db):
        load_dotenv()
        openai.api_key = api_key
        self.embeddings = None
        self.vector_store = None
        self.db_handler = MongoDBHandler(uri, db)
        self.collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
        self.prompts = prompts

    def embed_email_content(self, content):
        try:
            response = openai.embeddings.create(
                input=content,
                model="text-embedding-ada-002",
            )
            embedding = response.data[0].embedding
            norm = np.linalg.norm(embedding)
            logger.debug(f"Email embedding norm: {norm}")
            return embedding
        except Exception as e:
            logger.error(f"Error embedding email content: {e}")
            return None

    def classify_email(self, subject, message):
        try:
            prompt_doc = self.prompts.get("classify_email")
            if not prompt_doc:
                logger.error("classify_email prompt not found")
                return "product inquiry"
            prompt = prompt_doc["content"].replace("{subject}", subject).replace("{message}", message)
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": prompt_doc.get("role", "user"), "content": prompt}],
                max_tokens=10,
                temperature=0.0,
            )
            classification = response.choices[0].message.content.strip().lower()
            return "order request" if "order" in classification else "product inquiry"
        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            return "product inquiry"