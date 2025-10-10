import base64

# Decode Google Key from Render ENV
service_account_base64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
if service_account_base64:
    with open("serviceaccount.json", "wb") as f:
        f.write(base64.b64decode(service_account_base64))


import os
import json
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
from openai import OpenAI
from google.oauth2.service_account import Credentials
import gspread

# =======================
# 1. Setup
# =======================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))

# Gmail credentials
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

SERVICE_ACCOUNT_FILE = "serviceaccount.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)

# Open Google Sheet
sheet_name = "lead spreadsheet"
worksheet = gc.open(sheet_name).sheet1

# =======================
# 2. Generate Email
# =======================
def generate_email(name, summary):
    prompt = f"""
    Write a professional marketing email for Technosurge, an AI agency that offers automation and voice AI services.
    The lead's name is {name if name else "there"}.
    Their interest summary is: "{summary}".
    
    Guidelines:
    - Friendly and professional tone
    - Mention their specific interest from the summary
    - Suggest booking a free demo or consultation
    - Keep email under 200 words
    - Return only subject and body in JSON format:
      {{"subject": "subject line", "body": "email body"}}
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
            f"Hi {name},\n\nI’d love to show you how Technosurge can help with automation and AI solutions. Would you like to schedule a free demo?\n\nBest regards,\nTechnosurge Team"
        )

# =======================
# 3. Send Email
# =======================
def send_email(to_email, subject, body):
    msg = MIMEText(body, "plain")
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = to_email

    print(f"📧 Attempting to send email to: {to_email}")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        print(f"✅ Email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {str(e)}")

# =======================
# 4. Main Logic
# =======================
def main():
    leads = worksheet.get_all_records()
    print(f"📊 Leads fetched from sheet: {len(leads)}")

    for idx, lead in enumerate(leads, start=2):  # row 2 onwards (row 1 = headers)
        name = lead.get("name")
        email = lead.get("email")
        summary = lead.get("summary") or "No summary provided"

        if email and email != "NULL":
            print(f"➡️ Processing lead: {name} - {email}")
            subject, body = generate_email(name, summary)

            try:
                send_email(email, subject, body)
                worksheet.update_cell(idx, 4, "Email Sent")  # update status col
            except Exception as e:
                print(f"❌ Failed to send email to {email}: {e}")

def send_email_to_lead(lead):
    """
    Send email to a single lead.
    Expects lead = {"name": str, "email": str, "summary": str}
    """
    name = lead.get("name")
    email = lead.get("email")
    summary = lead.get("summary") or "No summary provided"

    if not email or email == "NULL":
        print("⚠️ No valid email for this lead, skipping.")
        return False

    subject, body = generate_email(name, summary)

    try:
        send_email(email, subject, body)
        print(f"✅ Email sent to {email}")
        
        # ✅ Update Google Sheet with SENT
        cell = worksheet.find(email)
        if cell:
            worksheet.update_cell(cell.row, 4, "SENT")  # assuming 'status' is 4th column
            print(f"📊 Status updated for {email} → SENT")

        return True

    except Exception as e:
        print(f"❌ Failed to send email to {email}: {e}")

        # ✅ Update Google Sheet with FAILED
        try:
            cell = worksheet.find(email)
            if cell:
                worksheet.update_cell(cell.row, 4, "FAILED")
                print(f"📊 Status updated for {email} → FAILED")
        except Exception as e2:
            print(f"⚠️ Could not update FAILED status for {email}: {e2}")

        return False


if __name__ == "__main__":
    main()

