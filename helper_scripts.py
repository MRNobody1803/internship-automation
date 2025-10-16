#!/usr/bin/env python3
"""
Helper scripts for n8n workflow integration
These scripts are called by n8n nodes
"""

import sqlite3
import json
import sys
from datetime import datetime, timedelta

DB_PATH = "internship_tracker.db"

# ==================== SCRIPT 1: Check Follow-ups ====================
def check_followups():
    """
    Check which companies need follow-up
    Returns JSON for n8n
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.company_name, c.email, c.contact_name, 
               a.sent_at, a.follow_up_count,
               CAST((julianday('now') - julianday(a.sent_at)) AS INTEGER) as days_ago
        FROM companies c
        JOIN applications a ON c.id = a.company_id
        WHERE a.response_received = 0 
        AND a.next_follow_up_date <= datetime('now')
        AND a.follow_up_count < 3
        ORDER BY c.priority ASC, a.sent_at ASC
    """)

    companies = cursor.fetchall()
    conn.close()

    companies_list = []
    for comp in companies:
        companies_list.append({
            "id": comp[0],
            "name": comp[1],
            "email": comp[2],
            "contact": comp[3] or "Hiring Manager",
            "sent_date": comp[4],
            "follow_up_count": comp[5],
            "days_ago": comp[6]
        })

    result = {
        "followups_needed": len(companies_list),
        "companies": companies_list,
        "companies_list": "\n".join([
            f"• {c['name']} ({c['email']}) - {c['days_ago']} days ago"
            for c in companies_list
        ])
    }

    print(json.dumps(result))
    return result


# ==================== SCRIPT 2: Check Responses ====================
def check_responses():
    """
    Check Gmail for responses and update database
    Returns JSON for n8n
    """
    import imaplib
    import email
    from email.header import decode_header

    # Email credentials (use environment variables in production)
    EMAIL = "your_email@gmail.com"
    PASSWORD = "your_app_password"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get list of companies we've contacted
    cursor.execute("""
        SELECT c.email, a.id, a.sent_at
        FROM companies c
        JOIN applications a ON c.id = a.company_id
        WHERE a.response_received = 0
    """)
    pending_apps = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    new_responses = []

    try:
        # Connect to Gmail
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        # Search for unread emails from last 7 days
        status, messages = mail.search(None, 'UNSEEN')

        for email_id in messages[0].split()[-50:]:  # Check last 50 unread
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            sender = msg.get("From")
            subject = msg.get("Subject")

            # Extract email address from sender
            sender_email = sender.split("<")[-1].replace(">", "").strip() if "<" in sender else sender

            # Check if this is from a company we contacted
            if sender_email in pending_apps:
                app_id, sent_date = pending_apps[sender_email]

                # Get email body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                body = part.get_payload(decode=True).decode()
                            except:
                                body = "Could not decode body"
                            break
                else:
                    try:
                        body = msg.get_payload(decode=True).decode()
                    except:
                        body = "Could not decode body"

                # Analyze sentiment (simple keyword-based)
                sentiment = analyze_sentiment(subject + " " + body)

                # Update database
                cursor.execute("""
                    UPDATE applications 
                    SET response_received = 1, response_date = ?
                    WHERE id = ?
                """, (datetime.now(), app_id))

                cursor.execute("""
                    INSERT INTO responses (application_id, subject, body, sentiment)
                    VALUES (?, ?, ?, ?)
                """, (app_id, subject, body[:500], sentiment))

                new_responses.append({
                    "company_email": sender_email,
                    "subject": subject,
                    "sentiment": sentiment,
                    "application_id": app_id
                })

        conn.commit()
        mail.close()
        mail.logout()

    except Exception as e:
        print(f"Error checking emails: {e}", file=sys.stderr)

    conn.close()

    result = {
        "new_responses": len(new_responses),
        "responses": new_responses
    }

    print(json.dumps(result))
    return result


def analyze_sentiment(text):
    """
    Simple sentiment analysis
    In production, use NLP library or API
    """
    positive_keywords = ["interested", "interview", "pleased", "love", "excited",
                         "opportunity", "congratulations", "selected"]
    negative_keywords = ["unfortunately", "sorry", "not", "cannot", "unable",
                         "filled", "closed", "regret"]

    text_lower = text.lower()

    positive_count = sum(1 for word in positive_keywords if word in text_lower)
    negative_count = sum(1 for word in negative_keywords if word in text_lower)

    if positive_count > negative_count:
        return "Positive"
    elif negative_count > positive_count:
        return "Negative"
    else:
        return "Neutral"


# ==================== SCRIPT 3: Generate Report ====================
def generate_report():
    """
    Generate statistics report
    Returns formatted text for email
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Total applications
    cursor.execute("SELECT COUNT(*) FROM applications")
    total = cursor.fetchone()[0]

    # Responses
    cursor.execute("SELECT COUNT(*) FROM applications WHERE response_received = 1")
    responses = cursor.fetchone()[0]

    # Positive responses
    cursor.execute("""
        SELECT COUNT(*) FROM responses WHERE sentiment = 'Positive'
    """)
    positive = cursor.fetchone()[0]

    # Pending
    pending = total - responses

    # Follow-ups needed
    cursor.execute("""
        SELECT COUNT(*) FROM applications 
        WHERE response_received = 0 AND next_follow_up_date <= datetime('now')
    """)
    followups = cursor.fetchone()[0]

    # Companies contacted
    cursor.execute("SELECT COUNT(DISTINCT company_id) FROM applications")
    companies = cursor.fetchone()[0]

    # Recent positive responses
    cursor.execute("""
        SELECT c.company_name, r.subject, r.received_at
        FROM responses r
        JOIN applications a ON r.application_id = a.id
        JOIN companies c ON a.company_id = c.id
        WHERE r.sentiment = 'Positive'
        ORDER BY r.received_at DESC
        LIMIT 3
    """)
    recent_positive = cursor.fetchall()

    # Applications timeline (last 7 days)
    cursor.execute("""
        SELECT DATE(sent_at) as date, COUNT(*) as count
        FROM applications
        WHERE sent_at >= date('now', '-7 days')
        GROUP BY DATE(sent_at)
        ORDER BY date DESC
    """)
    timeline = cursor.fetchall()

    conn.close()

    response_rate = (responses / total * 100) if total > 0 else 0

    # Build report
    report = f"""
📊 INTERNSHIP APPLICATION REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'=' * 60}

📈 OVERALL STATISTICS
{'─' * 60}
📧 Total Applications Sent:     {total}
✅ Responses Received:          {responses}
💚 Positive Responses:          {positive}
⏳ Pending Responses:           {pending}
🔔 Follow-ups Needed:           {followups}
🏢 Companies Contacted:         {companies}
📊 Response Rate:               {response_rate:.1f}%

{'=' * 60}

🎯 PERFORMANCE INSIGHTS
{'─' * 60}
"""

    if response_rate > 25:
        report += "✅ Excellent response rate! Your emails are working well.\n"
    elif response_rate > 15:
        report += "👍 Good response rate. Keep up the momentum!\n"
    else:
        report += "⚠️  Response rate could be improved. Consider:\n"
        report += "   • Personalizing emails more\n"
        report += "   • Following up sooner\n"
        report += "   • Targeting more relevant companies\n"

    report += f"\n{'=' * 60}\n\n"

    if recent_positive:
        report += "🌟 RECENT POSITIVE RESPONSES\n"
        report += f"{'─' * 60}\n"
        for comp_name, subject, received in recent_positive:
            report += f"• {comp_name}\n"
            report += f"  Subject: {subject}\n"
            report += f"  Received: {received}\n\n"
        report += f"{'=' * 60}\n\n"

    if timeline:
        report += "📅 ACTIVITY (Last 7 Days)\n"
        report += f"{'─' * 60}\n"
        for date, count in timeline:
            report += f"{date}: {count} application{'s' if count > 1 else ''} sent\n"
        report += f"\n{'=' * 60}\n\n"

    if followups > 0:
        report += f"🔔 ACTION REQUIRED\n"
        report += f"{'─' * 60}\n"
        report += f"You have {followups} compan{'ies' if followups > 1 else 'y'} that need follow-up!\n"
        report += f"Check your dashboard or email alerts for details.\n\n"
        report += f"{'=' * 60}\n\n"

    report += """
💪 KEEP PUSHING FORWARD!
Remember: Finding an internship is a numbers game.
Every application brings you closer to success!

Best of luck,
Your Automation System 🤖
"""

    result = {"report": report}
    print(json.dumps(result))
    return result


# ==================== SCRIPT 4: Job Post Scraper ====================
def scrape_linkedin_jobs():
    """
    Scrape LinkedIn for PFE internship posts
    Returns JSON with new job posts
    """
    import requests
    from bs4 import BeautifulSoup

    # LinkedIn job search URL (adjust based on your location/field)
    url = "https://www.linkedin.com/jobs/search/?keywords=stage%20pfe%20informatique&location=Morocco"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        jobs = []
        job_cards = soup.find_all('div', class_='base-card')

        for card in job_cards[:10]:  # Get first 10 jobs
            try:
                title_elem = card.find('h3', class_='base-search-card__title')
                company_elem = card.find('h4', class_='base-search-card__subtitle')
                location_elem = card.find('span', class_='job-search-card__location')
                link_elem = card.find('a', class_='base-card__full-link')

                if title_elem and company_elem and link_elem:
                    job = {
                        "title": title_elem.text.strip(),
                        "company": company_elem.text.strip(),
                        "location": location_elem.text.strip() if location_elem else "Remote",
                        "url": link_elem['href'],
                        "source": "LinkedIn",
                        "description": ""
                    }
                    jobs.append(job)
            except Exception as e:
                continue

        # Save to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        new_jobs = []
        for job in jobs:
            try:
                cursor.execute("""
                    INSERT INTO job_posts (title, company_name, location, url, source)
                    VALUES (?, ?, ?, ?, ?)
                """, (job['title'], job['company'], job['location'], job['url'], job['source']))
                new_jobs.append(job)
            except sqlite3.IntegrityError:
                pass  # Job already exists

        conn.commit()
        conn.close()

        result = {
            "new_jobs_found": len(new_jobs),
            "jobs": new_jobs
        }

        print(json.dumps(result))
        return result

    except Exception as e:
        print(json.dumps({"error": str(e), "new_jobs_found": 0, "jobs": []}))
        return {"error": str(e), "new_jobs_found": 0, "jobs": []}


# ==================== MAIN ====================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python helper_scripts.py [check_followups|check_responses|generate_report|scrape_jobs]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "check_followups":
        check_followups()
    elif command == "check_responses":
        check_responses()
    elif command == "generate_report":
        generate_report()
    elif command == "scrape_jobs":
        scrape_linkedin_jobs()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)