from fastapi import FastAPI
import requests

app = FastAPI()

BASE_URL = "https://insurance-api-471936962134.us-central1.run.app"


@app.get("/tools/get_customer")
async def get_customer(email: str):
    res = requests.get(f"{BASE_URL}/customer/{email}")
    return res.json()


@app.get("/tools/get_claim")
async def get_claim(claim_number: str):
    res = requests.get(f"{BASE_URL}/claim/{claim_number}")
    return res.json()


@app.get("/tools/get_full_details")
async def get_full_details(email: str):
    res = requests.get(f"{BASE_URL}/full-details/{email}")
    return res.json()


@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": "get_customer",
                "description": "Get customer details using email",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"}
                    },
                    "required": ["email"]
                }
            },
            {
                "name": "get_claim",
                "description": "Get claim details using claim ID",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "integer"}
                    },
                    "required": ["claim_id"]
                }
            },
            {
                "name": "get_full_details",
                "description": "Get full insurance details",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"}
                    },
                    "required": ["email"]
                }
            }
        ]
    }