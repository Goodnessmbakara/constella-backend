from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests


router = APIRouter(prefix="/aury", tags=["aury"])


# Dedicated Loops API key for Aury
_AURY_LOOPS_API_KEY = "bef01e2292c86b0fea89bf8188917e6e"


class CreateContactRequest(BaseModel):
    email: str


@router.post("/create-contact")
async def create_contact(payload: CreateContactRequest):
    try:
        url = "https://app.loops.so/api/v1/contacts/create"
        headers = {
            "Authorization": f"Bearer {_AURY_LOOPS_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "email": payload.email,
            "source": "aury",
            "subscribed": True,
        }

        response = requests.post(url, json=body, headers=headers, timeout=15)

        try:
            response_data = response.json()
        except Exception:
            response_data = {"text": response.text}

        print(response_data)

        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response_data)

        return {"success": True, "result": response_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


