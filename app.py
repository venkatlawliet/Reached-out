import csv
import json
import os
import re
import smtplib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

contacts = []
session_count = 0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COUNT_FILE = os.path.join(BASE_DIR, "count.json")
TEMPLATE_FILE = os.path.join(BASE_DIR, "template.json")
CSV_FILE = os.path.join(BASE_DIR, "contacts.csv")

EASTERN = ZoneInfo("America/New_York")


def log_to_csv(name, company, email, status):
    try:
        file_exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Name", "Company", "Email", "Status", "Date", "Time"])
            now = datetime.now(EASTERN)
            date_str = now.strftime("%b ") + str(now.day)
            time_str = now.strftime("%I:%M %p").lstrip("0").lower()
            writer.writerow([name, company, email, status, date_str, time_str])
    except Exception:
        pass  # Never let CSV logging crash the send flow


def load_total_count():
    try:
        with open(COUNT_FILE, "r") as f:
            return json.load(f).get("total", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def save_total_count(total):
    with open(COUNT_FILE, "w") as f:
        json.dump({"total": total}, f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    return jsonify(contacts)


@app.route("/api/contacts", methods=["POST"])
def add_contact():
    data = request.get_json()
    name = data.get("name", "").strip()
    company = data.get("company", "").strip()
    emails_raw = data.get("emails", [])

    if not name or not company:
        return jsonify({"error": "Name and company are required"}), 400

    emails = list(dict.fromkeys(e.strip() for e in emails_raw if e.strip()))
    if not emails:
        return jsonify({"error": "At least one email is required"}), 400

    for e in emails:
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', e):
            return jsonify({"error": f"Invalid email address: {e}"}), 400

    existing_emails = {e.lower() for c in contacts for e in c["emails"]}
    for e in emails:
        if e.lower() in existing_emails:
            return jsonify({"error": f"Email already added: {e}"}), 400

    x = data.get("x", "").strip()
    contact = {"id": str(uuid.uuid4()), "name": name, "company": company, "emails": emails, "x": x, "sent": False}
    contacts.append(contact)
    return jsonify(contact), 201


@app.route("/api/contacts/<contact_id>", methods=["PUT"])
def edit_contact(contact_id):
    contact = next((c for c in contacts if c["id"] == contact_id), None)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    if contact.get("sent") or contact.get("failed"):
        return jsonify({"error": "Cannot edit a contact that has already been sent or failed"}), 400

    data = request.get_json()
    name = data.get("name", "").strip()
    company = data.get("company", "").strip()
    emails_raw = data.get("emails", [])

    if not name or not company:
        return jsonify({"error": "Name and company are required"}), 400

    emails = list(dict.fromkeys(e.strip() for e in emails_raw if e.strip()))
    if not emails:
        return jsonify({"error": "At least one email is required"}), 400

    for e in emails:
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', e):
            return jsonify({"error": f"Invalid email address: {e}"}), 400

    existing_emails = {e.lower() for c in contacts if c["id"] != contact_id for e in c["emails"]}
    for e in emails:
        if e.lower() in existing_emails:
            return jsonify({"error": f"Email already added to another contact: {e}"}), 400

    x = data.get("x", "").strip()
    contact["name"] = name
    contact["company"] = company
    contact["emails"] = emails
    contact["x"] = x
    return jsonify(contact)


@app.route("/api/contacts", methods=["DELETE"])
def delete_contacts():
    contacts.clear()
    return jsonify({"message": "All contacts deleted"})


@app.route("/api/counts", methods=["GET"])
def get_counts():
    total = load_total_count()
    return jsonify({"session": session_count, "total": total})


@app.route("/api/template", methods=["GET"])
def get_template():
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"subject": "", "body": ""})


@app.route("/api/template", methods=["PUT"])
def save_template():
    data = request.get_json()
    template = {
        "subject": data.get("subject", ""),
        "body": data.get("body", "")
    }
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False)
    return jsonify({"message": "Template saved"})


@app.route("/api/config-status", methods=["GET"])
def config_status():
    gmail_address = os.getenv("COLD_EMAIL_MAIL", "")
    gmail_password = os.getenv("COLD_EMAIL_APP_PASSWORD", "")
    configured = (
        bool(gmail_address)
        and bool(gmail_password)
        and gmail_address != "your_email@gmail.com"
        and gmail_password != "your_app_password_here"
    )
    return jsonify({"configured": configured})


@app.route("/api/send", methods=["POST"])
def send_emails():
    global session_count

    gmail_address = os.getenv("COLD_EMAIL_MAIL", "")
    gmail_password = os.getenv("COLD_EMAIL_APP_PASSWORD", "")

    if (
        not gmail_address
        or not gmail_password
        or gmail_address == "your_email@gmail.com"
        or gmail_password == "your_app_password_here"
    ):
        return jsonify({
            "error": "Gmail credentials not configured. Please edit the .env file with your Gmail address and App Password, then restart the app."
        }), 400

    if not contacts:
        return jsonify({"error": "No contacts to send to"}), 400

    unsent = [c for c in contacts if not c.get("sent") and not c.get("failed")]
    if not unsent:
        return jsonify({"error": "All contacts have already been sent or marked as failed. Delete the list and add fresh contacts."}), 400

    data = request.get_json()
    subject_template = data.get("subject", "")
    body_template = data.get("body", "")

    if not subject_template or not body_template:
        return jsonify({"error": "Subject and body are required"}), 400

    results = []
    total = load_total_count()

    server = None
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_address, gmail_password)
    except Exception as e:
        return jsonify({"error": f"Failed to connect to Gmail: {str(e)}"}), 500

    for contact in unsent:
        # Use lambda to avoid backslash issues in names/companies
        subject = re.sub(r'\[name\]', lambda m: contact["name"], subject_template, flags=re.IGNORECASE)
        subject = re.sub(r'\[company\]', lambda m: contact["company"], subject, flags=re.IGNORECASE)
        body = re.sub(r'\[name\]', lambda m: contact["name"], body_template, flags=re.IGNORECASE)
        body = re.sub(r'\[company\]', lambda m: contact["company"], body, flags=re.IGNORECASE)

        # Handle [X] — replace if provided, remove the sentence if not
        x_value = contact.get("x", "")
        if x_value:
            subject = re.sub(r'\[X\]', lambda m: x_value, subject, flags=re.IGNORECASE)
            body = re.sub(r'\[X\]', lambda m: x_value, body, flags=re.IGNORECASE)
        else:
            # Remove any sentence containing [X] (text up to and including the period+space)
            subject = re.sub(r'[^.\n]*\[X\][^.\n]*\.\s*', '', subject, flags=re.IGNORECASE)
            body = re.sub(r'[^.\n]*\[X\][^.\n]*\.\s*', '', body, flags=re.IGNORECASE)

        # Clean up any leftover [X] that the sentence-removal regex didn't catch
        # (e.g. sentence without a trailing period)
        subject = re.sub(r'\[X\]', '', subject, flags=re.IGNORECASE).strip()
        body = re.sub(r'\[X\]', '', body, flags=re.IGNORECASE).strip()
        # Collapse any double-spaces or double-newlines left behind
        subject = re.sub(r'  +', ' ', subject)
        body = re.sub(r'\n{3,}', '\n\n', body)

        # Safety check: don't send if placeholders are still present
        if re.search(r'\[name\]', subject, re.IGNORECASE) or re.search(r'\[name\]', body, re.IGNORECASE):
            contact["failed"] = True
            results.append({"id": contact["id"], "status": "error", "error": "Placeholder [name] was not replaced"})
            continue
        if re.search(r'\[company\]', subject, re.IGNORECASE) or re.search(r'\[company\]', body, re.IGNORECASE):
            contact["failed"] = True
            results.append({"id": contact["id"], "status": "error", "error": "Placeholder [company] was not replaced"})
            continue

        recipient_list = contact["emails"]
        sent_ok = False
        try:
            # Reconnect if connection was lost
            try:
                server.noop()
            except Exception:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                server.login(gmail_address, gmail_password)

            msg = MIMEMultipart()
            msg["From"] = gmail_address
            msg["To"] = ", ".join(recipient_list)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            server.sendmail(gmail_address, recipient_list, msg.as_string())
            sent_ok = True
        except Exception as e:
            contact["failed"] = True
            results.append({"id": contact["id"], "status": "error", "error": str(e)})
            log_to_csv(contact["name"], contact["company"], " | ".join(recipient_list), "Failed")

        if sent_ok:
            contact["sent"] = True
            session_count += 1
            total += 1
            results.append({"id": contact["id"], "status": "sent"})
            log_to_csv(contact["name"], contact["company"], " | ".join(recipient_list), "Sent")

    try:
        if server:
            server.quit()
    except Exception:
        pass

    save_total_count(total)

    # Clear successfully sent contacts, keep failed ones for review
    contacts[:] = [c for c in contacts if c.get("failed")]

    return jsonify({
        "results": results,
        "counts": {"session": session_count, "total": total}
    })


if __name__ == "__main__":
    app.run(debug=False, port=5000)
