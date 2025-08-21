import json
import os

from dotenv import load_dotenv

from mongodb_handler import MongoDBHandler

# Define prompts
order_response = {
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
}

verify_category = {
    "prompt_name": "verify_category",
    "project": "customer_agent",
    "type": "production",
    "role": "user",
    "content": json.dumps({
        "role": "quality control agent",
        "task_1": "Read the customer email and determine what products the customer was interested in {email}",
        "task_2": "Read this list of similar products and determine which products align with the customers intent and if they would be good alternative suggestions: {similar_items}",
        "task_3": "Provide 2 lists in your response: list of Good Alternative items and a list of Bad Alternative items",
        "restrictions": "you must provide 2 lists even if one is empty and label each list either Good Alternative or Bad Alternative"
    }, indent=2)
}

if __name__ == "__main__":
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    db = os.getenv('MONGO_DB_NAME')
    handler = MongoDBHandler(uri, db)
    handler.collection = handler.db["Prompts"]

    # Update order_response prompt's content field
    handler.update_document(
        collection_name="Prompts",
        query={"prompt_name": "order_response"},
        update_data={"content": order_response["content"]}
    )

    # Insert verify_category prompt
    handler.insert(collection_name="Prompts", data=verify_category)

    handler.close()

