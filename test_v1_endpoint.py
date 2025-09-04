#!/usr/bin/env python3
"""
Minimal test server for testing the v1 check integrations endpoint.
This bypasses the problematic milvus imports to test the core functionality.
"""

from fastapi import FastAPI
from routers.horizon.integrations import router
import uvicorn
import os

# Set environment variables
os.environ.setdefault("ARCADE_API_KEY", "test_key")

app = FastAPI(title="V1 Endpoint Test Server")

# Include only the horizon integrations router
app.include_router(router)


@app.get("/")
async def root():
    return {"message": "V1 Endpoint Test Server", "endpoint": "/horizon/integrations/v1/check_integrations"}


@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Server is running"}

if __name__ == "__main__":
    print("🚀 Starting V1 Endpoint Test Server...")
    print("✅ V1 endpoint available at: /horizon/integrations/v1/check_integrations")
    print("✅ Health check at: /health")
    print("✅ Server will run on: http://localhost:8001")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )

