"""
Flask API application for visual product search.

This module provides REST API endpoints for:
- User authentication (signup/login with JWT)
- Visual product search using image embeddings
- Text-based product search

The application uses ResNet50 for image embeddings and FAISS for similarity search.
"""

import io
import math
import os
import sys
import base64
import logging

from datetime import timedelta
from PIL import Image

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    create_access_token,
    JWTManager,
    jwt_required,
    get_jwt_identity,
    verify_jwt_in_request
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Add parent directory to path for model imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
from models import similarity_module as similarity

# Load environment variables from project root
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path, override=True)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Prometheus metrics instrumentation
from prometheus_flask_exporter import PrometheusMetrics
metrics = PrometheusMetrics(app)

# JWT Configuration
# TODO: In production, use os.getenv("JWT_SECRET_KEY") with a strong, unique value
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY",
    "my-fixed-super-secret-key-for-debugging-only"
)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
jwt = JWTManager(app)


# JWT Error Handlers
@jwt.unauthorized_loader
def handle_unauthorized(callback):
    """Handle requests without authentication token."""
    logger.error("Unauthorized access attempt: No token provided.")
    return jsonify({"error": "Request does not contain an access token."}), 401


@jwt.invalid_token_loader
def handle_invalid_token(callback):
    """Handle requests with invalid authentication token."""
    logger.error("Invalid token provided: Signature verification failed.")
    return jsonify({
        "error": "Invalid token provided. Signature verification failed."
    }), 401


@jwt.expired_token_loader
def handle_expired_token(callback):
    """Handle requests with expired authentication token."""
    logger.error("Expired token provided.")
    return jsonify({"error": "Token has expired."}), 401


@jwt.revoked_token_loader
def handle_revoked_token(callback):
    """Handle requests with revoked authentication token."""
    logger.error("Revoked token provided.")
    return jsonify({"error": "Token has been revoked."}), 401


def clean_nan_values(data):
    """
    Recursively clean NaN float values from data structures.

    Converts NaN values to None for JSON compatibility.

    Args:
        data: Dictionary, list, or primitive value to clean

    Returns:
        Cleaned data structure with NaN values replaced by None
    """
    if isinstance(data, dict):
        return {key: clean_nan_values(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_nan_values(item) for item in data]
    elif isinstance(data, float) and math.isnan(data):
        return None
    else:
        return data


def initialize_resources():
    """
    Initialize all required resources for the application.

    Loads FAISS index, image embedding model, and establishes MongoDB connections.
    Exits the application if any critical resource fails to load.
    """
    logger.info("Starting resource initialization sequence...")

    try:
        logger.info("Loading FAISS index and CID mapping...")
        similarity.load_faiss_index_and_map()

        logger.info("Loading image embedding model and transforms...")
        similarity.load_image_embedding_model_and_transform()

        logger.info("Establishing MongoDB connections...")
        similarity.get_mongo_collection()
        similarity.get_users_collection()

        logger.info("Resource initialization completed successfully.")

        # Verify all resources loaded correctly
        if (similarity._faiss_index is None or
                similarity._image_embedding_model is None or
                similarity._mongo_collection is None or
                similarity._faiss_index_to_cid_map is None or
                similarity._users_collection is None):
            logger.critical(
                "One or more critical resources failed to load. "
                "API may not function correctly."
            )

    except Exception as error:
        logger.critical(
            f"CRITICAL ERROR during app initialization: {error}",
            exc_info=True
        )
        sys.exit(1)


# Initialize resources on startup
initialize_resources()


# Authentication Endpoints
@app.route('/signup', methods=['POST'])
def signup():
    """
    Register a new user account.

    Request body:
        {
            "username": str,
            "password": str
        }

    Returns:
        201: User created successfully
        400: Missing username or password
        409: Username already exists
        500: Database unavailable
    """
    request_data = request.get_json()
    username = request_data.get('username') if request_data else None
    password = request_data.get('password') if request_data else None

    if not username or not password:
        return jsonify({
            "error": "Username and password are required"
        }), 400

    users_collection = similarity.get_users_collection()
    if users_collection is None:
        logger.error("MongoDB users collection not available for signup.")
        return jsonify({
            "error": "Database not available for signup"
        }), 500

    if users_collection.find_one({"username": username}):
        return jsonify({
            "error": "Username already exists"
        }), 409

    hashed_password = generate_password_hash(password)
    users_collection.insert_one({
        "username": username,
        "password": hashed_password
    })
    logger.info(f"User '{username}' signed up successfully.")
    return jsonify({
        "message": "User created successfully"
    }), 201


@app.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and return JWT access token.

    Request body:
        {
            "username": str,
            "password": str
        }

    Returns:
        200: Login successful with access token
        400: Missing username or password
        401: Invalid credentials
        500: Database unavailable
    """
    request_data = request.get_json()
    username = request_data.get('username') if request_data else None
    password = request_data.get('password') if request_data else None

    if not username or not password:
        return jsonify({
            "error": "Username and password are required"
        }), 400

    users_collection = similarity.get_users_collection()
    if users_collection is None:
        logger.error("MongoDB users collection not available for login.")
        return jsonify({
            "error": "Database not available for login"
        }), 500

    user = users_collection.find_one({"username": username})

    if user and check_password_hash(user['password'], password):
        access_token = create_access_token(identity=username)
        logger.info(f"User '{username}' logged in successfully.")
        return jsonify({
            "message": "Login successful",
            "username": username,
            "access_token": access_token
        }), 200
    else:
        logger.warning(f"Failed login attempt for username: '{username}'")
        return jsonify({
            "error": "Invalid username or password"
        }), 401


# Search Endpoints
@app.route('/api/visual-search', methods=['POST'])
def visual_search():
    """
    Perform visual similarity search using an uploaded image.
    Authentication is optional - works without JWT token.

    Accepts image via:
        - multipart/form-data with 'image' file field
        - JSON with base64-encoded 'image' field

    Query parameters:
        k (int, default=50): Number of results to return

    Returns:
        200: Search results with product details
        400: Invalid image data
        415: Unsupported content type
        500: Configuration or processing error
    """
    """
    Perform visual similarity search using an uploaded image.

    Accepts image via:
        - multipart/form-data with 'image' file field
        - JSON with base64-encoded 'image' field

    Query parameters:
        k (int, default=50): Number of results to return

    Returns:
        200: Search results with product details
        400: Invalid image data
        415: Unsupported content type
        500: Configuration or processing error
    """
    try:
        # Verify resources are loaded
        if (similarity._faiss_index is None or
                similarity._image_embedding_model is None or
                similarity._mongo_collection is None or
                similarity._faiss_index_to_cid_map is None):
            logger.error(
                "Critical resources not loaded for visual search."
            )
            return jsonify({
                "error": "Configuration error: Resources not loaded."
            }), 500

        # Extract image from request
        image = None

        # Case 1: Multipart form data with file
        if 'image' in request.files:
            file = request.files['image']
            if file.filename == '':
                return jsonify({
                    "error": "Empty image filename"
                }), 400
            image = Image.open(file.stream).convert("RGB")

        # Case 2: JSON with base64 encoded image
        elif request.is_json:
            request_data = request.get_json()
            base64_image_data = request_data.get('image')
            if not base64_image_data:
                return jsonify({
                    "error": "No base64 image data provided"
                }), 400
            image_bytes = io.BytesIO(base64.b64decode(base64_image_data))
            image = Image.open(image_bytes).convert("RGB")

        else:
            return jsonify({
                "error": "Unsupported content type. "
                         "Use multipart/form-data or JSON with base64 image."
            }), 415

        # Generate embedding and search
        query_embedding = similarity.get_image_embedding(image)
        num_results = request.args.get('k', 50, type=int)

        # Perform FAISS search
        faiss_results = similarity.search_faiss(
            query_embedding,
            k=num_results
        )

        # Extract product IDs from results
        matched_product_ids = [result['cid'] for result in faiss_results]

        # Create mapping of product ID to similarity metrics
        similarity_metrics = {
            result['cid']: {
                'distance': result['distance'],
                'similarity': result['similarity']
            }
            for result in faiss_results
        }

        # Fetch product details from MongoDB
        product_details = similarity.get_product_details_from_mongo(
            matched_product_ids
        )

        # Combine FAISS results with MongoDB product data
        combined_results = []
        for product in product_details:
            product_id = product.get('CID')
            if product_id and product_id in similarity_metrics:
                combined_product = {
                    **product,
                    **similarity_metrics[product_id]
                }
                combined_results.append(combined_product)

        # Sort by similarity (descending)
        combined_results.sort(
            key=lambda x: x.get('similarity', 0),
            reverse=True
        )

        # Clean NaN values for JSON compatibility
        cleaned_results = clean_nan_values(combined_results)

        # Log image URL availability for debugging
        results_with_images = sum(1 for r in cleaned_results if r.get('cloudinary_url'))
        logger.info(
            f"Visual search returned {len(cleaned_results)} results, "
            f"{results_with_images} with images"
        )

        return jsonify({"results": cleaned_results}), 200

    except Exception as error:
        logger.error(
            f"Visual search error: {str(error)}",
            exc_info=True
        )
        return jsonify({
            "error": f"Internal server error during visual search: {str(error)}"
        }), 500


@app.route('/api/text-search', methods=['POST'])
def text_search():
    """
    Perform text-based product search across multiple fields.
    Authentication is optional - works without JWT token.

    Request body:
        {
            "query": str
        }

    Returns:
        200: Search results with product details
        400: Empty query
        500: Configuration error
    """
    try:
        if similarity._mongo_collection is None:
            logger.error(
                "MongoDB products collection not loaded for text search."
            )
            return jsonify({
                "error": "Configuration error: MongoDB not loaded."
            }), 500

        request_data = request.json
        query_text = request_data.get('query', '').strip()

        if not query_text:
            logger.warning("Empty query received for text search.")
            return jsonify({
                "error": "Query cannot be empty"
            }), 400

        logger.info(f"Received text search query: '{query_text}'")

        # Build MongoDB search filter
        # Search across multiple fields with case-insensitive regex
        search_fields = [
            "title", "category", "SubCategory", "gender",
            "material", "closure", "toe_style", "heel_height", "insole"
        ]
        search_filter = {
            "$or": [
                {field: {"$regex": query_text, "$options": "i"}}
                for field in search_fields
            ]
        }

        logger.debug(f"Executing MongoDB query: {search_filter}")

        # Execute search with limit
        products_cursor = similarity._mongo_collection.find(
            search_filter
        ).limit(50)

        results = []
        found_product_ids = []

        for document in products_cursor:
            product_id = str(document.get('_id'))
            
            # Build product data directly from document (more efficient)
            product_data = {
                "CID": product_id,
                "title": similarity.generate_product_title(
                    document.get('gender'),
                    document.get('material'),
                    document.get('SubCategory')
                ) or f"Zappos Product {product_id}",
                "cloudinary_url": document.get('cloudinary_url') or document.get('image_url') or document.get('url'),
                "category": document.get('category', 'N/A'),
                "SubCategory": document.get('SubCategory', 'N/A'),
                "gender": document.get('gender', 'N/A'),
                "material": document.get('material', 'N/A'),
                "closure": document.get('closure', 'N/A'),
                "toe_style": document.get('toe_style', 'N/A'),
                "heel_height": document.get('heel_height', 'N/A'),
                "insole": document.get('insole', 'N/A'),
                "distance": 0.0,  # Text search doesn't have similarity metric
            }
            
            results.append(product_data)
            found_product_ids.append(product_id)

        # Clean NaN values
        cleaned_results = clean_nan_values(results)
        
        # Log image URL availability for debugging
        results_with_images = sum(1 for r in cleaned_results if r.get('cloudinary_url'))
        logger.info(
            f"Text search returned {len(cleaned_results)} products for query '{query_text}'. "
            f"{results_with_images} have images, {len(cleaned_results) - results_with_images} without images"
        )

        return jsonify({"results": cleaned_results}), 200

    except Exception as error:
        logger.error(
            f"Error during text search: {error}",
            exc_info=True
        )
        return jsonify({
            "error": f"An internal server error occurred during text search: {str(error)}"
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
