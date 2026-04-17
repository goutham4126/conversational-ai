from mcp.server.fastmcp import FastMCP
import requests
import logging
import uvicorn

# Initialize FastMCP server
mcp = FastMCP("Insurance Tool Server")

BASE_URL = "https://insurance-api-471936962134.us-central1.run.app"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server")

@mcp.tool()
def get_customer(email: str) -> dict:
    """
    Get basic customer details using their registered email address.
    Use this when you specifically need personal info, policy list, or contact details.
    """
    logger.info(f"Calling get_customer for: {email}")
    try:
        res = requests.get(f"{BASE_URL}/customer/{email}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        logger.error(f"Error in get_customer: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_claim(claim_number: str) -> dict:
    """
    Retrieve specific claim details and status by claim number.
    Use this when a user provides a claim ID (e.g., CLM101) or asks about a specific incident.
    """
    logger.info(f"Calling get_claim for: {claim_number}")
    try:
        res = requests.get(f"{BASE_URL}/claim/{claim_number}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        logger.error(f"Error in get_claim: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_full_details(email: str) -> dict:
    """
    Get comprehensive insurance details including policies, all claims, and history for a customer.
    Prefer this tool for complex queries where the user wants a full overview of their account.
    """
    logger.info(f"Calling get_full_details for: {email}")
    try:
        res = requests.get(f"{BASE_URL}/full-details/{email}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        logger.error(f"Error in get_full_details: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    logger.info("Starting MCP Server on port 8001 using SSE transport...")
    app = mcp.sse_app()
    uvicorn.run(app, host="0.0.0.0", port=8001)