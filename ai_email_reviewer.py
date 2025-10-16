import openai
import os
from typing import Dict, List
import json

# ==================== OPENAI EMAIL REVIEWER ====================
class AIEmailReviewer:
    """
    AI-powered email reviewer using OpenAI GPT
    Reviews emails for grammar, tone, completeness, and professionalism
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        openai.api_key = self.api_key

    def review_email(self, email_content: str, company_name: str = "",
                     recipient_name: str = "", job_title: str = "") -> Dict:
        """
        Review an internship application email

        Args:
            email_content: The email body to review
            company_name: Target company name
            recipient_name: Recipient's name
            job_title: Job title applying for

        Returns:
            Dictionary with review results, suggestions, and score
        """

        prompt = f"""
You are an expert career coach reviewing an internship application email.

**Email Details:**
- Company: {company_name or 'Not specified'}
- Recipient: {recipient_name or 'Not specified'}
- Position: {job_title or 'PFE Internship'}

**Email to Review:**
{email_content}

**Please analyze this email and provide:**

1. **Overall Score** (0-100): Rate the email's effectiveness
2. **Strengths**: What works well (2-3 points)
3. **Weaknesses**: What needs improvement (2-3 points)
4. **Critical Issues**: Grammar errors, missing information, tone problems
5. **Specific Suggestions**: Actionable improvements with examples
6. **Revised Subject Line**: A better subject line if needed
7. **Approval**: YES/NO - Is this email ready to send?

**Evaluation Criteria:**
- Grammar and spelling
- Professional tone
- Clear value proposition
- Proper structure (greeting, body, closing)
- Personalization
- Call to action
- Length (not too short, not too long)
- Enthusiasm without desperation

**Format your response as JSON:**
{{
    "score": 85,
    "approved": true,
    "strengths": ["point 1", "point 2"],
    "weaknesses": ["point 1", "point 2"],
    "critical_issues": ["issue 1", "issue 2"],
    "suggestions": [
        {{"issue": "...", "fix": "...", "example": "..."}},
        {{"issue": "...", "fix": "...", "example": "..."}}
    ],
    "revised_subject": "...",
    "summary": "Brief overall assessment"
}}
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",  # or "gpt-3.5-turbo" for cheaper option
                messages=[
                    {"role": "system", "content": "You are a professional career coach specializing in internship applications."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            print(f"Error during AI review: {e}")
            return self._fallback_review(email_content)

    def improve_email(self, email_content: str, company_name: str = "",
                      recipient_name: str = "", job_title: str = "") -> str:
        """
        Generate an improved version of the email
        """

        prompt = f"""
Rewrite this internship application email to make it more professional and effective.

**Original Email:**
{email_content}

**Context:**
- Company: {company_name or 'Technology Company'}
- Recipient: {recipient_name or 'Hiring Manager'}
- Position: {job_title or 'PFE Internship'}

**Requirements:**
1. Keep it concise (150-200 words)
2. Professional but warm tone
3. Clear value proposition
4. Specific skills/achievements
5. Strong call to action
6. Proper structure

**Provide the improved email only, no explanations.**
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert at writing professional internship application emails."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"Error improving email: {e}")
            return email_content

    def generate_email(self, company_name: str, recipient_name: str,
                       job_title: str, your_skills: List[str],
                       your_name: str = "Abdessamad") -> str:
        """
        Generate a complete email from scratch
        """

        skills_text = ", ".join(your_skills)

        prompt = f"""
Write a professional internship application email.

**Details:**
- Applicant: {your_name}, 4th-year Computer Engineering student
- Company: {company_name}
- Recipient: {recipient_name}
- Position: {job_title}
- Key Skills: {skills_text}

**Requirements:**
1. Professional subject line
2. Personalized greeting
3. Brief introduction
4. Why interested in THIS company
5. Relevant skills/experience
6. Call to action
7. Professional closing

**Format:**
SUBJECT: [Your subject line]

[Email body]
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert at writing compelling internship application emails."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=600
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"Error generating email: {e}")
            return self._template_email(company_name, recipient_name, job_title)

    def _fallback_review(self, email_content: str) -> Dict:
        """
        Simple rule-based review if API fails
        """
        issues = []
        score = 100

        # Check length
        word_count = len(email_content.split())
        if word_count < 50:
            issues.append("Email is too short (less than 50 words)")
            score -= 20
        elif word_count > 300:
            issues.append("Email is too long (over 300 words)")
            score -= 10

        # Check for key elements
        if "cv" not in email_content.lower() and "resume" not in email_content.lower():
            issues.append("No mention of CV/resume")
            score -= 15

        if "thank" not in email_content.lower():
            issues.append("No thank you statement")
            score -= 10

        if not any(word in email_content.lower() for word in ["interested", "excited", "passionate"]):
            issues.append("Lacks enthusiasm")
            score -= 15

        return {
            "score": max(0, score),
            "approved": score >= 70,
            "strengths": ["Email structure is present"],
            "weaknesses": issues,
            "critical_issues": issues,
            "suggestions": [{"issue": issue, "fix": "Add this element", "example": ""} for issue in issues],
            "revised_subject": "PFE Internship Application - Computer Engineering Student",
            "summary": f"Rule-based review score: {score}/100"
        }

    def _template_email(self, company_name: str, recipient_name: str, job_title: str) -> str:
        """
        Fallback email template
        """
        return f"""SUBJECT: Application for {job_title} - Computer Engineering Student

Dear {recipient_name or 'Hiring Manager'},

I am writing to express my strong interest in the {job_title} position at {company_name}. As a fourth-year Computer Engineering student, I am eager to apply my technical skills and contribute to your team.

Throughout my studies, I have developed proficiency in software development, database management, and system architecture. I am particularly drawn to {company_name} because of your innovative approach to technology solutions.

I have attached my CV for your review and would welcome the opportunity to discuss how my background aligns with your team's needs.

Thank you for considering my application. I look forward to hearing from you.

Best regards,
Abdessamad
"""


# ==================== USAGE EXAMPLE ====================
if __name__ == "__main__":
    # Initialize reviewer (requires OPENAI_API_KEY environment variable)
    reviewer = AIEmailReviewer(api_key="your_openai_api_key_here")

    # Example email to review
    sample_email = """
    Hi there,
    
    I want to apply for internship at your company. I am student in computer engineering.
    Please see my CV.
    
    Thanks
    Abdessamad
    """

    # Review the email
    print("=" * 50)
    print("AI EMAIL REVIEW")
    print("=" * 50)

    review_result = reviewer.review_email(
        email_content=sample_email,
        company_name="TechCorp",
        recipient_name="Sarah Johnson",
        job_title="Software Engineering Intern"
    )

    print(f"\n📊 Score: {review_result['score']}/100")
    print(f"✅ Approved: {'YES' if review_result['approved'] else 'NO'}")

    print("\n💪 Strengths:")
    for strength in review_result['strengths']:
        print(f"  • {strength}")

    print("\n⚠️ Weaknesses:")
    for weakness in review_result['weaknesses']:
        print(f"  • {weakness}")

    print("\n🔍 Suggestions:")
    for suggestion in review_result['suggestions']:
        print(f"  Issue: {suggestion['issue']}")
        print(f"  Fix: {suggestion['fix']}")
        if suggestion.get('example'):
            print(f"  Example: {suggestion['example']}")
        print()

    print(f"\n📝 Suggested Subject: {review_result['revised_subject']}")
    print(f"\n💬 Summary: {review_result['summary']}")

    # If not approved, generate improved version
    if not review_result['approved']:
        print("\n" + "=" * 50)
        print("IMPROVED VERSION")
        print("=" * 50)

        improved = reviewer.improve_email(
            email_content=sample_email,
            company_name="TechCorp",
            recipient_name="Sarah Johnson",
            job_title="Software Engineering Intern"
        )

        print(improved)

    # Generate email from scratch
    print("\n" + "=" * 50)
    print("GENERATED EMAIL FROM SCRATCH")
    print("=" * 50)

    generated = reviewer.generate_email(
        company_name="TechCorp",
        recipient_name="Sarah Johnson",
        job_title="PFE Software Engineering Internship",
        your_skills=["Python", "JavaScript", "React", "Database Design", "Machine Learning"],
        your_name="Abdessamad"
    )

    print(generated)