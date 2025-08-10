import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from email_processor import EmailProcessor
from models import EmailRequest
from mongodb_handler import MongoDBHandler
from order_processing import OrderProcessing
from product_catalog import ProductCatalogProcessor
from product_inquiry import ProductInquiry
from utils import load_prompts

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')
collection_products = os.getenv('MONGO_COLLECTION_PRODUCTS_NAME')
collection_prompts = os.getenv('MONGO_COLLECTION_PROMPTS_NAME')
db_handler = MongoDBHandler()

try:
    prompts = load_prompts(db_handler, collection_prompts)
except Exception as e:
    logger.error(f"Failed to load prompts: {e}")
    raise

try:
    documents = db_handler.find_documents(collection_products)
    if not documents:
        logger.error(f"No products found in MongoDB {collection_products} collection")
        raise ValueError(f"No products found in MongoDB {collection_products}")
except Exception as e:
    raise ValueError(f"Error loading product data from MongoDB {collection_products}") from e

product_processor = ProductCatalogProcessor(api_key)
product_processor.process_catalog()
processed_catalog_df = product_processor.get_product_catalog()
catalog_embeddings = processed_catalog_df["embedding"].tolist()
product_inquiry = ProductInquiry(
    processed_catalog_df, catalog_embeddings, api_key, prompts
)
order_processor = OrderProcessing(api_key, prompts, use_saved_product_embeddings=True)
email_processor = EmailProcessor(api_key, prompts)

@app.post("/process_email")
async def process_email(email: EmailRequest):
    try:
        category = email_processor.classify_email(email.subject, email.message)
        if category == "product inquiry":
            response = product_inquiry.generate_inquiry_response(email.message)
        elif category == "order request":
            order_details = order_processor.extract_order_details(email.message)
            formatted_summary = order_processor.process_order(order_details)
            response = order_processor.generate_order_response(
                formatted_summary, email.message, order_details
            )
        else:
            raise ValueError(f"Unknown email category: {category}")
        return {"email_id": email.email_id, "category": category, "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing email: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)