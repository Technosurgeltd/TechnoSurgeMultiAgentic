import os
import json
import base64
from dotenv import load_dotenv
from email.mime.text import MIMEText
from openai import OpenAI
from google.oauth2.service_account import Credentials
import gspread
import smtplib
import time

# ===========================================
# 1️⃣ LOAD ENVIRONMENT VARIABLES
# ===========================================
load_dotenv()

# ===========================================
# 2️⃣ INITIALIZE SERVICES
# ===========================================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

# Google Sheets setup using environment variable directly
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Initialize Google Sheets
gc = None
worksheet = None
service_account_base64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64")

if service_account_base64:
    try:
        service_account_info = json.loads(base64.b64decode(service_account_base64))
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        gc = gspread.authorize(creds)
        print("✅ Google Sheets Connected via Environment Variable")
        
        sheet_name = "lead spreadsheet"
        worksheet = gc.open(sheet_name).sheet1
    except Exception as e:
        print(f"❌ Google Sheets Auth Failed: {e}")
else:
    print("❌ GOOGLE_APPLICATION_CREDENTIALS_BASE64 environment variable not found")

# ===========================================
# 3️⃣ EMAIL GENERATION (AI Powered)
# ===========================================
def generate_email(name, summary):
    prompt = (
        "Write a professional marketing email for Technosurge, an AI agency offering automation and voice AI services.\n"
        f"Lead Name: {name if name else 'there'}\n"
        f"Interest Summary: \"{summary}\"\n"
        "Guidelines:\n"
        "- Friendly but professional\n"
        "- Mention their interest\n"
        "- Include call to action for a free demo\n"
        "- Under 200 words\n"
        "Return JSON only:\n"
        "{\n"
        "  \"subject\": \"...\",\n"
        "  \"body\": \"...\"\n"
        "}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use latest GPT model
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )

        raw = response.choices[0].message.content.strip()
        try:
            data = json.loads(raw)
            if "subject" in data and "body" in data:
                return data["subject"], data["body"]
            else:
                print(f"❌ Malformed JSON response: {raw}")
                raise ValueError("JSON missing subject or body")
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}, Raw: {raw}")
            raise
    except Exception as e:
        print(f"❌ Email generation failed: {e}")
        return (
            "Let's Talk About AI Automation",
            f"Hi {name or 'there'},\n\nI'd love to show you how Technosurge can help with automation and AI solutions.\nWould you like to schedule a free demo?\n\nBest,\nTechnosurge Team"
        )

# ===========================================
# 4️⃣ SMTP EMAIL SENDER
# ===========================================
def send_email(to_email, subject, body, retries=3, delay=5):
    msg = MIMEText(body, "plain")
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = to_email

    print(f"📧 Sending to: {to_email}")
    for attempt in range(1, retries + 1):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(GMAIL_USER, GMAIL_PASS)
                server.sendmail(GMAIL_USER, to_email, msg.as_string())
            print(f"✅ Email delivered to {to_email}")
            return True
        except Exception as e:
            print(f"❌ Email attempt {attempt} failed to {to_email}: {e}")
            if attempt < retries:
                print(f"⏳ Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"❌ All {retries} email attempts failed to {to_email}")
                return False

# ===========================================
# 5️⃣ PROCESS ENTIRE SHEET
# ===========================================
def main():
    if not worksheet:
        print("❌ Google Sheets not available. Cannot process leads.")
        return

    try:
        leads = worksheet.get_all_records()
        print(f"📊 Leads Found: {len(leads)}")
    except Exception as e:
        print(f"❌ Failed to read sheet: {e}")
        return

    for idx, lead in enumerate(leads, start=2):
        name = lead.get("name")
        email = lead.get("email")
        summary = lead.get("summary") or "No summary provided"

        if email and email != "NULL":
            print(f"➡️ Processing: {name} <{email}>")
            subject, body = generate_email(name, summary)

            success = send_email(email, subject, body)
            worksheet.update_cell(idx, 4, "SENT" if success else "FAILED")

# ===========================================
# 6️⃣ SINGLE LEAD FUNCTION
# ===========================================
def send_email_to_lead(lead):
    if not worksheet:
        print("❌ Google Sheets not available.")
        return False

    name = lead.get("name")
    email = lead.get("email")
    summary = lead.get("summary") or "No summary provided"

    if not email or email == "NULL":
        print("⚠️ Invalid email, skipping...")
        return False

    try:
        subject, body = generate_email(name, summary)
        success = send_email(email, subject, body)
        if success:
            print(f"✅ Sent to {email}")
            cell = worksheet.find(email)
            if cell:
                worksheet.update_cell(cell.row, 4, "SENT")
        return success
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    main()
