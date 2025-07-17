import json
import logging
import os
import pickle

import faiss
import numpy as np
import openai
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Load prompts from JSON file
def load_prompts(file_path="prompts.json"):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Prompts file {file_path} not found")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in {file_path}")
        raise


PROMPTS = load_prompts()

# FastAPI app and request model
app = FastAPI()

# Add CORS middleware for front-end access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmailRequest(BaseModel):
    email_id: str
    subject: str
    message: str


class ProductCatalogProcessor:
    def __init__(self, product_catalog_df, api_key):
        self.product_catalog_df = product_catalog_df
        openai.api_key = api_key
        self.embeddings = None

    def embed_product_description(self, description):
        try:
            response = openai.embeddings.create(
                input=description, model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error embedding product description: {e}")
            return None

    def process_catalog(self, use_saved_product_embeddings: bool = True):
        embeddings_file = "product_embeddings.pkl"
        if use_saved_product_embeddings and os.path.exists(embeddings_file):
            try:
                with open(embeddings_file, "rb") as f:
                    self.embeddings = pickle.load(f)
                logger.info(
                    f"Loaded {len(self.embeddings)} embeddings from {embeddings_file}"
                )
                if len(self.embeddings) != len(self.product_catalog_df):
                    logger.warning(
                        f"Embedding count ({len(self.embeddings)}) does not match product count ({len(self.product_catalog_df)}). Regenerating embeddings."
                    )
                    self._generate_and_save_embeddings(embeddings_file)
                else:
                    self.product_catalog_df["embedding"] = self.embeddings
            except Exception as e:
                logger.error(
                    f"Error loading embeddings from {embeddings_file}: {e}. Regenerating embeddings."
                )
                self._generate_and_save_embeddings(embeddings_file)
        else:
            logger.info(
                f"No saved embeddings found or use_saved_product_embeddings=False. Generating embeddings."
            )
            self._generate_and_save_embeddings(embeddings_file)

        norms = [np.linalg.norm(emb) for emb in self.embeddings if emb is not None]
        if not norms:
            raise ValueError("No valid embeddings generated or loaded")
        logger.info(
            f"Embedding norms: min={min(norms)}, max={max(norms)}, mean={np.mean(norms)}"
        )

    def _generate_and_save_embeddings(self, embeddings_file):
        self.embeddings = (
            self.product_catalog_df["description"]
            .apply(self.embed_product_description)
            .tolist()
        )
        self.product_catalog_df["embedding"] = self.embeddings
        try:
            with open(embeddings_file, "wb") as f:
                pickle.dump(self.embeddings, f)
            logger.info(f"Saved {len(self.embeddings)} embeddings to {embeddings_file}")
        except Exception as e:
            logger.error(f"Error saving embeddings to {embeddings_file}: {e}")

    def get_product_catalog(self):
        return self.product_catalog_df


class VectorStore:
    def __init__(self, dimension):
        self.index = faiss.IndexFlatL2(dimension)

    def add_embeddings(self, embeddings):
        embeddings = np.array(embeddings).astype("float32")
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.where(norms == 0, 1, norms)
        logger.debug(
            f"Normalized embedding norms: {[np.linalg.norm(emb) for emb in embeddings]}"
        )
        self.index.add(embeddings)

    def search(self, query_embedding, k=5):
        query_embedding = np.array(query_embedding).astype("float32")
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm
        logger.debug(
            f"Normalized query embedding norm: {np.linalg.norm(query_embedding)}"
        )
        query_embedding = query_embedding.reshape(1, -1)
        distances, indices = self.index.search(query_embedding, k)
        return distances, indices


class ProductInquiry:
    def __init__(
        self, product_catalog_df, catalog_vector_store, catalog_embeddings, api_key
    ):
        self.product_catalog_df = product_catalog_df
        self.catalog_vector_store = catalog_vector_store
        self.catalog_embeddings = catalog_embeddings
        openai.api_key = api_key

    def embed_product_description(self, description):
        try:
            response = openai.embeddings.create(
                input=description, model="text-embedding-ada-002"
            )
            embedding = response.data[0].embedding
            norm = np.linalg.norm(embedding)
            logger.debug(f"Query embedding norm: {norm}")
            return embedding
        except Exception as e:
            logger.error(f"Error embedding product description: {e}")
            return None

    def extract_inquiry_details(self, email_content):
        prompt = PROMPTS.get("inquiry_extract", "").format(email_content=email_content)
        if not prompt:
            logger.error("inquiry_extract prompt not found in prompts.json")
            return "Customer Name: Customer\nProduct of Interest: Product\nRelevant Questions: General inquiry"
        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            details = response.choices[0].message.content
            return details
        except Exception as e:
            logger.error(f"Error extracting inquiry details: {e}")
            return "Customer Name: Customer\nProduct of Interest: Product\nRelevant Questions: General inquiry"

    def find_closest_products(
        self, product_embedding, k=5, filter_features=None, distance_threshold=None
    ):
        distances, indices = self.catalog_vector_store.search(
            np.array([product_embedding]).astype("float32"), k
        )
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
        available_products = closest_products[closest_products["stock"] > 0]
        if available_products.empty:
            logger.warning("No available products found after filtering")
        return available_products

    def generate_inquiry_response(self, email_content, k=5):
        prompt_extract = PROMPTS.get("inquiry_extract", "").format(
            email_content=email_content
        )
        if not prompt_extract:
            logger.error("inquiry_extract prompt not found in prompts.json")
            return "We encountered an issue while processing your inquiry. Please contact us again."
        try:
            response_extract = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt_extract}],
                max_tokens=1000,
                temperature=0.0,
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
        response_prompt = PROMPTS.get("inquiry_response", "").format(
            customer_name=customer_name,
            products_of_interest=", ".join(products_of_interest),
            questions=questions,
            closest_products_str=closest_products_str,
        )
        if not response_prompt:
            logger.error("inquiry_response prompt not found in prompts.json")
            return "We encountered an issue while generating the response. Please contact us again."

        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": response_prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            final_response = response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating inquiry response: {e}")
            return "We encountered an issue while generating the response. Please contact us again."

        return final_response


class EmailProcessor:
    def __init__(self, api_key):
        openai.api_key = api_key
        self.embeddings = None
        self.vector_store = None

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
        prompt = PROMPTS.get("classify_email", "").format(
            subject=subject, message=message
        )
        if not prompt:
            logger.error("classify_email prompt not found in prompts.json")
            return "product inquiry"
        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.0,
            )
            classification = response.choices[0].message.content.strip().lower()
            return "order request" if "order" in classification else "product inquiry"
        except Exception as e:
            logger.error(f"Error classifying email  #1: {e}")
            return "product inquiry"


class OrderProcessing:
    def __init__(
        self, product_catalog_df, api_key, use_saved_product_embeddings: bool = True
    ):
        self.product_catalog_df = product_catalog_df
        openai.api_key = api_key
        self.product_descriptions = (
            self.product_catalog_df.set_index("product_id")[["name", "description"]]
            .apply(lambda x: f"{x['name']} {x['description']}".lower(), axis=1)
            .to_dict()
        )
        embeddings_file = "product_embeddings.pkl"
        if use_saved_product_embeddings and os.path.exists(embeddings_file):
            try:
                with open(embeddings_file, "rb") as f:
                    self.product_embeddings = pickle.load(f)
                logger.info(
                    f"Loaded {len(self.product_embeddings)} embeddings from {embeddings_file} for OrderProcessing"
                )
                if len(self.product_embeddings) != len(self.product_descriptions):
                    logger.warning(
                        f"Embedding count ({len(self.product_embeddings)}) does not match product description count ({len(self.product_descriptions)}). Regenerating embeddings."
                    )
                    self._generate_and_save_embeddings(embeddings_file)
                else:
                    self.product_embeddings = np.array(self.product_embeddings)
            except Exception as e:
                logger.error(
                    f"Error loading embeddings from {embeddings_file}: {e}. Regenerating embeddings."
                )
                self._generate_and_save_embeddings(embeddings_file)
        else:
            logger.info(
                f"No saved embeddings found or use_saved_product_embeddings=False. Generating embeddings for OrderProcessing."
            )
            self._generate_and_save_embeddings(embeddings_file)

        norms = [
            np.linalg.norm(emb) for emb in self.product_embeddings if emb is not None
        ]
        if not norms:
            raise ValueError(
                "No valid embeddings generated or loaded for OrderProcessing"
            )
        logger.info(
            f"Order processing embedding norms: min={min(norms)}, max={max(norms)}, mean={np.mean(norms)}"
        )

    def _generate_and_save_embeddings(self, embeddings_file):
        self.product_embeddings = [
            self.embed_product_description(desc)
            for desc in self.product_descriptions.values()
        ]
        self.product_embeddings = np.array(self.product_embeddings)
        try:
            with open(embeddings_file, "wb") as f:
                pickle.dump(self.product_embeddings.tolist(), f)
            logger.info(
                f"Saved {len(self.product_embeddings)} embeddings to {embeddings_file} for OrderProcessing"
            )
        except Exception as e:
            logger.error(f"Error saving embeddings to {embeddings_file}: {e}")

    def embed_product_description(self, description):
        try:
            response = openai.embeddings.create(
                input=description, model="text-embedding-ada-002"
            )
            embedding = response.data[0].embedding
            norm = np.linalg.norm(embedding)
            logger.debug(f"Order query embedding norm: {norm}")
            return embedding
        except Exception as e:
            logger.error(f"Error embedding description: {e}")
            return None

    def extract_order_details(self, email_content):
        prompt = PROMPTS.get("order_extract", "").format(email_content=email_content)
        if not prompt:
            logger.error("order_extract prompt not found in prompts.json")
            return []
        try:
            response = openai.chat.completions.create(
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
                if len(product_id) != 7 or not self.vector_store_has_product(
                    product_id
                ):
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

    def find_product_id_by_description(self, description):
        normalized_description = description.strip().lower()
        try:
            description_embedding = self.embed_product_description(
                normalized_description
            )
            similarities = cosine_similarity(
                [description_embedding], self.product_embeddings
            )[0]
            best_match_idx = np.argmax(similarities)
            best_product_id = list(self.product_descriptions.keys())[best_match_idx]
            return best_product_id
        except Exception as e:
            logger.error(f"Error finding product ID: {e}")
            return None

    def vector_store_has_product(self, product_id):
        return product_id in self.product_catalog_df["product_id"].values

    def check_stock_level(self, product_id):
        product = self.product_catalog_df[
            self.product_catalog_df["product_id"] == product_id
        ]
        if not product.empty:
            return product.iloc[0]["stock"]
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
            new_stock_level = stock_available - quantity_filled
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

    def generate_order_response(self, summary_string, email_content):
        prompt_extract = PROMPTS.get("order_extract_mentions", "").format(
            email_content=email_content
        )
        if not prompt_extract:
            logger.error("order_extract_mentions prompt not found in prompts.json")
            extracted_products = []
        else:
            try:
                response_extract = openai.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt_extract}],
                    max_tokens=1000,
                    temperature=0.0,
                )
                extracted_products = json.loads(
                    response_extract.choices[0].message.content
                )
            except Exception as e:
                logger.error(f"Error extracting product mentions: {e}")
                extracted_products = []

        similar_items = []
        for product in extracted_products:
            product_desc = product.get("Product description", "")
            product_embedding = self.embed_product_description(product_desc)
            if product_embedding is not None:
                similarities = cosine_similarity(
                    [product_embedding], self.product_embeddings
                )[0]
                best_match_idx = np.argmax(similarities)
                best_product_id = list(self.product_descriptions.keys())[best_match_idx]
                similar_items.append(best_product_id)

        response_prompt = PROMPTS.get("order_response", "").format(
            summary_string=summary_string,
            email_content=email_content,
            similar_items=", ".join(similar_items),
        )
        if not response_prompt:
            logger.error("order_response prompt not found in prompts.json")
            return "An error occurred while generating the response."

        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": response_prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            final_response = response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating order response: {e}")
            final_response = "An error occurred while generating the response."

        return final_response


# Initialize global resources
api_key = "sk-dEf7P9bZoV5K3CTNZ7UgiRYErojgPVir_82zLAkou7T3BlbkFJuwU6wlhlR_KRwBoUFYxxuN1hDagKG_rG5D-QhdVP8A"
products_csv = "products.csv"

try:
    product_catalog_df = pd.read_csv(products_csv)
except FileNotFoundError:
    logger.error(f"Product data file {products_csv} not found")
    raise ValueError(f"Product data file {products_csv} not found")
except Exception as e:
    logger.error(f"Error reading {products_csv}: {e}")
    raise ValueError(f"Error reading product data file") from e

product_processor = ProductCatalogProcessor(product_catalog_df, api_key)
product_processor.process_catalog(use_saved_product_embeddings=True)
processed_catalog_df = product_processor.get_product_catalog()
catalog_embeddings = processed_catalog_df["embedding"].tolist()
dimension = len(catalog_embeddings[0])
catalog_vector_store = VectorStore(dimension)
catalog_vector_store.add_embeddings(catalog_embeddings)
product_inquiry = ProductInquiry(
    product_catalog_df, catalog_vector_store, catalog_embeddings, api_key
)
order_processor = OrderProcessing(
    product_catalog_df, api_key, use_saved_product_embeddings=True
)
email_processor = EmailProcessor(api_key)


@app.post("/process_email")
async def process_email(email: EmailRequest):
    try:
        # Classify email
        category = email_processor.classify_email(email.subject, email.message)

        # Process based on category
        if category == "product inquiry":
            response = product_inquiry.generate_inquiry_response(email.message)
        elif category == "order request":
            order_details = order_processor.extract_order_details(email.message)
            formatted_summary = order_processor.process_order(order_details)
            response = order_processor.generate_order_response(
                formatted_summary, email.message
            )
        else:
            raise ValueError(f"Unknown email category: {category}")

        return {"email_id": email.email_id, "category": category, "response": response}
    except Exception as e:
        logger.error(f"Error processing email {email.email_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing email: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
