import logging

from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

def load_prompts(db_handler: MongoDBHandler, collection_prompts: str) -> dict:
    """
    Load prompts from the specified MongoDB collection.

    Args:
        db_handler (MongoDBHandler): Instance of MongoDBHandler for database access.
        collection_prompts (str): Name of the prompts collection.

    Returns:
        dict: Dictionary mapping prompt_name to the corresponding document.

    Raises:
        Exception: If the database query fails.
    """
    try:
        documents = db_handler.find_documents(
            collection_name=collection_prompts,
            query={"project": "customer_agent", "type": "production"}
        )
        return {doc["prompt_name"]: doc for doc in documents}
    except Exception as e:
        logger.error(f"Error loading prompts from '{collection_prompts}': {e}")
        raise