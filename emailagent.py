import os
import json
import base64
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
from openai import OpenAI
from google.oauth2.service_account import Credentials
import gspread

# ===========================================
# 1️⃣ LOAD ENV & DECODE GOOGLE CREDENTIALS
# ===========================================
load_dotenv()

# Base64 Google Credential Fix (Render Friendly)
service_account_base64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
if service_account_base64 and not os.path.exists("serviceaccount.json"):
    try:
        with open("serviceaccount.json", "wb") as f:
            f.write(base64.b64decode(service_account_base64))
        print("🔐 Google service account decoded successfully.")
    except Exception as e:
        print(f"❌ Failed to decode Google credentials: {e}")

# ===========================================
# 2️⃣ INITIALIZE SERVICES
# ===========================================
client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

SERVICE_ACCOUNT_FILE = "serviceaccount.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    print("✅ Google Sheets Connected")
except Exception as e:
    print(f"❌ Google Sheets Auth Failed: {e}")
    exit()

# Google Sheet Name
sheet_name = "lead spreadsheet"
worksheet = gc.open(sheet_name).sheet1

# ===========================================
# 3️⃣ EMAIL GENERATION (AI Powered)
# ===========================================
def generate_email(name, summary):
    prompt = f"""
    Write a professional marketing email for Technosurge, an AI agency offering automation and voice AI services.
    Lead Name: {name if name else "there"}
    Interest Summary: "{summary}"

    Guidelines:
    - Friendly but professional
    - Mention their interest
    - Include call to action for a free demo
    - Under 200 words
    Return JSON only:
    {{
      "subject": "...",
      "body": "..."
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.7
    )

    raw = response.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        return data["subject"], data["body"]
    except:
        return (
            "Let’s Talk About AI Automation",
            f"Hi {name},\n\nI’d love to show you how Technosurge can help with automation and AI solutions.\nWould you like to schedule a free demo?\n\nBest,\nTechnosurge Team"
        )

# ===========================================
# 4️⃣ SMTP EMAIL SENDER
# ===========================================
def send_email(to_email, subject, body):
    msg = MIMEText(body, "plain")
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = to_email

    print(f"📧 Sending to: {to_email}")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        print(f"✅ Email delivered to {to_email}")
    except Exception as e:
        print(f"❌ Email failed to {to_email}: {e}")

# ===========================================
# 5️⃣ PROCESS ENTIRE SHEET
# ===========================================
def main():
    try:
        leads = worksheet.get_all_records()
        print(f"📊 Leads Found: {len(leads)}")
    except Exception as e:
        print(f"❌ Failed to read sheet: {e}")
        return

    for idx, lead in enumerate(leads, start=2):  # starting from row 2
        name = lead.get("name")
        email = lead.get("email")
        summary = lead.get("summary") or "No summary provided"

        if email and email != "NULL":
            print(f"➡️ Processing: {name} <{email}>")
            subject, body = generate_email(name, summary)

            try:
                send_email(email, subject, body)
                worksheet.update_cell(idx, 4, "SENT")
            except Exception as e:
                print(f"❌ Failed: {e}")
                worksheet.update_cell(idx, 4, "FAILED")

# ===========================================
# 6️⃣ SINGLE LEAD FUNCTION (Optional)
# ===========================================
def send_email_to_lead(lead):
    name = lead.get("name")
    email = lead.get("email")
    summary = lead.get("summary") or "No summary provided"

    if not email or email == "NULL":
        print("⚠️ Invalid email, skipping...")
        return False

    subject, body = generate_email(name, summary)

    try:
        send_email(email, subject, body)
        print(f"✅ Sent to {email}")

        cell = worksheet.find(email)
        if cell:
            worksheet.update_cell(cell.row, 4, "SENT")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ===========================================
# 🚀 RUN SCRIPT
# ===========================================
if __name__ == "__main__":
    main()
