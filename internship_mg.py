import sqlite3
import yagmail
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import imaplib
import email
from email.header import decode_header
import json

# ==================== DATABASE SETUP ====================
class InternshipDB:
    def __init__(self, db_path="internship_tracker.db"):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        # Companies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                contact_name TEXT,
                website TEXT,
                field TEXT,
                priority INTEGER DEFAULT 3,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Applications table (tracks each email sent)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                subject TEXT,
                email_body TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Sent',
                response_received INTEGER DEFAULT 0,
                response_date TIMESTAMP,
                follow_up_count INTEGER DEFAULT 0,
                next_follow_up_date TIMESTAMP,
                ai_reviewed INTEGER DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """)

        # Responses table (tracks replies from companies)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subject TEXT,
                body TEXT,
                sentiment TEXT,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            )
        """)

        # Job Posts table (scraped opportunities)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company_name TEXT,
                location TEXT,
                description TEXT,
                url TEXT UNIQUE,
                posted_date DATE,
                source TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied INTEGER DEFAULT 0
            )
        """)

        self.conn.commit()

    def add_company(self, company_name, email, contact_name=None, website=None, field=None, priority=3):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO companies (company_name, email, contact_name, website, field, priority)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (company_name, email, contact_name, website, field, priority))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            print(f"Company with email {email} already exists")
            return None

    def log_application(self, company_id, subject, email_body, ai_reviewed=False):
        cursor = self.conn.cursor()
        next_followup = datetime.now() + timedelta(days=7)
        cursor.execute("""
            INSERT INTO applications (company_id, subject, email_body, next_follow_up_date, ai_reviewed)
            VALUES (?, ?, ?, ?, ?)
        """, (company_id, subject, email_body, next_followup, int(ai_reviewed)))
        self.conn.commit()
        return cursor.lastrowid

    def get_companies_needing_followup(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT c.id, c.company_name, c.email, c.contact_name, a.sent_at, a.follow_up_count
            FROM companies c
            JOIN applications a ON c.id = a.company_id
            WHERE a.response_received = 0 
            AND a.next_follow_up_date <= ?
            AND a.follow_up_count < 3
            ORDER BY c.priority ASC, a.sent_at ASC
        """, (datetime.now(),))
        return cursor.fetchall()

    def mark_response_received(self, application_id, response_body, sentiment="Neutral"):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE applications 
            SET response_received = 1, response_date = ?
            WHERE id = ?
        """, (datetime.now(), application_id))

        cursor.execute("""
            INSERT INTO responses (application_id, body, sentiment)
            VALUES (?, ?, ?)
        """, (application_id, response_body, sentiment))
        self.conn.commit()

    def get_statistics(self):
        cursor = self.conn.cursor()

        # Total applications
        cursor.execute("SELECT COUNT(*) FROM applications")
        total_sent = cursor.fetchone()[0]

        # Responses received
        cursor.execute("SELECT COUNT(*) FROM applications WHERE response_received = 1")
        responses = cursor.fetchone()[0]

        # Pending responses
        pending = total_sent - responses

        # Companies contacted
        cursor.execute("SELECT COUNT(DISTINCT company_id) FROM applications")
        companies_contacted = cursor.fetchone()[0]

        # Follow-ups needed
        cursor.execute("""
            SELECT COUNT(*) FROM applications 
            WHERE response_received = 0 AND next_follow_up_date <= ?
        """, (datetime.now(),))
        followups_needed = cursor.fetchone()[0]

        return {
            "total_sent": total_sent,
            "responses": responses,
            "pending": pending,
            "companies_contacted": companies_contacted,
            "followups_needed": followups_needed,
            "response_rate": round((responses / total_sent * 100) if total_sent > 0 else 0, 2)
        }

    def add_job_post(self, title, company, location, description, url, source):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO job_posts (title, company_name, location, description, url, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, company, location, description, url, source))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None  # Already exists


# ==================== EMAIL HANDLER ====================
class EmailManager:
    def __init__(self, email_address, password):
        self.email = email_address
        self.password = password
        self.yag = yagmail.SMTP(email_address, password)

    def send_application(self, to_email, contact_name, subject, body):
        """Send application email"""
        try:
            personalized_body = body.format(contact_name=contact_name or "Hiring Manager")
            self.yag.send(to=to_email, subject=subject, contents=personalized_body)
            return True
        except Exception as e:
            print(f"Error sending email to {to_email}: {e}")
            return False

    def check_responses(self, imap_server="imap.gmail.com"):
        """Check inbox for responses from companies"""
        responses = []
        try:
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(self.email, self.password)
            mail.select("inbox")

            # Search for unread emails from last 7 days
            status, messages = mail.search(None, 'UNSEEN')
            email_ids = messages[0].split()

            for email_id in email_ids[-50:]:  # Check last 50 unread
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                sender = msg.get("From")
                subject = msg.get("Subject")

                # Get email body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()

                responses.append({
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_at": datetime.now()
                })

            mail.close()
            mail.logout()

        except Exception as e:
            print(f"Error checking emails: {e}")

        return responses


# ==================== AI EMAIL REVIEWER (Placeholder) ====================
def ai_review_email(email_content):
    """
    TODO: Integrate with OpenAI API or local LLM
    Reviews email for:
    - Grammar errors
    - Professionalism
    - Missing information
    - Tone appropriateness
    """
    # Placeholder: In production, call OpenAI API
    suggestions = []

    if len(email_content) < 100:
        suggestions.append("Email is too short. Add more details about your skills.")

    if "CV" not in email_content and "resume" not in email_content.lower():
        suggestions.append("Consider mentioning your CV or resume.")

    if "thank you" not in email_content.lower():
        suggestions.append("Add a thank you statement for professionalism.")

    return {
        "approved": len(suggestions) == 0,
        "suggestions": suggestions,
        "score": max(0, 100 - len(suggestions) * 20)
    }


# ==================== REPORT GENERATOR ====================
def generate_report(db: InternshipDB):
    """Generate and send report every 3 days"""
    stats = db.get_statistics()

    report = f"""
    📊 INTERNSHIP APPLICATION REPORT - {datetime.now().strftime('%Y-%m-%d')}
    ================================================
    
    📧 Total Applications Sent: {stats['total_sent']}
    ✅ Responses Received: {stats['responses']}
    ⏳ Pending Responses: {stats['pending']}
    🏢 Companies Contacted: {stats['companies_contacted']}
    🔔 Follow-ups Needed: {stats['followups_needed']}
    📈 Response Rate: {stats['response_rate']}%
    
    ================================================
    
    🚀 Next Steps:
    - {'✅ Great response rate! Keep going!' if stats['response_rate'] > 20 else '⚠️ Consider improving your email template'}
    - {f'🔔 {stats["followups_needed"]} companies need follow-up!' if stats['followups_needed'] > 0 else '✅ No follow-ups needed today'}
    
    Keep pushing forward! 💪
    """

    return report


# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    # Initialize
    db = InternshipDB()
    email_mgr = EmailManager("your_email@gmail.com", "your_app_password")

    # Example: Add a company
    company_id = db.add_company(
        company_name="TechCorp",
        email="hr@techcorp.com",
        contact_name="Sarah Johnson",
        field="Software Engineering",
        priority=1
    )

    # Example: Send application with AI review
    email_template = """
    Hi {contact_name},
    
    I'm Abdessamad, a 4th-year Computer Engineering student at [Your University].
    I'm very interested in applying for a PFE internship at your company.
    
    I have experience in [mention skills] and would love to contribute to your team.
    
    Please find my CV here: [Link]
    
    Thank you for considering my application.
    
    Best regards,
    Abdessamad
    """

    # AI Review
    review = ai_review_email(email_template)
    if not review['approved']:
        print("⚠️ AI Suggestions:", review['suggestions'])

    # Send and log
    if company_id and email_mgr.send_application(
            to_email="hr@techcorp.com",
            contact_name="Sarah Johnson",
            subject="PFE Internship Application - Computer Engineering Student",
            body=email_template
    ):
        db.log_application(company_id, "PFE Internship Application", email_template, ai_reviewed=True)
        print("✅ Application sent and logged!")

    # Generate report
    print(generate_report(db))