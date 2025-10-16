import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Page config
st.set_page_config(
    page_title="Internship Application Tracker",
    page_icon="🎯",
    layout="wide"
)

# Database connection
@st.cache_resource
def get_db_connection():
    return sqlite3.connect('internship_tracker.db', check_same_thread=False)

conn = get_db_connection()

# Title
st.title("🎯 Internship Application Tracker Dashboard")
st.markdown("---")

# Fetch statistics
def get_statistics():
    cursor = conn.cursor()

    # Total applications
    cursor.execute("SELECT COUNT(*) FROM applications")
    total_sent = cursor.fetchone()[0]

    # Responses
    cursor.execute("SELECT COUNT(*) FROM applications WHERE response_received = 1")
    responses = cursor.fetchone()[0]

    # Pending
    pending = total_sent - responses

    # Follow-ups needed
    cursor.execute("""
        SELECT COUNT(*) FROM applications 
        WHERE response_received = 0 AND next_follow_up_date <= ?
    """, (datetime.now(),))
    followups_needed = cursor.fetchone()[0]

    # Companies contacted
    cursor.execute("SELECT COUNT(DISTINCT company_id) FROM applications")
    companies = cursor.fetchone()[0]

    response_rate = (responses / total_sent * 100) if total_sent > 0 else 0

    return {
        'total': total_sent,
        'responses': responses,
        'pending': pending,
        'followups': followups_needed,
        'companies': companies,
        'response_rate': response_rate
    }

# Display KPIs
stats = get_statistics()

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("📧 Total Sent", stats['total'])

with col2:
    st.metric("✅ Responses", stats['responses'])

with col3:
    st.metric("⏳ Pending", stats['pending'])

with col4:
    st.metric("🔔 Follow-ups", stats['followups'],
              delta=f"{stats['followups']} urgent" if stats['followups'] > 0 else "None")

with col5:
    st.metric("📈 Response Rate", f"{stats['response_rate']:.1f}%")

st.markdown("---")

# Charts section
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Application Status Distribution")

    # Pie chart
    fig_pie = go.Figure(data=[go.Pie(
        labels=['Responses Received', 'Pending Responses'],
        values=[stats['responses'], stats['pending']],
        hole=0.4,
        marker_colors=['#00D9FF', '#FF6B6B']
    )])
    fig_pie.update_layout(height=300)
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("📅 Applications Timeline (Last 30 Days)")

    # Get timeline data
    query = """
        SELECT DATE(sent_at) as date, COUNT(*) as count
        FROM applications
        WHERE sent_at >= date('now', '-30 days')
        GROUP BY DATE(sent_at)
        ORDER BY date
    """
    df_timeline = pd.read_sql_query(query, conn)

    if not df_timeline.empty:
        fig_timeline = px.line(df_timeline, x='date', y='count',
                               markers=True, line_shape='spline')
        fig_timeline.update_layout(height=300, xaxis_title="Date", yaxis_title="Applications Sent")
        st.plotly_chart(fig_timeline, use_container_width=True)
    else:
        st.info("No data available for the last 30 days")

st.markdown("---")

# Companies needing follow-up
st.subheader("🔔 Companies Needing Follow-up")

query_followup = """
    SELECT c.company_name, c.email, c.contact_name, a.sent_at, a.follow_up_count,
           CAST((julianday('now') - julianday(a.sent_at)) AS INTEGER) as days_ago
    FROM companies c
    JOIN applications a ON c.id = a.company_id
    WHERE a.response_received = 0 AND a.next_follow_up_date <= datetime('now')
    ORDER BY a.sent_at ASC
"""
df_followup = pd.read_sql_query(query_followup, conn)

if not df_followup.empty:
    st.dataframe(df_followup, use_container_width=True)

    if st.button("📧 Send Follow-up Reminders"):
        st.success(f"✅ Follow-up reminders scheduled for {len(df_followup)} companies!")
else:
    st.success("✅ No follow-ups needed today!")

st.markdown("---")

# Recent applications
st.subheader("📋 Recent Applications")

query_recent = """
    SELECT c.company_name, c.email, a.subject, a.sent_at, 
           CASE WHEN a.response_received = 1 THEN '✅ Responded' ELSE '⏳ Pending' END as status
    FROM applications a
    JOIN companies c ON a.company_id = c.id
    ORDER BY a.sent_at DESC
    LIMIT 10
"""
df_recent = pd.read_sql_query(query_recent, conn)

if not df_recent.empty:
    st.dataframe(df_recent, use_container_width=True)

st.markdown("---")

# Job posts section
st.subheader("🎯 New Job Opportunities")

query_jobs = """
    SELECT title, company_name, location, url, posted_date, applied
    FROM job_posts
    WHERE applied = 0
    ORDER BY scraped_at DESC
    LIMIT 5
"""
df_jobs = pd.read_sql_query(query_jobs, conn)

if not df_jobs.empty:
    for idx, row in df_jobs.iterrows():
        with st.expander(f"📌 {row['title']} - {row['company_name']}"):
            st.write(f"**Location:** {row['location']}")
            st.write(f"**Link:** {row['url']}")
            if st.button(f"Mark as Applied", key=f"apply_{idx}"):
                cursor = conn.cursor()
                cursor.execute("UPDATE job_posts SET applied = 1 WHERE url = ?", (row['url'],))
                conn.commit()
                st.success("✅ Marked as applied!")
                st.rerun()
else:
    st.info("No new job opportunities found. Scraper will check again soon!")

st.markdown("---")

# Top performers
st.subheader("🏆 Top Responding Companies")

query_top = """
    SELECT c.company_name, c.field, 
           CAST((julianday(a.response_date) - julianday(a.sent_at)) AS INTEGER) as response_days
    FROM companies c
    JOIN applications a ON c.id = a.company_id
    WHERE a.response_received = 1
    ORDER BY response_days ASC
    LIMIT 5
"""
df_top = pd.read_sql_query(query_top, conn)

if not df_top.empty:
    st.dataframe(df_top, use_container_width=True)
else:
    st.info("No responses yet. Keep applying!")

# Sidebar - Quick Actions
with st.sidebar:
    st.header("⚡ Quick Actions")

    st.subheader("➕ Add New Company")
    with st.form("add_company"):
        company_name = st.text_input("Company Name")
        email = st.text_input("Email")
        contact_name = st.text_input("Contact Name (optional)")
        field = st.text_input("Field")
        priority = st.slider("Priority", 1, 5, 3)

        if st.form_submit_button("Add Company"):
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO companies (company_name, email, contact_name, field, priority)
                    VALUES (?, ?, ?, ?, ?)
                """, (company_name, email, contact_name, field, priority))
                conn.commit()
                st.success(f"✅ {company_name} added!")
            except sqlite3.IntegrityError:
                st.error("Company already exists!")

    st.markdown("---")

    st.subheader("📊 Export Data")
    if st.button("Download CSV Report"):
        df_export = pd.read_sql_query("SELECT * FROM applications", conn)
        csv = df_export.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"internship_report_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    st.markdown("---")
    st.info("💡 **Tip:** Check this dashboard daily to stay on top of your applications!")