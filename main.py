import logging
import os
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.graph import END, StateGraph

from email_processor import EmailProcessor
from global_state import Category, State
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
uri = os.getenv("MONGODB_URI")
db = os.getenv('MONGO_DB_NAME')
db_handler = MongoDBHandler(uri, db)

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

product_processor = ProductCatalogProcessor(api_key, db_handler)
product_processor.process_catalog()
processed_catalog_df = product_processor.get_product_catalog()
catalog_embeddings = processed_catalog_df["embedding"].tolist()
product_inquiry = ProductInquiry(
    processed_catalog_df, catalog_embeddings, api_key, prompts, db_handler
)
order_processor = OrderProcessing(api_key, prompts, db_handler, use_saved_product_embeddings=True)
email_processor = EmailProcessor(api_key, prompts, db_handler)

def classify_email_node(state: State) -> dict:
    category = email_processor.classify_email(state)
    state.customer_message.category = Category[category.upper()]
    return {}

def verify_email_node(state: State) -> dict:
    try:
        email_processor.verify_email_extraction(state)
        logger.debug(f"Verification result: {state.verification_result.dict()}")
    except Exception as e:
        logger.error(f"Error in verify_email_node: {e}")
    return {}

def product_inquiry_node(state: State) -> dict:
    response = product_inquiry.generate_inquiry_response(state)
    products_of_interest = state.customer_message.products_inquiry
    state.customer_message.response = response
    state.customer_message.history.append(response)
    return {}

def extract_order_details_node(state: State) -> dict:
    order_details = order_processor.extract_order_details(state)
    state.customer_message.order_details = order_details
    return {}

def process_order_node(state: State) -> dict:
    formatted_summary = order_processor.process_order(state)
    state.customer_message.formatted_summary = formatted_summary
    return {}

def generate_order_response_node(state: State) -> dict:
    response = order_processor.generate_order_response(state)
    state.customer_message.response = response
    state.customer_message.history.append(response)
    return {}

workflow = StateGraph(State)
workflow.add_node("classify_email", classify_email_node)
workflow.add_node("verify_email", verify_email_node)
workflow.add_node("product_inquiry", product_inquiry_node)
workflow.add_node("extract_order_details", extract_order_details_node)
workflow.add_node("process_order", process_order_node)
workflow.add_node("generate_order_response", generate_order_response_node)
workflow.set_entry_point("classify_email")

def route_after_verify(state: State):
    category = state.customer_message.category.value
    if category == "inquiry":
        return "product_inquiry"
    elif category == "order":
        return "extract_order_details"
    else:
        logger.warning(f"Unknown email category: {category}")
        return END

workflow.add_edge("classify_email", "verify_email")
workflow.add_conditional_edges(
    "verify_email",
    route_after_verify,
    {
        "product_inquiry": "product_inquiry",
        "extract_order_details": "extract_order_details",
        END: END
    }
)
workflow.add_edge("extract_order_details", "process_order")
workflow.add_edge("process_order", "generate_order_response")
workflow.add_edge("product_inquiry", END)
workflow.add_edge("generate_order_response", END)

graph = workflow.compile()

@app.post("/process_email")
async def process_email(email: EmailRequest):
    try:
        state = State()
        state.customer_message.id = email.email_id
        state.customer_message.subject = email.subject
        state.customer_message.body = email.message

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        final_state = await graph.ainvoke(state, config)
        return {
            "email_id": final_state.customer_message.id,
            "category": final_state.customer_message.category.value,
            "response": final_state.customer_message.response,
            "verification_result": final_state.verification_result.dict()
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Unknown email category: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing email: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)