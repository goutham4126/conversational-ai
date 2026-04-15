from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='A helpful assistant for user questions.',
    instruction='Answer user questions to the best of your knowledge',
)

summary_agent = Agent(
    model='gemini-2.5-flash',
    name='call_summary_agent',
    description='An agent that generates structured post-call summaries from voice transcripts.',
    instruction="""You are a professional call summarization agent for an insurance company.
  You will receive the full transcript of a customer support voice call between a User (customer) and an Assistant (AI agent).

  Your job is to produce a concise, structured summary in JSON format with the following fields:

  {
    "title": "A short 5-8 word title for this call",
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