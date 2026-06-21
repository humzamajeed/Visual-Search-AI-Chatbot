"""
Stubbed similarity module for DevOps pipeline testing.
FAISS index and ResNet50 embedding model are not loaded — visual search
will return empty results until a real index is rebuilt from MongoDB data.
MongoDB connections remain fully functional.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Module-level state expected by app.py
_faiss_index = None
_faiss_index_to_cid_map = None
_image_embedding_model = None
_image_transform = None
_mongo_collection = None
_users_collection = None

_mongo_client = None


def load_faiss_index_and_map():
    """Stub: FAISS index intentionally not loaded (file not present)."""
    global _faiss_index, _faiss_index_to_cid_map
    logger.warning("FAISS index NOT loaded — running in stub mode.")
    _faiss_index = None
    _faiss_index_to_cid_map = None


def load_image_embedding_model_and_transform():
    """Stub: ResNet50 model intentionally not loaded."""
    global _image_embedding_model, _image_transform
    logger.warning("Image embedding model NOT loaded — running in stub mode.")
    _image_embedding_model = None
    _image_transform = None


def get_mongo_collection():
    """Real MongoDB connection for product data."""
    global _mongo_collection, _mongo_client
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "zappos_products")
    coll_name = os.getenv("MONGO_COLLECTION_NAME", "products")
    if _mongo_client is None:
        _mongo_client = MongoClient(mongo_uri)
    _mongo_collection = _mongo_client[db_name][coll_name]
    return _mongo_collection


def get_users_collection():
    """Real MongoDB connection for user auth data."""
    global _users_collection, _mongo_client
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGO_URI", "mongodb://mongo:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "zappos_products")
    users_coll_name = os.getenv("MONGO_USERS_COLLECTION_NAME", "users")
    if _mongo_client is None:
        _mongo_client = MongoClient(mongo_uri)
    _users_collection = _mongo_client[db_name][users_coll_name]
    return _users_collection


def get_image_embedding(image):
    """Stub: returns None since no embedding model is loaded."""
    logger.warning("get_image_embedding called in stub mode — returning None.")
    return None


def search_faiss(query_embedding, k=50):
    """Stub: returns empty results since FAISS index is not loaded."""
    logger.warning("search_faiss called in stub mode — returning empty list.")
    return []


def get_product_details_from_mongo(product_ids):
    """Real lookup — works once MongoDB has product data."""
    collection = get_mongo_collection() if _mongo_collection is None else _mongo_collection
    if not product_ids:
        return []
    return list(collection.find({"_id": {"$in": product_ids}}))
