FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port 9000
EXPOSE 9000

# Set environment variables
ENV PYTHONPATH=/app

# Run the application on port 9000
CMD ["uvicorn", "workflow:app", "--host", "0.0.0.0", "--port", "9000"]