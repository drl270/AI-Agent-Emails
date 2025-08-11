import json
import logging

from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_prompts():
    return [
        {
            "prompt_name": "inquiry_extract",
            "project": "customer_agent",
            "type": "production",
            "role": "user",
            "content": json.dumps({
                "role": "Customer support assistant",
                "task_1": "Read the following email and extract important details {email_content}",
                "task_2": "Extract customer name (if provided)",
                "task_3": "Extract product(s) of interest including name(s), product ID, and product descriptions. This should be a list.",
                "task_4": "Extract any relevant questions or specific details (e.g., product features, intended use, etc.). This should be a list.",
                "example_output": "JSON object with keys: \"customer_name\", \"products_of_interest\", \"questions\"",
                "restrictions": ""
            }, indent=2)
        },
        {
            "prompt_name": "inquiry_response",
            "project": "customer_agent",
            "type": "production",
            "role": "user",
            "content": json.dumps({
                "role": "Helpful and professional assistant working for a fashion store",
                "task_1": "Generate a friendly, professional response based on customer inquiry {email_content} and relevant products {products_of_interest}",
                "task_2": "Address the customer by name (if provided) {customer_name} and answer their questions: {questions}",
                "task_3": "Suggest relevant products from the store catalog: {closest_products_str} provide product names, IDs, and descriptions",
                "task_4": "Conclude with a friendly salutation from Customer Support",
                "example_output": "",
                "restrictions": "If no name is mentioned, use 'Dear Customer. Do not include placeholders like [Your Name], [Your Position]"
            }, indent=2)
        },
        {
            "prompt_name": "classify_email",
            "project": "customer_agent",
            "type": "production",
            "role": "user",
            "content": json.dumps({
                "role": "classifier",
                "task_1": "Determine whether an email is an 'order request' or a 'product inquiry' based on {subject} and {message}",
                "task_2": "Classify as 'product inquiry' if subject contains words like 'inquiry', 'shopping', 'looking for', or 'want to know', unless explicit order instructions exist",
                "task_3": "Classify as 'order request' if email explicitly places an order with quantity, product, and intent to buy",
                "task_4": "Use email subject for context (e.g., 'buy', 'purchase', 'order' suggest 'order request')",
                "task_5": "Require quantity, product, and explicit intent for 'order request'",
                "example_output": "",
                "restrictions": "If in doubt, classify as 'product inquiry'."
            }, indent=2)
        },
        {
            "prompt_name": "order_extract",
            "project": "customer_agent",
            "type": "production",
            "role": "user",
            "content": json.dumps({
                "role": "customer support assistant",
                "task_1": "Extract order details for products the customer explicitly wants to purchase now from {email_content}",
                "task_2": "Ignore comments about past or future purchases",
                "task_3": "Determine Product ID (remove spaces, ensure 7 characters), product description, and quantity",
                "task_4": "Handle vague quantities: 'few' as 3, 'all available' as 1000, unspecified as 1",
                "task_5": "Return a list of JSON objects with Product ID, description, and quantity",
                "example_output": "[{\"Product ID\": \"ABC1234\", \"Product description\": \"Blue Jeans\", \"Quantity\": 1}, {\"Product ID\": \"XYZ5678\", \"Product description\": \"T-shirt\", \"Quantity\": 2}]",
                "restrictions": "Set 'Product ID' to '' if not 7 characters or format 'ABC1234'."
            }, indent=2)
        },
        {
        "prompt_name": "order_response",
        "project": "customer_agent",
        "type": "production",
        "role": "user",
        "content": json.dumps({
            "role": "customer support assistant",
            "task_1": "Write a professional email based on order summary {summary_string}",
            "task_2": "Recommend other items based on the provided product names, IDs, and descriptions: {similar_items}",
            "task_3": "If a product has both quantity_filled > 0 and quantity_unfilled > 0, congratulate the customer on the filled portion and apologize for the unfilled portion.",
            "task_4": "If there is a filled quantity tell the customer that they can log into the website and use this code {code} to complete the order.",
            "task_5": "End with a friendly salutation signed Customer Service",
            "example_output": (
                "Dear Customer:\n"
                " We are excited to inform you that we are able to fulfill your request for:\n"
                "  3 Neon Sock (NOS1745)\n"
                "  1 Pair of Retro Blue Jean (BJT1876)\n"
                " Unfortunately we could not complete the entire request for:\n"
                "  3 Pair of Retro Blue Jean (BJT1876)\n"
                " We would like to recommend:\n"
                "  Faded Grey Jean 60's style (SIX2298)\n"
                " We think this would be a great choice. You can complete your order by logging into our website with this code {code}.\n"
                " Thank you for being a great customer and let me know if there is anything else I can help you with.\n"
                " Regards, Customer Service"
            ),
            "restrictions": "If no name is mentioned, use 'Dear Customer'. Do not include placeholders like [Your Name], [Your Position]"
        }, indent=2)
        },
        {
            "prompt_name": "order_extract_mentions",
            "project": "customer_agent",
            "type": "production",
            "role": "user",
            "content": json.dumps({
                "role": "customer support assistant",
                "task_1": "Extract a JSON list of products mentioned for past or future purchases from {email_content}",
                "task_2": "Provide Product ID (if mentioned) and product description",
                "example_output": "",
                "restrictions": ""
            }, indent=2)
        }
    ]

if __name__ == "__main__":
    load_dotenv()
    handler = MongoDBHandler()
    handler.create_collection("Prompts")
    handler.collection = handler.db["Prompts"]
    
    for prompt in get_prompts():
        try:
            inserted_id = handler.insert(prompt)
            logger.info(f"Inserted document '{prompt['prompt_name']}' with ID: {inserted_id}")
        except Exception as e:
            logger.error(f"Error inserting document '{prompt['prompt_name']}': {e}")
    
    handler.close()