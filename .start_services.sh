#!/bin/bash

# Constella Backend Service Starter
# This script starts all necessary services for the Constella backend

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Constella Backend Services...${NC}"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating one...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Check if requirements need to be installed
echo -e "${GREEN}Installing/updating dependencies...${NC}"
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    if [ -f ".env.backup" ]; then
        echo -e "${YELLOW}No .env file found. Copying from .env.backup...${NC}"
        cp .env.backup .env
    else
        echo -e "${RED}Error: No .env file found. Please create one with required environment variables.${NC}"
        exit 1
    fi
fi

# Load environment variables
echo -e "${GREEN}Loading environment variables...${NC}"
# Use grep to filter out comments and empty lines, then export
set -o allexport
source .env
set +o allexport

# Check MongoDB connection
echo -e "${GREEN}Checking MongoDB connection...${NC}"
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
from db.mongodb import get_client, get_db
try:
    client = get_client()
    db = get_db()
    if client is not None and db is not None:
        print('✓ MongoDB connection successful')
    else:
        print('✗ MongoDB connection failed')
        exit(1)
except Exception as e:
    print(f'✗ MongoDB connection error: {e}')
    exit(1)
"

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}Warning: ngrok is not installed. The server will only be available locally.${NC}"
    echo -e "${YELLOW}To install ngrok: brew install ngrok/ngrok/ngrok${NC}"
    NGROK_AVAILABLE=false
else
    NGROK_AVAILABLE=true
fi

# Function to cleanup background processes
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    if [ -n "$UVICORN_PID" ]; then
        kill $UVICORN_PID 2>/dev/null || true
    fi
    if [ -n "$GUNICORN_PID" ]; then
        kill $GUNICORN_PID 2>/dev/null || true
    fi
    if [ -n "$NGROK_PID" ]; then
        kill $NGROK_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers for graceful shutdown
trap cleanup SIGINT SIGTERM

# Start ngrok in the background if available
if [ "$NGROK_AVAILABLE" = true ]; then
    echo -e "${GREEN}Starting ngrok tunnel...${NC}"
    ngrok http 8000 --log=stdout > ngrok.log 2>&1 &
    NGROK_PID=$!
    
    # Wait a moment for ngrok to start
    sleep 3
    
    # Extract the public URL from ngrok
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'] if data['tunnels'] else 'Not available')" 2>/dev/null || echo "Not available")
    
    if [ "$NGROK_URL" != "Not available" ]; then
        echo -e "${GREEN}✓ Ngrok tunnel established!${NC}"
        echo -e "${YELLOW}Public URL: $NGROK_URL${NC}"
        echo -e "${YELLOW}Public API docs: $NGROK_URL/docs${NC}"
    else
        echo -e "${YELLOW}Ngrok started but URL not immediately available. Check ngrok.log for details.${NC}"
    fi
fi

# Start the FastAPI application
echo -e "${GREEN}Starting FastAPI server...${NC}"
echo -e "${YELLOW}Local server: http://localhost:8000${NC}"
echo -e "${YELLOW}Local API docs: http://localhost:8000/docs${NC}"

# Use uvicorn for development or gunicorn for production based on ENV
if [ "$ENV" = "prod" ] || [ "$ENV" = "production" ]; then
    echo -e "${GREEN}Starting in production mode with gunicorn...${NC}"
    gunicorn main:app --workers 4 --timeout 90 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 &
    GUNICORN_PID=$!
else
    echo -e "${GREEN}Starting in development mode with uvicorn...${NC}"
    uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
    UVICORN_PID=$!
fi

echo -e "${GREEN}✓ All services started successfully!${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Wait for background processes
wait
