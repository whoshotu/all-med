FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port (Cloud Run defaults to 8080, but can be overridden by $PORT)
ENV PORT=8000
EXPOSE $PORT

# Start the FastAPI server
CMD uvicorn apps.python.medops_call_commander.server:app --host 0.0.0.0 --port $PORT
