import os
import json
import base64
from dotenv import load_dotenv
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Fixed typo

# 🔐 Google Credential Setup for Render
def setup_google_credentials():
    service_account_base64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
    
    if not service_account_base64:
        print("❌ GOOGLE_APPLICATION_CREDENTIALS_BASE64 not found")
        return None
    
    try:
        # Decode base64 and create credentials directly without saving to file
        service_account_info = json.loads(base64.b64decode(service_account_base64))
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        print("✅ Google credentials loaded successfully from environment variable")
        return creds
    except Exception as e:
        print(f"❌ Failed to setup Google credentials: {e}")
        return None

# Google Sheets setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Initialize Google credentials
creds = setup_google_credentials()

if creds:
    gc = gspread.authorize(creds)
    try:
        sheet_name = "lead spreadsheet"
        worksheet = gc.open(sheet_name).sheet1
        print("✅ Google Sheets connected successfully")
    except Exception as e:
        print(f"❌ Google Sheets connection failed: {e}")
        gc = None
        worksheet = None
else:
    gc = None
    worksheet = None
    print("❌ Google Sheets not available due to credential issues")

# ---------------- Rest of your code remains the same ----------------
intents = {
    "end": {
        "keywords": ["bye", "thanks", "goodbye", "stop", "end", "quit", "that's all", "finished", "no more"],
        "threshold": 1
    }
}

def detect_intent(user_input):
    user_input = user_input.lower()
    for intent, data in intents.items():
        overlap = sum(1 for kw in data["keywords"] if kw in user_input)
        if overlap >= data["threshold"]:
            return intent
    return "general"

# ---------------- Extract Lead Details ----------------
def analyze_details(user_input, prev_lead=None):
    prev_name = prev_lead.get("name") if prev_lead else None
    prev_email = prev_lead.get("email") if prev_lead else None

    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": (
                "Extract name and email from user input. Return ONLY JSON: "
                '{"name": "name_or_null", "email": "email_or_null", "refused": true_or_false}. '
                "Rules: Only accept explicit names (e.g., 'My name is Haider'). "
                "Do not infer names from email. If valid email provided, capture it. "
                "Merge with previous info if partial."
            )},
            {"role": "user", "content": f"Previous name: {prev_name or 'none'}, Previous email: {prev_email or 'none'}. User input: {user_input}"}
        ]
    )

    try:
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        name = data.get("name") if data.get("name") != "null" else prev_name
        email = data.get("email") if data.get("email") != "null" else prev_email
        return {"name": name or "Unknown", "email": email or "NULL"}
    except:
        return prev_lead or {"name": "Unknown", "email": "NULL"}

# ---------------- Save Lead ----------------
def save_lead_to_sheet(lead, conversation_history):
    if not lead or not worksheet:
        print("❌ Cannot save lead: Worksheet not available")
        return

    summary_resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Summarize the conversation in 2-3 sentences, focusing on business needs and AI services."},
            {"role": "user", "content": json.dumps(conversation_history)}
        ]
    )
    summary = summary_resp.choices[0].message.content.strip()
    lead["summary"] = summary

    worksheet.append_row([lead.get("name", "NULL"), lead.get("email", "NULL"), summary])
    print("✅ Lead saved to Google Sheet.")
    return lead

# ---------------- AI Chat ----------------
conversation_memory = []

def respond(user_msg: str, prev_lead: dict | None):
    """
    Handle one user message, return AI reply + updated lead.
    """
    global conversation_memory
    conversation_memory.append({"role": "user", "content": user_msg})

    # Detect intent
    intent = detect_intent(user_msg)
    if intent == "end":
        ai_reply = "Thank you for your time! Looking forward to assisting you further or seeing you at the demo. Goodbye 👋"
        conversation_memory.append({"role": "assistant", "content": ai_reply})

        # Save lead + summary ONLY on conversation end
        lead = save_lead_to_sheet(prev_lead, conversation_memory)
        return ai_reply, lead, True   # True = conversation ended

    # Extract details
    updated_lead = analyze_details(user_msg, prev_lead)

    # Ask AI for reply
    system_prompt = (
        "You are Technosurge's professional sales and marketing AI assistant. "
        "Keep replies under 150 words, warm and professional. "
        "If name/email not yet provided, politely request them. "
        "Guide user toward scheduling a demo. "
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}] + conversation_memory,
        temperature=0.7,
        max_tokens=200
    )

    ai_reply = response.choices[0].message.content.strip()
    conversation_memory.append({"role": "assistant", "content": ai_reply})

    return ai_reply, updated_lead, False   # False = still ongoing

def run_conversation_from_messages(messages: list, prev_lead: dict | None = None):
    """
    Resume or continue a conversation given message history.
    Supports LangChain message objects or dict messages.
    Returns the AI reply + updated lead.
    """
    global conversation_memory
    conversation_memory = []

    # Normalize messages into dicts {role, content}
    for m in messages:
        if hasattr(m, "type") and hasattr(m, "content"):  # HumanMessage / AIMessage
            role = "user" if m.type == "human" else "assistant"
            conversation_memory.append({"role": role, "content": m.content})
        elif isinstance(m, dict):
            conversation_memory.append(m)

    # Find last user message
    last_user_msg = None
    for m in reversed(conversation_memory):
        if m["role"] == "user":
            last_user_msg = m["content"]
            break

    if not last_user_msg:
        return {
            "ai_reply": "Hi! I'm the Technosurge assistant. How can I help with your automation needs?",
            "lead": prev_lead or {"name": "Unknown", "email": "NULL", "summary": "No input yet"}
        }

    # ✅ IMPORTANT: Pass the previous lead to maintain context
    ai_reply, updated_lead, conversation_ended = respond(last_user_msg, prev_lead)

    return {
        "ai_reply": ai_reply,
        "lead": updated_lead,
        "conversation_ended": conversation_ended
    }
