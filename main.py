import asyncio
import logging
import os
import sys
import traceback
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.graph import END, StateGraph

from email_processor import EmailProcessor
from global_state import Category, CustomerMessage, State, VerificationResult
from inventory_manager import InventoryManager
from locate_products import LocateProductByDescription
from models import EmailRequest
from mongodb_handler import MongoDBHandler
from product_catalog import ProductCatalogProcessor
from product_similarity import ProductSimilarity
from response_generator import ResponseGenerator
from utils import load_prompts
from verification_processor import VerificationProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

logging.getLogger('email_processor').setLevel(logging.INFO)
logging.getLogger('verification_processor').setLevel(logging.INFO) 
logging.getLogger('response_generator').setLevel(logging.INFO)
logging.getLogger('inventory_manager').setLevel(logging.INFO)
logging.getLogger('locate_products').setLevel(logging.INFO)
logging.getLogger('product_similarity').setLevel(logging.INFO)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse('static/ai-customer-agent.html')

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
email_processor = EmailProcessor(api_key, prompts, db_handler)
verification_processor = VerificationProcessor(api_key, prompts, db_handler)
locate_products_processor = LocateProductByDescription(api_key, db_handler, processed_catalog_df, catalog_embeddings)
inventory_processor = InventoryManager(processed_catalog_df)
response_processor = ResponseGenerator(prompts, db_handler)
product_similarity = ProductSimilarity(
    processed_catalog_df, catalog_embeddings, api_key, prompts, db_handler
)

async def extract_category_node(state: State) -> dict:
    try:
        result = email_processor.extract_category(state)
        return result
    except Exception as e:
        logger.debug(f"extract_category_node error: {e}")
        return {"customer_message": state.get("customer_message", CustomerMessage())}

async def verify_category_node(state: State) -> dict:
    try:
        verification_result = verification_processor.verify_category(state)
        return verification_result
    except Exception as e:
        logger.error(f"Error in verify_category_node: {e}")
        return {"verification_result": None}

async def extract_additional_info_node(state: State) -> dict:
    try:
        customer_message = state.get("customer_message", CustomerMessage())
        category = customer_message.category.value.lower()
        
        methods_to_call = [
            email_processor.extract_name_title,
            email_processor.extract_reason,
            email_processor.extract_questions
        ]
        
        if category == "order":
            methods_to_call.append(email_processor.extract_orders)
        elif category == "inquiry":
            methods_to_call.append(email_processor.extract_inquiries)
        elif category == "order_inquiry":
            methods_to_call.append(email_processor.extract_purchase_and_inquiry)
        
        logger.info(f"Processing category '{category}' with methods: {[method.__name__ for method in methods_to_call]}")
        
        results = []
        for method in methods_to_call:
            try:
                logger.info(f"Calling {method.__name__}")
                result = method(state)
                results.append(result)
                logger.info(f"{method.__name__} completed successfully")
            except Exception as e:
                logger.error(f"{method.__name__} failed: {e}")
                continue
        
        merged_updates = {}
        for result in results:
            if not isinstance(result, dict) or "customer_message" not in result:
                continue
                
            cm = result["customer_message"]
            
            if hasattr(cm, "products_purchase") and cm.products_purchase:
                merged_updates["products_purchase"] = cm.products_purchase
                logger.info(f"Updated products_purchase with {len(cm.products_purchase)} items")
            
            if hasattr(cm, "products_inquiry") and cm.products_inquiry:
                merged_updates["products_inquiry"] = cm.products_inquiry
                logger.info(f"Updated products_inquiry with {len(cm.products_inquiry)} items")
            
            if hasattr(cm, "questions") and cm.questions:
                merged_updates["questions"] = cm.questions
                logger.info(f"Updated questions with {len(cm.questions)} items")
            
            if hasattr(cm, "first_name") and cm.first_name and cm.first_name.lower() != 'none':
                merged_updates.update({
                    "first_name": cm.first_name,
                    "last_name": getattr(cm, "last_name", ""),
                    "title": getattr(cm, "title", "")
                })
                logger.info(f"Updated name/title: {cm.first_name} {getattr(cm, 'last_name', '')}")
            
            if hasattr(cm, "occasion") and cm.occasion and cm.occasion.strip():
                merged_updates["occasion"] = cm.occasion.strip()
                logger.info(f"Updated occasion: {cm.occasion}")
        
        if merged_updates:
            logger.info(f"Applying updates: {list(merged_updates.keys())}")
            updated_message = customer_message.model_copy(update=merged_updates)
        else:
            logger.info("No updates to apply")
            updated_message = customer_message
        
        logger.info("Additional info extraction completed successfully")
        return {"customer_message": updated_message}
    
    except Exception as e:
        logger.error(f"Error in extract_additional_info_node: {e}")
        return {"customer_message": state.get("customer_message", CustomerMessage())}

async def verify_remaining_extracted_data_node(state: State) -> dict:
    try:
        result = verification_processor.verify_remaining_extracted_data(state)
        return result  
    except Exception as e:
        logger.error(f"Error in verify_remaining_extracted_data_node: {e}")
        return {"verification_result": None}
    
async def locate_product_id_node(state: State) -> dict:
    try:
        result = locate_products_processor.locate_product_ids(state)
        return result  
    except Exception as e:
        logger.error(f"Error in locate_product_id_node: {e}")
        return {"customer_message": state.get("customer_message", CustomerMessage())}
    
async def check_inventory_node(state: State) -> dict:
    try:
        result = inventory_processor.check_inventory(state)
        return result  
    except Exception as e:
        logger.error(f"Error in check_inventory_node: {e}")
        return {"customer_message": state.get("customer_message", CustomerMessage())}
        
async def similar_products_node(state: State) -> dict:
    try:
        result = product_similarity.generate_similar_products(state)
        logger.debug(f"similar_products_node type: {type(result)}")
        return result
    except Exception as e:
        logger.error(f"Error in similar_products_node: {e}")
        return {"customer_message": state.get("customer_message", CustomerMessage())}
        
async def generate_response_node(state: State) -> dict:
    try:
        customer_message = state.get("customer_message", CustomerMessage())
        category = customer_message.category.value.lower()
        
        if category == "order":
            result = response_processor.generate_order(state)
        elif category == "order_inquiry":
            result = response_processor.generate_order_inquiry(state)
        elif category == "inquiry":
            result = response_processor.generate_inquiry(state)
        elif category == "status":
            result = response_processor.generate_status(state)
        elif category == "complaint":
            result = response_processor.generate_complaint(state)
        else:
            result = response_processor.generate_unknown(state)
        
        updated_message = result["customer_message"]
        logger.debug(f"Response: {updated_message.response}")
        
        return {"customer_message": updated_message}
        
    except Exception as e:
        logger.error(f"Error in generate_response_node: {e}")
        
        customer_message = state.get("customer_message", CustomerMessage())
        error_message = "Sorry, I encountered an error processing your request."
        
        updated_message = customer_message.model_copy(update={
            "response": error_message,
            "history": customer_message.history + [error_message]
        })
        
        return {"customer_message": updated_message}
        
workflow = StateGraph(State)
workflow.add_node("extract_category", extract_category_node)
workflow.add_node("verify_category", verify_category_node)
workflow.add_node("extract_additional_info", extract_additional_info_node)
workflow.add_node("verify_remaining_extracted_data", verify_remaining_extracted_data_node)
workflow.add_node("locate_product_id", locate_product_id_node)
workflow.add_node("check_inventory", check_inventory_node)
workflow.add_node("similar_products", similar_products_node)
workflow.add_node("generate_response", generate_response_node)
workflow.set_entry_point("extract_category")
   
def route_after_verify_category(state: State):
    passed = state["verification_result"].category if state["verification_result"] is not None else False
    
    if passed:
        return "extract_additional_info"
    else:
        return "generate_response"
    
def route_after_verify_extracted_data(state: State):
    category = state["customer_message"].category.value.lower()
    logger.debug(f"Routing category: {category}")
    if category in ["order", "inquiry", "order_inquiry"]:
        return "locate_product_id"  
    elif category in ["complaint", "status", "unknown"]:
        return "generate_response"
    else:
        logger.warning(f"Unknown email category: {category}")
        return END
    
workflow.add_edge("extract_category", "verify_category")
workflow.add_conditional_edges("verify_category", route_after_verify_category,
    {
        "extract_additional_info": "extract_additional_info",
        "generate_response": "generate_response"
    }
)

workflow.add_edge("extract_additional_info", "verify_remaining_extracted_data")
workflow.add_conditional_edges( "verify_remaining_extracted_data", route_after_verify_extracted_data,
    {
        "locate_product_id": "locate_product_id",
        "generate_response": "generate_response",
        END: END
    }
)
workflow.add_edge("locate_product_id", "check_inventory")
workflow.add_edge("check_inventory", "similar_products")
workflow.add_edge("similar_products", "generate_response")
workflow.add_edge("generate_response", END)

graph = workflow.compile()

@app.post("/process_email")
async def process_email(email: EmailRequest):
    logger.debug(f"Received request: email_id={email.email_id}, subject={email.subject}, message={email.message}")
    try:
        state: State = {
            "customer_message": CustomerMessage(
                id=email.email_id,
                subject=email.subject,
                body=email.message
            ),
            "verification_result": None
        }
        logger.debug("State initialized and populated")

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        logger.debug(f"Config: {config}")
        final_state = await graph.ainvoke(state, config)
        logger.debug(f"Final state: {final_state['customer_message']}")
        
        resp =  {"response": final_state["customer_message"].response}
        print(f"  response {resp}  ")
        logger.debug(f"Response: {final_state["customer_message"].products_purchase}")
        
        print(f"PRODUCTS_PURCHASE: {final_state['customer_message'].products_purchase}")
        print(f"PRODUCTS_INQUIRY: {final_state['customer_message'].products_inquiry}")
        print(f"PRODUCTS_ISUGGESTIONS: {final_state['customer_message'].products_recommendations}")
        
        return {
            "email_id": final_state["customer_message"].id,
            "category": final_state["customer_message"].category.value,
            "response": final_state["customer_message"].response,
            "first_name": final_state["customer_message"].first_name,
            "last_name": final_state["customer_message"].last_name,
            "title": final_state["customer_message"].title,
            "history": final_state["customer_message"].history,
            "products_purchase": final_state["customer_message"].products_purchase,
            "products_inquiry": final_state["customer_message"].products_inquiry,
            "products_recommendations": final_state["customer_message"].products_recommendations,
            "verification_result": final_state["verification_result"] if final_state["verification_result"] else None
            
        }
    except ValueError as ve:
        logger.error(f"ValueError in process_email: {str(ve)}")
        raise HTTPException(status_code=400, detail=f"Unknown email category: {str(ve)}")
    except Exception as e:
        logger.error(f"Error in process_email: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing email: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)