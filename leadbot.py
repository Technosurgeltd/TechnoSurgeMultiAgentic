import os
import json
import base64
from dotenv import load_dotenv
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔐 Google Credential Setup for Render
def setup_google_credentials():
    service_account_base64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
    
    if not service_account_base64:
        print("❌ GOOGLE_APPLICATION_CREDENTIALS_BASE64 not found")
        return None
    
    try:
        service_account_info = json.loads(base64.b64decode(service_account_base64))
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        print("✅ Google credentials loaded successfully from environment variable")
        return creds
    except Exception as e:
        print(f"❌ Failed to setup Google credentials: {e}")
        return None

# Google Sheets setup
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

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

# ---------------- Intents ----------------
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

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",  # Use latest GPT model
            messages=[
                {"role": "system", "content": (
                    "Extract name and email from user input. Return ONLY JSON: "
                    "{\"name\": \"name_or_null\", \"email\": \"email_or_null\", \"refused\": true_or_false}. "
                    "Rules: Accept explicit names (e.g., 'My name is Zain') or standalone proper nouns as names (e.g., 'Zain'). "
                    "Capture valid emails (e.g., 'zain@example.com'). Do not infer names from emails. "
                    "If no new info, preserve previous values. If user refuses, set refused: true."
                )},
                {"role": "user", "content": f"Previous name: {prev_name or 'none'}, Previous email: {prev_email or 'none'}. User input: {user_input}"}
            ]
        )

        raw = resp.choices[0].message.content.strip()
        print(f"📝 Raw OpenAI response: {raw}")  # Debug log
        try:
            data = json.loads(raw)
            name = data.get("name") if data.get("name") != "null" else prev_name
            email = data.get("email") if data.get("email") != "null" else prev_email
            refused = data.get("refused", False)
            if refused:
                print("⚠️ User refused to provide details")
            return {"name": name or prev_name or "Unknown", "email": email or prev_email or "NULL"}
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed in analyze_details: {e}, Raw: {raw}")
            return prev_lead or {"name": "Unknown", "email": "NULL"}
    except Exception as e:
        print(f"❌ Error in analyze_details: {e}")
        return prev_lead or {"name": "Unknown", "email": "NULL"}

# ---------------- Save Lead ----------------
def save_lead_to_sheet(lead, conversation_history):
    if not lead or not worksheet:
        print("❌ Cannot save lead: Worksheet not available")
        return lead

    try:
        summary_resp = client.chat.completions.create(
            model="gpt-4o",  # Use latest GPT model
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
    except Exception as e:
        print(f"❌ Failed to save lead to sheet: {e}")
        return lead

# ---------------- AI Chat ----------------
def respond(user_msg: str, prev_lead: dict | None, conversation_memory: list):
    conversation_memory.append({"role": "user", "content": user_msg})

    intent = detect_intent(user_msg)
    conversation_ended = False
    if intent == "end":
        ai_reply = "Thank you for your time! Looking forward to assisting you further or seeing you at the demo. Goodbye 👋"
        conversation_memory.append({"role": "assistant", "content": ai_reply})
        lead = save_lead_to_sheet(prev_lead, conversation_memory)
        conversation_ended = True
        return ai_reply, lead, conversation_ended

    updated_lead = analyze_details(user_msg, prev_lead)
    print(f"📋 Updated lead: {updated_lead}")  # Debug log

    system_prompt = (
        "You are Technosurge's professional sales and marketing AI assistant, specializing in AI automation and voice AI solutions. "
        "Keep replies under 150 words, warm, professional, and engaging. Personalize with the user's name if known. "
        "If name/email not yet provided, politely request them at the end of your response (e.g., 'To get started, may I have your name and email?'). "
        "Highlight how our AI can solve their needs. Always guide toward scheduling a free demo for personalized advice."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use latest GPT model
            messages=[{"role": "system", "content": system_prompt}] + conversation_memory,
            temperature=0.7,
            max_tokens=200
        )

        ai_reply = response.choices[0].message.content.strip()
        conversation_memory.append({"role": "assistant", "content": ai_reply})
    except Exception as e:
        print(f"❌ Error in respond: {e}")
        ai_reply = "Sorry, I'm having trouble responding. Please try again or contact us directly!"

    return ai_reply, updated_lead, conversation_ended

def run_conversation_from_messages(messages: list, prev_lead: dict | None = None):
    conversation_memory = []

    for m in messages:
        if hasattr(m, "type") and hasattr(m, "content"):
            role = "user" if m.type == "human" else "assistant"
            conversation_memory.append({"role": role, "content": m.content})
        elif isinstance(m, dict):
            conversation_memory.append(m)

    last_user_msg = None
    for m in reversed(conversation_memory):
        if m["role"] == "user":
            last_user_msg = m["content"]
            break

    if not last_user_msg:
        return {
            "ai_reply": "Hi! I'm the Technosurge assistant. How can I help with your automation needs?",
            "lead": prev_lead or {"name": "Unknown", "email": "NULL", "summary": "No input yet"},
            "conversation_ended": False
        }

    ai_reply, updated_lead, conversation_ended = respond(last_user_msg, prev_lead, conversation_memory)

    return {
        "ai_reply": ai_reply,
        "lead": updated_lead,
        "conversation_ended": conversation_ended
    }
