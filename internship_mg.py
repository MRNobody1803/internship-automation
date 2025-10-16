import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()


# ==================== DATABASE CONNECTION ====================
class InternshipDB:
    def __init__(self):
        # PostgreSQL connection parameters
        self.host = os.getenv("DB_HOST")
        self.port = os.getenv("DB_PORT")
        self.database = os.getenv("DB_NAME")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")

        self.conn = None
        self.connect()
        self.create_tables()

    def connect(self):
        """Establish PostgreSQL connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            print("✅ Connected to PostgreSQL")
        except psycopg2.Error as e:
            print(f"❌ Connection error: {e}")
            raise

    def create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()

        try:
            # Companies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    contact_name VARCHAR(255),
                    website VARCHAR(255),
                    field VARCHAR(255),
                    priority INTEGER DEFAULT 3 CHECK (priority >= 1 AND priority <= 5),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Applications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    subject VARCHAR(255),
                    email_body TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'Sent',
                    response_received BOOLEAN DEFAULT FALSE,
                    response_date TIMESTAMP,
                    follow_up_count INTEGER DEFAULT 0,
                    next_follow_up_date TIMESTAMP,
                    ai_reviewed BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                )
            """)

            # Responses table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id SERIAL PRIMARY KEY,
                    application_id INTEGER NOT NULL,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    subject VARCHAR(255),
                    body TEXT,
                    sentiment VARCHAR(50),
                    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
                )
            """)

            # Job posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255),
                    company_name VARCHAR(255),
                    location VARCHAR(255),
                    description TEXT,
                    url VARCHAR(255) UNIQUE,
                    posted_date DATE,
                    source VARCHAR(100),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    applied BOOLEAN DEFAULT FALSE
                )
            """)

            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_email ON companies(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_company_id ON applications(company_id)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_applications_response_received ON applications(response_received)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_posts_url ON job_posts(url)")

            self.conn.commit()
            print("✅ Tables created successfully")
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error creating tables: {e}")
            raise
        finally:
            cursor.close()

    # ==================== COMPANY OPERATIONS ====================

    def add_company(self, company_name, email, contact_name=None, website=None, field=None, priority=3):
        """Add a new company"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO companies (company_name, email, contact_name, website, field, priority)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (company_name, email, contact_name, website, field, priority))

            company_id = cursor.fetchone()[0]
            self.conn.commit()
            print(f"✅ Company added with ID: {company_id}")
            return company_id
        except psycopg2.errors.UniqueViolation:
            self.conn.rollback()
            print(f"⚠️ Company with email {email} already exists")
            return None
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error adding company: {e}")
            return None
        finally:
            cursor.close()

    def get_all_companies(self):
        """Get all companies"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT * FROM companies ORDER BY priority ASC, created_at DESC")
            columns = [desc[0] for desc in cursor.description]
            companies = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return companies
        finally:
            cursor.close()

    # ==================== APPLICATION OPERATIONS ====================

    def log_application(self, company_id, subject, email_body, ai_reviewed=False):
        """Log an application sent"""
        cursor = self.conn.cursor()
        try:
            next_followup = datetime.now() + timedelta(days=7)
            cursor.execute("""
                INSERT INTO applications (company_id, subject, email_body, next_follow_up_date, ai_reviewed)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (company_id, subject, email_body, next_followup, ai_reviewed))

            app_id = cursor.fetchone()[0]
            self.conn.commit()
            return app_id
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error logging application: {e}")
            return None
        finally:
            cursor.close()

    def get_companies_needing_followup(self):
        """Get companies needing follow-up"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT c.id, c.company_name, c.email, c.contact_name, 
                       a.sent_at, a.follow_up_count,
                       EXTRACT(DAY FROM (NOW() - a.sent_at)) as days_ago
                FROM companies c
                JOIN applications a ON c.id = a.company_id
                WHERE a.response_received = FALSE 
                AND a.next_follow_up_date <= NOW()
                AND a.follow_up_count < 3
                ORDER BY c.priority ASC, a.sent_at ASC
            """)

            columns = [desc[0] for desc in cursor.description]
            companies = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return companies
        finally:
            cursor.close()

    def mark_response_received(self, application_id, response_body, sentiment="Neutral"):
        """Mark application as responded"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                UPDATE applications 
                SET response_received = TRUE, response_date = NOW()
                WHERE id = %s
            """, (application_id,))

            cursor.execute("""
                INSERT INTO responses (application_id, body, sentiment)
                VALUES (%s, %s, %s)
            """, (application_id, response_body, sentiment))

            self.conn.commit()
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error marking response: {e}")
        finally:
            cursor.close()

    def update_follow_up(self, application_id):
        """Update follow-up count and date"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                UPDATE applications 
                SET follow_up_count = follow_up_count + 1,
                    next_follow_up_date = NOW() + INTERVAL '7 days'
                WHERE id = %s
            """, (application_id,))

            self.conn.commit()
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error updating follow-up: {e}")
        finally:
            cursor.close()

    # ==================== STATISTICS ====================

    def get_statistics(self):
        """Get comprehensive statistics"""
        cursor = self.conn.cursor()
        try:
            # Total sent
            cursor.execute("SELECT COUNT(*) FROM applications")
            total_sent = cursor.fetchone()[0]

            # Responses
            cursor.execute("SELECT COUNT(*) FROM applications WHERE response_received = TRUE")
            responses = cursor.fetchone()[0]

            # Companies contacted
            cursor.execute("SELECT COUNT(DISTINCT company_id) FROM applications")
            companies_contacted = cursor.fetchone()[0]

            # Follow-ups needed
            cursor.execute("""
                SELECT COUNT(*) FROM applications 
                WHERE response_received = FALSE AND next_follow_up_date <= NOW()
            """)
            followups_needed = cursor.fetchone()[0]

            # Positive responses
            cursor.execute("""
                SELECT COUNT(*) FROM responses WHERE sentiment = 'Positive'
            """)
            positive = cursor.fetchone()[0]

            pending = total_sent - responses
            response_rate = (responses / total_sent * 100) if total_sent > 0 else 0

            return {
                "total_sent": total_sent,
                "responses": responses,
                "positive": positive,
                "pending": pending,
                "companies_contacted": companies_contacted,
                "followups_needed": followups_needed,
                "response_rate": round(response_rate, 2)
            }
        finally:
            cursor.close()

    # ==================== JOB POSTS ====================

    def add_job_post(self, title, company, location, description, url, source):
        """Add a job posting"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO job_posts (title, company_name, location, description, url, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
            """, (title, company, location, description, url, source))

            result = cursor.fetchone()
            self.conn.commit()
            return result[0] if result else None
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Error adding job post: {e}")
            return None
        finally:
            cursor.close()

    def get_unapplied_jobs(self, limit=10):
        """Get unapplied job posts"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM job_posts 
                WHERE applied = FALSE
                ORDER BY scraped_at DESC
                LIMIT %s
            """, (limit,))

            columns = [desc[0] for desc in cursor.description]
            jobs = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return jobs
        finally:
            cursor.close()

    # ==================== TIMELINE ANALYTICS ====================

    def get_application_timeline(self, days=30):
        """Get applications sent in last N days"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT DATE(sent_at) as date, COUNT(*) as count
                FROM applications
                WHERE sent_at >= NOW() - INTERVAL '%s days'
                GROUP BY DATE(sent_at)
                ORDER BY date DESC
            """, (days,))

            timeline = cursor.fetchall()
            return timeline
        finally:
            cursor.close()

    def get_response_time_stats(self):
        """Get average response time"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    ROUND(AVG(EXTRACT(DAY FROM (response_date - sent_at)))) as avg_days,
                    MIN(EXTRACT(DAY FROM (response_date - sent_at))) as min_days,
                    MAX(EXTRACT(DAY FROM (response_date - sent_at))) as max_days
                FROM applications
                WHERE response_received = TRUE
            """)

            result = cursor.fetchone()
            return {
                "avg_response_days": result[0] or 0,
                "min_response_days": result[1] or 0,
                "max_response_days": result[2] or 0
            }
        finally:
            cursor.close()

    # ==================== CLEANUP ====================

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("✅ Database connection closed")

    def __del__(self):
        """Destructor to ensure connection is closed"""
        self.close()


# ==================== USAGE EXAMPLE ====================
if __name__ == "__main__":
    # Initialize database
    db = InternshipDB()

    # Add a company
    company_id = db.add_company(
        company_name="TechCorp",
        email="hr@techcorp.com",
        contact_name="Sarah Johnson",
        field="Software Engineering",
        priority=1
    )

    # Log an application
    if company_id:
        app_id = db.log_application(
            company_id=company_id,
            subject="PFE Internship Application",
            email_body="Your email here...",
            ai_reviewed=True
        )
        print(f"✅ Application logged with ID: {app_id}")

    # Get statistics
    stats = db.get_statistics()
    print("\n📊 Statistics:")
    print(json.dumps(stats, indent=2))

    # Get companies needing follow-up
    followups = db.get_companies_needing_followup()
    print(f"\n🔔 Companies needing follow-up: {len(followups)}")

    # Close connection
    db.close()
