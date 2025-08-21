import logging

from mongodb_handler import MongoDBHandler

logger = logging.getLogger(__name__)

def load_prompts(db_handler: MongoDBHandler, collection_prompts: str, role: str = None) -> dict:
    try:
        query = {"project": "customer_agent", "type": "production"}
        if role:
            query["role"] = role
        documents = db_handler.find_documents(
            collection_name=collection_prompts,
            query=query
        )
        return {doc["prompt_name"]: doc for doc in documents}
    except Exception as e:
        logger.error(f"Error loading prompts from '{collection_prompts}' with role '{role}': {e}")
        raise
    
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

def find_similar_products(
    db_handler,
    collection_name,
    query_embedding,
    k=1,
    exclude_product_ids=None,
    min_stock=0,
    num_candidates=100,
    distance_threshold=None,
    filter_features=None
):
    """
    Perform vector search to find similar products in MongoDB.
    
    Args:
        db_handler: MongoDBHandler instance for database access.
        collection_name (str): Name of the product collection.
        query_embedding (list): Embedding vector for the search query.
        k (int): Number of similar products to return (default: 1).
        exclude_product_ids (list): Product IDs to exclude (default: None).
        min_stock (int): Minimum stock level (default: 0).
        num_candidates (int): Number of candidates for vector search (default: 100).
        distance_threshold (float): Maximum distance for filtering (default: None).
        filter_features (dict): Feature filters (e.g., {'price': 10}) (default: None).
    
    Returns:
        tuple: (product_ids, distances, closest_products_df)
            - product_ids (list): List of matching product IDs.
            - distances (list): List of distances for matching products.
            - closest_products_df (DataFrame): Product details with distances.
    """
    # Normalize query embedding
    query_embedding = np.array(query_embedding).astype("float32")
    norm = np.linalg.norm(query_embedding)
    if norm > 0:
        query_embedding = query_embedding / norm
    logger.debug(f"Normalized query embedding norm: {np.linalg.norm(query_embedding)}")

    # Perform vector search
    product_ids, distances, indices = db_handler.vector_search(
        collection_name=collection_name,
        query_embedding=query_embedding,
        k=k,
        exclude_product_ids=exclude_product_ids,
        min_stock=min_stock,
        num_candidates=num_candidates
    )

    if not product_ids:
        logger.warning(f"No products found in vector search in '{collection_name}'")
        return [], [], pd.DataFrame()

    # Fetch all product documents
    all_products = db_handler.find_documents(collection_name)
    if not all_products:
        logger.warning(f"No documents found in '{collection_name}'")
        return [], [], pd.DataFrame()

    # Create DataFrame from all products
    df = pd.DataFrame(all_products)
    df['_id'] = df['_id'].astype(str)

    # Filter DataFrame to match indices from vector search
    try:
        closest_indices = [df.index[df['_id'] == str(result['_id'])].tolist()[0] for result in indices]
        closest_products_df = df.iloc[closest_indices].copy()
        closest_products_df["distance"] = distances[0]
    except IndexError:
        logger.warning(f"Error matching vector search indices to products")
        return product_ids, distances[0].tolist(), pd.DataFrame()

    # Apply distance threshold
    if distance_threshold is not None:
        closest_products_df = closest_products_df[closest_products_df["distance"] <= distance_threshold]
        logger.debug(f"After distance threshold {distance_threshold}, {len(closest_products_df)} products remain")
        # Update product_ids and distances to match filtered DataFrame
        product_ids = closest_products_df["product_id"].tolist()
        distances = closest_products_df["distance"].tolist()

    # Apply feature filters
    if filter_features:
        for feature, value in filter_features.items():
            if feature in closest_products_df.columns:
                closest_products_df = closest_products_df[closest_products_df[feature] >= value]
                logger.debug(f"After filtering {feature} >= {value}, {len(closest_products_df)} products remain")
        # Update product_ids and distances
        product_ids = closest_products_df["product_id"].tolist()
        distances = closest_products_df["distance"].tolist()

    if closest_products_df.empty:
        logger.warning("No products found after filtering")
        return [], [], pd.DataFrame()

    logger.debug(f"Vector search returned {len(product_ids)} products: {product_ids}")
    return product_ids, distances, closest_products_df