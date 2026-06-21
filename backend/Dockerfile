FROM docker.io/library/python:3.10-slim-bookworm
WORKDIR /app

# System dependencies needed for PyTorch, Pillow, bcrypt
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    build-essential \
    gfortran \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# NOTE: faiss_index.bin and cid_map.npy are stubbed out for now.
# COPY backend/faiss_index.bin .
# COPY backend/cid_map.npy .

# Copy the models package (similarity_module.py) so 'from models import similarity_module' works
COPY models/ ./models/
COPY backend/app.py .

ENV PORT=5000
# Essential for PyTorch on some systems
ENV KMP_DUPLICATE_LIB_OK=TRUE

EXPOSE 5000
CMD gunicorn --bind 0.0.0.0:$PORT app:app
