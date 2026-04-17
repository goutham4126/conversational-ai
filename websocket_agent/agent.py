from google.adk.agents.llm_agent import Agent
import requests

# post call summary
summary_agent = Agent(
    model='gemini-2.5-flash',
    name='call_summary_agent',
    description='An agent that generates structured post-call summaries from voice transcripts.',
    instruction="""You are a professional call summarization agent for an insurance company.
  You will receive the full transcript of a customer support voice call between a User (customer) and an Assistant (AI agent).

  Your job is to produce a concise, structured summary in JSON format with the following fields:

  {
    "title": "A short 5-8 word title for this call",
    "language": "The primary language(s) used in the call (e.g., English, Hindi, Tamil, etc.)",
    "customer_intent": "What the customer was calling about (1-2 sentences)",
    "key_topics": ["topic1", "topic2", "topic3"],
    "resolution": "How the call was resolved or what next steps were agreed upon (1-2 sentences)",
    "sentiment": "positive | neutral | negative | escalated",
    "action_items": ["Any follow-up actions mentioned"],
    "call_quality": "brief | normal | detailed",
    "summary": "A 2-4 sentence natural language summary of the entire call"
  }

  Rules:
  - Be factual — only include information actually discussed in the transcript
  - Do NOT invent policy numbers, claim amounts, or dates not mentioned
  - If the call was very short or mostly noise, set sentiment to "neutral" and note it in the summary
  - The title should be descriptive and professional (e.g., "Health Claim Status Inquiry", "Policy Renewal Discussion")
  - Respond ONLY with the JSON object, no markdown formatting, no code blocks, no extra text
  """,
  )





# MCP Tool Integration
import json
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_SERVER_URL = "http://localhost:8001/sse"

async def _call_mcp_tool(tool_name: str, arguments: dict):
    """Internal helper to call an MCP tool via SSE transport."""
    try:
        async with sse_client(MCP_SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                
                # MCP tool results are returned as a list of content blocks
                if not result.content:
                    return {"error": "No content returned from tool"}
                
                # Try to parse as JSON if it looks like a JSON string, otherwise return raw text
                content_text = result.content[0].text
                try:
                    return json.loads(content_text)
                except:
                    return content_text
    except Exception as e:
        return {"error": f"MCP Client Error: {str(e)}"}

async def get_customer(email: str):
    """Get basic customer details using their registered email address."""
    return await _call_mcp_tool("get_customer", {"email": email})

async def get_claim(claim_number: str):
    """Retrieve specific claim details and status by claim number."""
    return await _call_mcp_tool("get_claim", {"claim_number": claim_number})

async def get_full_details(email: str):
    """Get comprehensive insurance details including policies, all claims, and history for a customer."""
    return await _call_mcp_tool("get_full_details", {"email": email})


root_agent = Agent(
    model="gemini-2.5-flash",
    name="insurance_agent",
    description="Handles insurance queries by leveraging official MCP tools.",
    instruction="""
You are an expert insurance assistant. Use the provided MCP tools to answer customer questions accurately.

Use tools smartly:
- If user gives email → use get_full_details for a complete overview.
- If user asks specifically for customer info → use get_customer.
- If a claim number is mentioned (e.g. CLM101) → use get_claim.

Prefer get_full_details when you need a holistic view of the customer's account.
""",
    tools=[get_customer, get_claim, get_full_details]
)