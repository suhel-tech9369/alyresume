import os
import base64
import re
import json
import io
import razorpay
from pdfminer.high_level import extract_text as pdfminer_extract
from flask import Flask, render_template, request, jsonify, session, send_file,redirect
from dotenv import load_dotenv
from openai import OpenAI
import sqlite3
import uuid
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from flask import render_template_string
from reportlab.lib.styles import getSampleStyleSheet
from playwright.sync_api import sync_playwright
from flask import send_file
from flask import send_from_directory
import io
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ===============================
# Load API Key
# ===============================
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
razorpay_client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_SECRET")
    )
)

# ===============================
# Flask App
# ===============================
app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

conn = sqlite3.connect("payments.db", check_same_thread=False)
c = conn.cursor()
from datetime import timedelta
app.permanent_session_lifetime = timedelta(minutes=30)
app.secret_key = os.getenv("SECRET_KEY")
def ensure_payments_table():
    conn = sqlite3.connect("payments.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        payment_id TEXT,
        signature TEXT,
        amount INTEGER,
        cover_letter BOOLEAN,
        download_token TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect("payments.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            payment_id TEXT,
            signature TEXT,
            amount INTEGER,
            cover_letter BOOLEAN,
            download_token TEXT, 
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
# ===============================
# Helper: Clean User Input
# ===============================
def clean_text(msg):
    msg = msg.strip()

    patterns = [
        r"mera naam\s*",
        r"my name is\s*",
        r"i am\s*",
        r"main\s*",
        r"me\s*"
    ]

    for p in patterns:
        msg = re.sub(p, "", msg, flags=re.IGNORECASE)

    msg = re.sub(r"\s*hai$", "", msg, flags=re.IGNORECASE)
    msg = re.sub(r"\s*hoon$", "", msg, flags=re.IGNORECASE)

    return msg.strip().title()


# ===============================
# ✅ Strict Yes/No Validator
# ===============================
def strict_yes_no(user_msg):
    msg = user_msg.strip().lower()
    if msg == "yes":
        return "yes"
    if msg == "no":
        return "no"
    return None


# ===============================
# ✅ Email Validator
# ===============================
def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email)


# ===============================
# Detect Technical Job Role
# ===============================
def is_technical(role):
    tech_keywords = [
        "software", "developer", "engineer", "data",
        "it", "programmer", "mechanical", "electrical",
        "civil", "electronics"
    ]
    return any(word in role.lower() for word in tech_keywords)


# ===============================
# 🌍 Country Photo Rule System
# ===============================
def photo_rule(country, lang):

    c = country.lower()

    # STRICT NO PHOTO COUNTRIES
    strict = [
        "usa","united states","america",
        "uk","united kingdom",
        "canada","australia","ireland","new zealand"
    ]

    # OPTIONAL COUNTRIES
    optional = [
        "india","uae","dubai",
        "singapore","south africa"
    ]

    # RECOMMENDED COUNTRIES
    recommended = [
        "germany","france","spain","italy",
        "netherlands","belgium","austria",
        "switzerland","japan","korea","china"
    ]


    # =========================
    # LANGUAGE MESSAGES
    # =========================

    if lang.lower().startswith("h"):

        if c in strict:
            return "❌ Is country me resume me photo lagana allowed nahi hota. Strictly avoid kiya jata hai."

        elif c in optional:
            return "⚠️ Is country me resume me photo optional hoti hai. Aap chahe to add kar sakte hain."

        elif c in recommended:
            return "✅ Is country me resume me professional photo lagana recommended hota hai."

        else:
            return "⚠️ Resume photo optional hai."

    else:

        if c in strict:
            return "❌ Resume photos are not allowed in this country. Strictly avoided."

        elif c in optional:
            return "⚠️ Resume photo is optional in this country."

        elif c in recommended:
            return "✅ Adding a professional resume photo is recommended in this country."

        else:
            return "⚠️ Resume photo is optional."


# ===============================
# Ask Question in User Language
# ===============================
def ask_in_language(lang, question):
    if not lang or lang.strip().lower().startswith("e"):
        return question

    prompt = f"""
Translate this text into Hinglish (Hindi + English mix).

IMPORTANT RULES:
- Keep the SAME meaning
- DO NOT remove anything
- DO NOT skip "Example"
- KEEP examples EXACTLY same
- KEEP line breaks same
- Translate ONLY main question text
- DO NOT translate URLs, numbers, examples

Text:
{question}

Return translated text.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()


# ===============================
# Home Page
# ===============================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat")
def chat():

    # Only initialize session if it doesn't exist
    if "step" not in session:

        session["step"] = "language"

        session["resume_data"] = {
            "language": None,
            "apply_country": None,
            "current_country": None,
            "job_role": None,
            "experience_type": None,
            "full_name": None,
            "address": None,
            "email": None,
            "phone": None,
            "total_exp": None,
            "companies": [],
            "education": None,
            "college": None,
            "completion_year": None,
            "languages": None,
            "skills": None,
            "projects": None,
            "extra_notes": None,
            "final_resume": None,
            "resume_json": None
        }

    return render_template("chat.html")

# API Chat Endpoint — UPDATED
# Returns: step, chips, example (same as JD version)
# ===============================
# ===============================
# API Chat Endpoint — FINAL
# No ask_in_language — direct Hindi/English
# ===============================
@app.route("/api/chat", methods=["POST"])
def api_chat():
    user_message = request.json.get("message", "").strip()

    step = session.get("step", "language")
    data = session.get("resume_data", {})
    msg_lower = user_message.lower()

    def reply(msg, next_step=None, chips=None, example=None, generating=False):
        session["resume_data"] = data
        session.modified = True
        if next_step:
            session["step"] = next_step
        resp = {"reply": msg}
        if next_step:  resp["step"]      = next_step
        if chips:      resp["chips"]     = chips
        if example:    resp["example"]   = example
        if generating: resp["generating"] = True
        return jsonify(resp)

    # ===============================
    # START
    # ===============================
    if user_message == "__start__":
        session["step"] = "language"
        session["resume_data"] = {
            "language": None, "apply_country": None, "current_country": None,
            "job_role": None, "experience_type": None, "full_name": None,
            "address": None, "email": None, "phone": None, "total_exp": None,
            "companies": [], "education": None, "college": None,
            "completion_year": None, "languages": None, "skills": None,
            "projects": None, "extra_notes": None, "final_resume": None,
            "resume_json": None
        }
        return jsonify({
            "reply": "👋 Welcome to Resume Chat!\n\nApni chat language chunein:\n• English — Chat in English\n• Hindi — Chat in Hindi+English\n\n(Resume hamesha English me banega)",
            "step":  "language",
            "chips": ["English", "Hindi"]
        })

    lang_h = (data.get("language") or "").lower().startswith("h")

    # ===============================
    # STEP 1: Language
    # ===============================
    if step == "language":
        data["language"] = user_message
        lang_h = user_message.lower().startswith("h")

        if lang_h:
            q = "Aap kis country ke liye apply kar rahe hain?"
        else:
            q = "Which country are you applying for?"

        return reply(q, next_step="country",
                     example="India / Germany / UAE / USA")

    # ===============================
    # STEP 2: Country
    # ===============================
    if step == "country":
        data["apply_country"] = user_message

        if lang_h:
            q = "Aap kis job role ke liye apply kar rahe hain?"
        else:
            q = "What job role are you applying for?"

        return reply(q, next_step="job_role",
                     example="Software Developer / Electrician / Accountant")

    # ===============================
    # STEP 3: Job Role
    # ===============================
    if step == "job_role":
        data["job_role"] = user_message

        if lang_h:
            q = "Aap fresher hain ya experienced?"
        else:
            q = "Are you fresher or experienced?"

        return reply(q, next_step="experience_type",
                     chips=["fresher", "experienced"])

    # ===============================
    # STEP 4: Experience Type
    # ===============================
    if step == "experience_type":
        data["experience_type"] = user_message.lower()

        if "exp" in data["experience_type"]:
            data["companies"] = []

            if lang_h:
                q = "Aapke paas kitne saal ka total experience hai?"
            else:
                q = "How many years of total experience do you have?"

            return reply(q, next_step="total_exp",
                         chips=["skip"],
                         example="2 years / 6 months / skip")

        if lang_h:
            q = "Aapka poora naam kya hai?"
        else:
            q = "What is your full name?"

        return reply(q, next_step="full_name",
                     example="Rahul Sharma / Priya Singh")

    # ===============================
    # STEP 4A: Total Experience
    # ===============================
    if step == "total_exp":
        if user_message.lower() != "skip":
            data["total_exp"] = user_message

        if lang_h:
            q = "Aapne sabse recently kis company mein kaam kiya tha?"
        else:
            q = "Which company did you work in most recently?"

        return reply(q, next_step="company_name",
                     chips=["skip", "self"],
                     example="TCS / Infosys / self / skip")

    # ===============================
    # STEP 4B: Company Name
    # ===============================
    if step == "company_name":
        if user_message.lower() == "skip":
            if lang_h:
                q = "Aapka poora naam kya hai?"
            else:
                q = "What is your full name?"
            return reply(q, next_step="full_name",
                         example="Rahul Sharma / Priya Singh")

        if any(w in msg_lower for w in ["khud","own","self","freelance","business"]):
            company = {"name": "Self-Employed"}
        else:
            company = {"name": user_message}

        data["companies"].append(company)

        if lang_h:
            q = f"Aap {company['name']} mein kis saal se kis saal tak kaam kiya?"
        else:
            q = f"In {company['name']}, you worked from which year to which year?"

        return reply(q, next_step="company_duration",
                     example="2021 - 2023 / Jan 2022 - Mar 2024")

    # ===============================
    # STEP 4C: Company Duration
    # ===============================
    if step == "company_duration":
        data["companies"][-1]["duration"] = user_message

        if lang_h:
            q = "Kya aap ek aur company add karna chahte hain?"
        else:
            q = "Do you want to add another company?"

        return reply(q, next_step="add_more_company",
                     chips=["yes", "no"])

    # ===============================
    # STEP 4D: Add More Company
    # ===============================
    if step == "add_more_company":
        answer = strict_yes_no(user_message)
        if answer is None:
            return jsonify({
                "reply": "⚠ Sirf yes ya no likhein" if lang_h else "⚠ Please answer only: yes or no",
                "chips": ["yes", "no"]
            })

        if answer == "yes":
            if lang_h:
                q = "Agli company ka naam batayein?"
            else:
                q = "Next company name?"
            return reply(q, next_step="company_name",
                         chips=["skip", "self"],
                         example="Wipro / HCL / self")

        if lang_h:
            q = "Aapka poora naam kya hai?"
        else:
            q = "What is your full name?"

        return reply(q, next_step="full_name",
                     example="Rahul Sharma / Priya Singh")

    # ===============================
    # STEP 5: Name
    # ===============================
    if step == "full_name":
        data["full_name"] = clean_text(user_message)

        if lang_h:
            q = "Aapka poora address kya hai?"
        else:
            q = "What is your full address?"

        return reply(q, next_step="address",
                     example="Lucknow, Uttar Pradesh, India")

    # ===============================
    # STEP 6: Address
    # ===============================
    if step == "address":
        data["address"] = user_message
        if "india" in user_message.lower():
            data["current_country"] = "India"

        if lang_h:
            q = "Aapka email address kya hai?"
        else:
            q = "What is your email address?"

        return reply(q, next_step="email",
                     example="rahul123@gmail.com")

    # ===============================
    # STEP 7: Email
    # ===============================
    if step == "email":
        if not is_valid_email(user_message):
            return jsonify({
                "reply":   "⚠ Sahi email dalein." if lang_h else "⚠ Please enter a valid email.",
                "step":    "email",
                "example": "name@gmail.com"
            })

        data["email"] = user_message
        session["resume_data"] = data

        if lang_h:
            q = "Aapka phone number kya hai?"
        else:
            q = "What is your phone number?"

        return reply(q, next_step="phone",
                     example="+91 9876543210")

    # ===============================
    # STEP 8: Phone
    # ===============================
    if step == "phone":
        data["phone"] = user_message
        session["resume_data"] = data

        if lang_h:
            q = "Aapki sabse badi degree ya qualification kya hai?"
        else:
            q = "What is your highest qualification or degree?"

        return reply(q, next_step="education",
                     example="B.Tech in Computer Science / MBA / 12th Pass")

    # ===============================
    # STEP 9: Education
    # ===============================
    if step == "education":
        data["education"] = user_message

        if lang_h:
            q = "Aapne kis college ya university mein padhai ki?"
        else:
            q = "Which college or university did you study in?"

        return reply(q, next_step="college",
                     example="Delhi University / IIT Bombay / AKTU")

    # ===============================
    # STEP 10: College
    # ===============================
    if step == "college":
        data["college"] = user_message

        if lang_h:
            q = "Aapka graduation year kya tha?"
        else:
            q = "What is your completion year?"

        return reply(q, next_step="completion_year",
                     chips=["Pursuing"],
                     example="2021 / 2023 / Pursuing")

    # ===============================
    # STEP 11: Completion Year
    # ===============================
    if step == "completion_year":
        data["completion_year"] = user_message

        if lang_h:
            q = "Aap kaun kaun si languages jaante hain?"
        else:
            q = "Which languages do you know?"

        return reply(q, next_step="languages",
                     example="Hindi, English / English, French")

    # ===============================
    # STEP 12: Languages
    # ===============================
    if step == "languages":
        data["languages"] = user_message

        if lang_h:
            q = "Aapki skills batayein, ya main job role ke hisaab se generate kar dun? (generate likhein)"
        else:
            q = "Tell me your skills, or should I generate ATS-friendly skills? (type: generate)"

        return reply(q, next_step="skills",
                     chips=["generate"],
                     example="Python, HTML, CSS / ya likhein: generate")

    # ===============================
    # STEP 13: Skills
    # ===============================
    if step == "skills":
        if "generate" in msg_lower:
            skill_prompt = f"Generate ATS-friendly skills for job role: {data['job_role']}"
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": skill_prompt}]
            )
            data["skills"] = res.choices[0].message.content.strip()
        else:
            data["skills"] = user_message

        if lang_h:
            q = "Kya aapke paas koi certificate ya course hai?\n\nExample: AWS Certified Developer / Python course Coursera se\n\nNahi hai to skip likhein."
        else:
            q = "Do you have any certifications or courses?\n\nExample: AWS Certified Developer / Python course from Coursera\n\nType skip if none."

        return reply(q, next_step="extra_custom",
                     chips=["skip"],
                     example="AWS Certificate / Python course / skip")

    # ===============================
    # STEP: Extra Custom (Certificate)
    # ===============================
    if step == "extra_custom":
        data["extra_custom"] = user_message

        if lang_h:
            q = """Kya aap kuch aur add karna chahte hain?

Aap in mein se kuch bhi add kar sakte hain:
- Achievement (jaise award mila, competition jita)
- Project (jaise koi app banaya, website banai)
- Hobbies (aapki pasand)
- Links (LinkedIn, GitHub, Portfolio)

Example:
"Achievement: District level cricket tournament jita"
"Hobbies: Football, Photography"
"Links: linkedin.com/in/rahul"

Ya seedha likh dein jo add karna ho.
Skip likhein agar kuch nahi add karna."""
        else:
            q = """Do you want to add anything else?

You can add any of these:
- Achievement (award received, competition won)
- Project (app built, website created)
- Hobbies (your interests)
- Links (LinkedIn, GitHub, Portfolio)

Example:
"Achievement: Won district level cricket tournament"
"Hobbies: Football, Photography"
"Links: linkedin.com/in/rahul"

Or just type whatever you want to add.
Type skip if nothing to add."""

        return reply(q, next_step="extra_notes",
                     chips=["skip"],
                     example="Achievement: Won prize / Hobbies: Cricket / skip")

    # ===============================
    # STEP 14: Resume Generate
    # ===============================
    if step == "extra_notes":
        data["extra_notes"] = user_message
        session["step"] = "done"

        prompt = f"""
        Generate a Europass ATS Professional Resume.

        MANDATORY NUMBERED FORMAT:

        Use EXACT numbering + formatting below.

        FIXED SECTIONS (Never change numbers)

        1. Name
        Write full name only under heading.

        2. Contact Information
        Address: ___
        Phone: ___
        Email: ___

        3. Skills
        • Use bullet points only.
        • Never number skills.
        • Summarize skills into 5–6 main lines.
        • Categorize if technical role.
        • Keep ATS-friendly keywords.

        4. Languages
        • Hindi (Native)
        • English (Fluent)

        5. Professional Summary
        Write in paragraph format. Strong ATS Europass tone.
        • Mention total years of experience if provided.
        • Mention company names if user worked in companies.
        • Mention job role.
        • Highlight technical strengths.
        • Minimum 4–6 lines summary.

        6. Education
        Degree
        Institution
        Completion Year

        7. Work Experience
        If fresher → write professionally.
        If experienced → STRICT rules:
        • Show EACH company separately.
        • Company name MUST appear.
        • Duration MUST appear.
        • Role MUST appear.
        • Add 2–3 responsibility points.

        FORMAT:
        Software Engineer — Google
        2022 – 2025
        • Developed scalable applications
        • Worked on cloud systems

        8. Certifications
        • Write only user-provided certificates.
        • If none → write placeholder.

        9. Projects
        If none → write placeholder.
        If provided → bullet format.

        DYNAMIC SECTIONS RULE:
        If user provides Achievements, Awards, Availability,
        Hobbies, Links → Create NEW numbered sections from 10 onward.

        SMART EXTRACTION RULE:
        • "hobby" or "I like" → Hobbies section
        • "linkedin" or "portfolio" → Links section
        • Project links → inside Projects section

        Do NOT generate References section.

        Extra Custom Instructions:
        {data.get("extra_custom","")}

        User Data:
        {data}

        Return ONLY resume text.
        """

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Europass ATS Resume Expert."},
                {"role": "user",   "content": prompt}
            ]
        )

        final_resume = res.choices[0].message.content
        final_resume = re.sub(r"-{3,}", "", final_resume)
        final_resume = re.sub(r"_{3,}", "", final_resume)
        data["final_resume"] = final_resume

        # JSON conversion
        json_prompt = f"""
        Convert this NUMBERED resume into JSON.

        Resume Text:
        {final_resume}

        Number Mapping:
        1 → name
        2 → contact
        3 → skills
        4 → languages
        5 → summary
        6 → education
        7 → experience
        10+ → extra_sections

        JSON Format:
        {{
         "name":"",
         "contact":{{"email":"","phone":"","address":""}},
         "skills":[],
         "languages":[],
         "summary":"",
         "education":[],
         "experience":[],
         "extra_sections":[{{"title":"","content":[]}}]
        }}

        Return ONLY JSON.
        """

        json_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return only JSON."},
                {"role": "user",   "content": json_prompt}
            ]
        )

        ai_text = json_res.choices[0].message.content.strip()

        if not ai_text:
            return jsonify({"error": "AI response empty. Please retry."}), 500

        try:
            data["resume_json"] = json.loads(ai_text)
        except json.JSONDecodeError:
            return jsonify({"error": "AI returned invalid JSON. Retry."}), 500

        if lang_h:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Aapka resume ready hai!\n\n"
                "✏️ Kuch badalna ho to bas likhein:\n"
                "→ \"Summary ko aur lamba karo\"\n"
                "→ \"Achievement add karo: Team lead tha\"\n"
                "→ \"Hobbies add karo: Cricket\"\n\n"
                "🎨 Ya Template button click karein download ke liye."
            )
        else:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Your resume is ready!\n\n"
                "✏️ Want to edit? Just tell me:\n"
                "→ \"Make summary longer\"\n"
                "→ \"Add Achievement: Led team of 5\"\n"
                "→ \"Add Hobbies: Cricket\"\n\n"
                "🎨 Or click Template button to download."
            )

        final_resume += instruction_msg
        data["final_resume"] = final_resume
        session["resume_data"] = data
        session.modified = True

        return jsonify({
            "reply":      final_resume,
            "generating": True,
            "step":       "done"
        })

    # ===============================
    # EDIT MODE
    # ===============================
    if step == "done":
        old_resume = data.get("final_resume", "").split("--------------------")[0].strip()

        edit_prompt = f"""
        You are a Resume Editor AI.

        Here is the current numbered resume:
        {old_resume}

        User requested this update:
        "{user_message}"

        STRICT NUMBER PROTECTION RULES:
        Sections 1–9 are FIXED. NEVER change their numbers.

        Mapping:
        1 → Name
        2 → Contact
        3 → Skills
        4 → Languages
        5 → Professional Summary
        6 → Education
        7 → Work Experience
        8 → Certifications
        9 → Projects

        New sections start from 10 onward.
        Return FULL updated resume.
        Apply ONLY requested edit.
        Keep all other content exactly same.
        """

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Resume Editor AI."},
                {"role": "user",   "content": edit_prompt}
            ]
        )

        updated_resume = res.choices[0].message.content
        updated_resume = re.sub(r"-{3,}", "", updated_resume)
        updated_resume = re.sub(r"_{3,}", "", updated_resume)
        data["final_resume"] = updated_resume

        if lang_h:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Resume update ho gaya!\n\n"
                "✏️ Aur changes chahiye to likhein.\n"
                "🎨 Ya Template button click karein."
            )
        else:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Resume updated!\n\n"
                "✏️ Need more changes? Just tell me.\n"
                "🎨 Or click Template button to download."
            )

        updated_resume += instruction_msg
        session["resume_data"] = data
        session.modified = True

        return jsonify({"reply": updated_resume, "step": "done"})

    return jsonify({"reply": "Something went wrong. Please try again."})
# ===============================
# 🔥 NUMBER RESUME PARSER
# ===============================
def parse_numbered_resume(text):

    sections = {}

    # 🔥 Strict heading match (line start only)
    pattern = r"^\s*(\d+)\.\s+(.+?)(:|-)?\s*$"

    matches = list(re.finditer(pattern, text, re.MULTILINE))

    for i in range(len(matches)):

        start = matches[i].end()

        number = matches[i].group(1).strip()
        title = matches[i].group(2).strip().lower()

        end = matches[i+1].start() if i+1 < len(matches) else len(text)

        content = text[start:end].strip()

        # 🔥 CLEAN content → merge broken lines
        content = re.sub(r"\n{2,}", "\n", content)

        sections[number] = {
            "title": title,
            "content": content
        }

    return sections
# ===============================
# ✅ Template Preview Route
# ===============================
@app.route("/template1-preview")
def template_preview():

    data = session.get("resume_data", {})
    country = data.get("apply_country","")
    if not data.get("final_resume"):
        return "Resume not generated yet!"

    resume_text = data["final_resume"]
    resume_text = resume_text.split("--------------------")[0].strip()
    sections = parse_numbered_resume(resume_text)

    # ===============================
    # SUMMARY CLEAN FIX
    # ===============================

    summary_section = sections.get("5", {})
    summary_content = summary_section.get("content", "")

    # 🔥 REMOVE extra blank lines
    summary_content = re.sub(r"\n{2,}", "\n", summary_content)

    # 🔥 REMOVE leading/trailing spaces
    summary_content = summary_content.strip()

    # 🔥 FORCE single paragraph flow
    summary_content = summary_content.replace("\n", " ")

    sections["5"]["content"] = summary_content

    return render_template(

        "template1.html",
        apply_country = country,
        contact=sections.get("2", {}),
        skills=sections.get("3", {}),
        languages=sections.get("4", {}),

        name=sections.get("1", {}),

        summary=sections.get("5", {}),
        education=sections.get("6", {}),
        experience=sections.get("7", {}),
        certifications=sections.get("8", {}),
        projects=sections.get("9", {}),

        job_role=data.get("job_role"),
        extra_sections={
            k: v for k, v in sections.items() if int(k) > 9
        }
    )

# ===============================
# TEMPLATE 2 PREVIEW ROUTE
# ===============================
@app.route("/template2-preview")
def template2_preview():

    data = session.get("resume_data", {})
    country = data.get("apply_country", "")
    if not data.get("final_resume"):
        return "Resume not generated yet!"

    resume_text = data["final_resume"]
    resume_text = resume_text.split("--------------------")[0].strip()

    sections = parse_numbered_resume(resume_text)
    # ===============================
    # SUMMARY CLEAN FIX
    # ===============================

    summary_section = sections.get("5", {})
    summary_content = summary_section.get("content", "")

    # 🔥 REMOVE extra blank lines
    summary_content = re.sub(r"\n{2,}", "\n", summary_content)

    # 🔥 REMOVE leading/trailing spaces
    summary_content = summary_content.strip()

    # 🔥 FORCE single paragraph flow
    summary_content = summary_content.replace("\n", " ")

    sections["5"]["content"] = summary_content

    return render_template(

        "template2.html",
        apply_country=country,
        contact=sections.get("2", {}),
        skills=sections.get("3", {}),
        languages=sections.get("4", {}),

        name=sections.get("1", {}),

        summary=sections.get("5", {}),
        education=sections.get("6", {}),
        experience=sections.get("7", {}),
        certifications=sections.get("8", {}),
        projects=sections.get("9", {}),

        job_role=data.get("job_role"),
        extra_sections={
            k: v for k, v in sections.items()
            if int(k) > 9
        }
    )

# ===============================
# TEMPLATE 3 PREVIEW ROUTE
# ===============================
@app.route("/template3-preview")
def template3_preview():

    data = session.get("resume_data", {})
    country = data.get("apply_country", "")
    if not data.get("final_resume"):
        return "Resume not generated yet!"

    resume_text = data["final_resume"]
    resume_text = resume_text.split("--------------------")[0].strip()

    sections = parse_numbered_resume(resume_text)

    # ===============================
    # SUMMARY CLEAN FIX
    # ===============================

    summary_section = sections.get("5", {})
    summary_content = summary_section.get("content", "")

    # 🔥 REMOVE extra blank lines
    summary_content = re.sub(r"\n{2,}", "\n", summary_content)

    # 🔥 REMOVE leading/trailing spaces
    summary_content = summary_content.strip()

    # 🔥 FORCE single paragraph flow
    summary_content = summary_content.replace("\n", " ")

    sections["5"]["content"] = summary_content

    return render_template(

        "template3.html",
        apply_country=country,
        contact=sections.get("2", {}),
        skills=sections.get("3", {}),
        languages=sections.get("4", {}),

        name=sections.get("1", {}),

        summary=sections.get("5", {}),
        education=sections.get("6", {}),
        experience=sections.get("7", {}),
        certifications=sections.get("8", {}),
        projects=sections.get("9", {}),
        job_role=data.get("job_role"),
        extra_sections={
            k: v for k, v in sections.items()
            if int(k) > 9
        }
    )


@app.route("/check-resume")
def check_resume():
    chat_data = session.get("resume_data", {}) or {}
    jd_data   = session.get("jd_data", {}) or {}
    ready = bool(chat_data.get("final_resume")) or bool(jd_data.get("final_resume"))
    return jsonify({"ready": ready})
# ===============================
# GENERATE COVER LETTER
# ===============================
@app.route("/generate-cover-letter")
def generate_cover_letter():

    data = session.get("resume_data", {})

    resume_text = data.get("final_resume", "")

    prompt = f"""
    Write a professional job cover letter
    based strictly on the resume below.

    Resume:
    {resume_text}

    STRICT INSTRUCTIONS:

    1️⃣ Extract REAL candidate details from resume:

    - Full Name
    - Address
    - Phone
    - Email
    - Skills
    - Education
    - Experience
    - Companies worked in

    ⚠️ IMPORTANT FORMAT RULE:

    Write candidate contact details at the VERY TOP
    of the cover letter in this order:

    Full Name  
    Address  
    Phone  
    Email  

    (Do NOT place contact details at bottom)

    --------------------------------------------------

    2️⃣ EXPERIENCE LOGIC:

    If candidate is EXPERIENCED:

    • Mention companies worked in
    • Mention years of experience
    • Mention achievements tone

    Example tone:
    "With professional experience at [Company Name]..."

    If candidate is FRESHER:

    • Focus on education
    • Focus on skills
    • Focus on learning attitude

    Example tone:
    "As a recent graduate..."

    --------------------------------------------------

    3️⃣ MANUAL FIELDS (User will fill):

Keep placeholders but write clear guidance
in same line so user understands instantly:

[EMPLOYER NAME — Hiring Manager / HR of company you are applying to]

[COMPANY APPLYING NAME — Company where you are applying]

[COMPANY ADDRESS — Office address of applying company]

[JOB TITLE — Position you are applying for]

[DATE — Write today’s date]

Write them in CAPITAL LETTERS
so user can easily identify and edit.

    --------------------------------------------------

    4️⃣ SALUTATION RULE:

    If company applying name not available:

    Write:
    Dear Hiring Manager

    --------------------------------------------------

    5️⃣ Write complete job-ready cover letter.

    Professional tone.
    No explanations.
    No extra notes.
    Proper business letter format.
    """

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system",
             "content":"You are a professional HR writer."},
            {"role":"user",
             "content":prompt}
        ]
    )

    letter = res.choices[0].message.content

    data["cover_letter"] = letter
    session["resume_data"] = data

    return jsonify({"cover_letter":letter})

# ===============================
# DOWNLOAD COVER LETTER PDF
# ===============================


@app.route("/download-cover-letter", methods=["POST"])
def download_cover_letter():

    data = request.get_json()
    text = data.get("text", "")

    buffer = io.BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    content = []

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    custom_style = ParagraphStyle(
        'CoverStyle',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#444444"),
        spaceAfter=5
    )

    for line in text.split("\n"):
        if line.strip() != "":
            content.append(Paragraph(line, custom_style))

    pdf.build(content)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="CoverLetter.pdf",
        mimetype="application/pdf"
    )

@app.route("/create-order", methods=["POST"])
def create_order():
    ensure_payments_table()
    from datetime import datetime, timedelta

    conn = sqlite3.connect("payments.db")
    c = conn.cursor()

    c.execute("""
    SELECT created_at FROM payments
    ORDER BY created_at DESC
    LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    try:
        data = request.get_json()
        print("DATA RECEIVED:", data)

        type_ = data.get("type")   # ats or resume
        include_cover = data.get("cover_letter", False)

        # 🔥 SAFE SKIP LOGIC (IMPORTANT FIX)
        if row:
            last_payment_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")

            # 👉 ATS payment ko resume skip me use mat karo
            if type_ != "ats":
                if datetime.now() - last_payment_time < timedelta(minutes=30):
                    session["paid"] = True
                    session.modified = True
                    return jsonify({
                        "skip_payment": True
                    })

        # 🔥 FINAL PRICING
        if type_ == "ats":
            amount = 1100   # ₹11
        else:
            amount = 4900   # ₹49 (resume + cover)

        print("AMOUNT:", amount)

        order = razorpay_client.order.create({
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        })

        print("ORDER CREATED:", order)

        return jsonify({
            "order_id": order["id"],
            "amount": amount,
            "key": os.getenv("RAZORPAY_KEY_ID")
        })

    except Exception as e:
        print("CREATE ORDER ERROR:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/verify-payment", methods=["POST"])
def verify_payment():

    data = request.get_json()

    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })

        payment = razorpay_client.payment.fetch(razorpay_payment_id)
        amount = payment["amount"]

        download_token = str(uuid.uuid4())

        # 🔥 VALID AMOUNTS
        if amount not in [4900, 1100]:
            return jsonify({"status": "invalid_amount"}), 400

        # 🔥 TYPE DETECT
        if amount == 1100:
            payment_type = "ats"
        else:
            payment_type = "resume"

        # 🔥 SAVE DB
        conn = sqlite3.connect("payments.db")
        c = conn.cursor()

        c.execute("SELECT * FROM payments WHERE payment_id = ?", (razorpay_payment_id,))
        existing = c.fetchone()

        if existing:
            conn.close()
            return jsonify({"status": "already_recorded"})

        c.execute("""
            INSERT INTO payments 
            (order_id, payment_id, signature, amount, cover_letter, download_token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
            amount,
            True if payment_type == "resume" else False,
            download_token,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        # 🔥 SESSION CONTROL
        if payment_type == "resume":
            session["paid"] = True
        elif payment_type == "ats":
            session["ats_paid"] = True

        session["paid_time"] = datetime.now().isoformat()
        session.modified = True

        return jsonify({
            "status": "success",
            "token": download_token
        })

    except Exception as e:
        print("VERIFY ERROR:", e)
        return jsonify({"status": "failed", "error": str(e)}), 400

@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        password = request.form.get("password")

        if password == os.getenv("ADMIN_PASSWORD"):
            session.permanent = True
            session["admin_logged_in"] = True
            return redirect("/admin/dashboard")
        else:
            return "Wrong Password ❌"

    return """
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: Arial; padding: 50px; text-align:center; }
            input { padding:10px; width:250px; }
            button { padding:10px 20px; background:#3b82f6; color:white; border:none; }
        </style>
    </head>
    <body>
        <h2>Admin Login</h2>
        <form method="POST">
            <div style="position:relative; display:inline-block;">
    <input type="password" id="password" name="password" placeholder="Enter Admin Password" required style="padding:10px; width:250px;">
    <span onclick="togglePassword()" 
          style="position:absolute; right:10px; top:10px; cursor:pointer;">👁</span>
</div>

<script>
function togglePassword() {
    var x = document.getElementById("password");
    if (x.type === "password") {
        x.type = "text";
    } else {
        x.type = "password";
    }
}
</script>
            <br><br>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin_logged_in"):
        return redirect("/admin")

    conn = sqlite3.connect("payments.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM payments ORDER BY id DESC")
    payments = c.fetchall()

    c.execute("SELECT SUM(amount) FROM payments")
    total_revenue = c.fetchone()[0] or 0

    c.execute("SELECT COUNT(*) FROM payments WHERE cover_letter = 0")
    resume_only = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM payments WHERE cover_letter = 1")
    resume_cover = c.fetchone()[0]
    conn.close()

    table_rows = ""
    for p in payments:
        table_rows += f"""
        <tr>
            <td>{p['id']}</td>
            <td>{p['order_id']}</td>
            <td>{p['payment_id']}</td>
            <td>₹ {p['amount']/100}</td>
            <td>{"Yes" if p['cover_letter'] else "No"}</td>
            <td>{p['created_at']}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{ font-family: Arial; padding: 30px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
            th {{ background-color: #3b82f6; color: white; }}
        </style>
    </head>
    <body>

    <h1>Admin Dashboard</h1>
    <a href="/admin/logout" style="float:right;
     background:red; color:white; padding:8px 15px; text-decoration:none;">Logout</a>

    <h3>Total Revenue: ₹ {total_revenue / 100}</h3>
    <h3>Resume Only Sales: {resume_only}</h3>
    <h3>Resume + Cover Sales: {resume_cover}</h3>

    <hr>

    <table>
        <tr>
            <th>ID</th>
            <th>Order ID</th>
            <th>Payment ID</th>
            <th>Amount</th>
            <th>Cover Letter</th>
            <th>Date</th>
        </tr>
        {table_rows}
    </table>

    </body>
    </html>
    """
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin")


@app.route("/download-resume", methods=["POST"])
@limiter.limit("5 per minute")
def download_resume():

    print("=== DOWNLOAD CALLED ===")

    data = request.get_json()
    template_path = data.get("template")

    # 🔥 FREE TEMPLATE (template1)
    if "template1" not in template_path:
        if not session.get("paid"):
            return jsonify({"error": "Payment required"}), 403

    data = request.get_json()
    template_path = data.get("template")
    edited_html = data.get("html")

    if not edited_html:
        return "NO edited content found", 400

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1200, "height": 1600}
            )

            page = context.new_page()
            page.set_default_timeout(60000)

            # ===============================
            # CSS LOAD
            # ===============================
            template_name = template_path.split("-")[0].replace("/", "")
            css_path = f"static/{template_name}.css"

            css_content = ""
            if os.path.exists(css_path):
                with open(css_path, "r") as f:
                    css_content = f.read()

            # ===============================
            # PHOTO BASE64
            # ===============================
            photo_path = "static/uploads/profile.jpg"
            photo_base64 = ""

            if os.path.exists(photo_path):
                with open(photo_path, "rb") as img_file:
                    photo_base64 = base64.b64encode(img_file.read()).decode("utf-8")

            # ===============================
            # SAFE PHOTO INJECT
            # ===============================
            if photo_base64 and 'id="profileImg"' in edited_html:
                edited_html = edited_html.replace(
                    'id="profileImg"',
                    f'id="profileImg" src="data:image/jpeg;base64,{photo_base64}"'
                )

            # ===============================
            # FINAL HTML
            # ===============================
            full_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<style>
{css_content}
</style>

<style>
body {{
    margin: 0;
    padding: 0;
}}

.top-bar {{ display: none !important; }}
.watermark-preview {{ display: none !important; }}
button {{ display: none !important; }}
</style>

</head>

<body>
{edited_html}
</body>
</html>
"""

            print("HTML LENGTH:", len(full_html))

            # ===============================
            # LOAD CONTENT
            # ===============================
            page.set_content(full_html, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1000)

            # ===============================
            # PDF
            # ===============================
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                scale=1.12,
                margin={
                    "top": "0mm",
                    "bottom": "0mm",
                    "left": "0mm",
                    "right": "0mm"
                }
            )

            print("PDF SIZE:", len(pdf_bytes))

            page.close()
            context.close()
            browser.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        as_attachment=True,
        download_name="Resume.pdf",
        mimetype="application/pdf"
    )
@app.route("/save-edited-resume", methods=["POST"])
def save_edited_resume():

    data = request.get_json()
    html_content = data.get("html")
    template_path = data.get("template")

    resume_data = session.get("resume_data", {})

    # Always overwrite with latest snapshot
    resume_data["template_path"] = template_path
    session["resume_data"] = resume_data
    session.modified = True

    return {"status": "saved"}


from flask import request, jsonify, url_for, session
from PIL import Image

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload-photo", methods=["POST"])
def upload_photo():

    file = request.files.get("photo")

    if not file:
        return jsonify({"status": "error"})

    filepath = os.path.join(UPLOAD_FOLDER, "profile.jpg")

    # save original image
    file.save(filepath)

    # open image using Pillow
    img = Image.open(filepath)

    # convert to RGB (important for PNG/WEBP uploads)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # resize automatically for resume photo
    max_size = (600, 600)
    img.thumbnail(max_size)

    # compress image
    img.save(filepath, format="JPEG", quality=85, optimize=True)

    # generate correct static url
    photo_url = url_for("static", filename="uploads/profile.jpg")

    session["photo_url"] = photo_url

    return jsonify({
        "status": "success",
        "url": photo_url
    })


@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/reset-session", methods=["POST"])
def reset_session():
    session.clear()
    return {"status": "reset_done"}

@app.route("/robots.txt")
def robots():
    return send_from_directory(".", "robots.txt")

@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory(".", "sitemap.xml")

@app.route("/google903960e41c35f118.html")
def google_verify():
    return send_from_directory(".", "google903960e41c35f118.html")


#resume to cover letter
def extract_pdf_text(file):
    file_bytes = file.read()
    try:
        text = pdfminer_extract(io.BytesIO(file_bytes))
        if text and text.strip():
            return text.strip()
    except Exception:
        pass
    return ""

@app.route("/cover-letter", methods=["GET", "POST"])
def cover_letter_page():
    if request.method == "GET":
        return render_template("cover_letter.html")

    file = request.files.get("resume")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    resume_text = extract_pdf_text(file)

    prompt = f"""
    You are a professional HR writer.
    Read this resume and write a complete professional cover letter.

    Resume:
    {resume_text}

    STRICT FORMAT:

    [Candidate Full Name from resume]
    [Candidate Address from resume]
    [Candidate Phone from resume]
    [Candidate Email from resume]

    [DATE — Write today's date here]

    [EMPLOYER NAME — Write name of Hiring Manager / HR here]
    [COMPANY NAME — Write name of company you are applying to]
    [COMPANY ADDRESS — Write address of that company here]

    Dear Hiring Manager,

    [3 professional paragraphs based on resume]

    Warm regards,
    [Candidate Full Name from resume]

    ---NOTE---
    Fields you need to fill manually:
    - DATE: Write today's date
    - EMPLOYER NAME: Write name of HR or Hiring Manager
    - COMPANY NAME: Write name of company you are applying to
    - COMPANY ADDRESS: Write address of that company
    ---END NOTE---

    STRICT RULES:
    - Extract name, phone, email, address DIRECTLY from resume
    - No labels like "Name:" or "Phone:"
    - All placeholders in English only
    - Return ONLY the cover letter
    """
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """You are a cover letter writer.
    STRICT RULES:
    1. Extract candidate real name, phone, email, address from resume text and write them DIRECTLY at top — no placeholders for these.
    2. These fields user will fill — keep EXACTLY as written with guidance:
       [DATE — Write today's date here, example: 16 March 2026]
       [EMPLOYER NAME — Write Hiring Manager or HR name here, example: Mr. Rahul Sharma]
       [COMPANY NAME — Write the company name where you are applying, example: TCS / Google]
       [COMPANY ADDRESS — Write that company's office address here]
    3. NEVER fill EMPLOYER NAME, COMPANY NAME, COMPANY ADDRESS, DATE yourself.
    4. Write professional cover letter body based on resume.
    5. Return ONLY the cover letter."""},
            {"role": "user", "content": prompt}
        ]
    )

    return jsonify({"result": res.choices[0].message.content})


@app.route("/download-cover-letter-tool", methods=["POST"])
def download_cover_letter_tool():
    data = request.get_json()
    text = data.get("text", "")

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    custom_style = ParagraphStyle(
        'CoverStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11.5,
        leading=18,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=8,
        leftIndent=10,
        rightIndent=10
    )

    content = []
    for line in text.split("\n"):
        if line.strip() != "":
            content.append(Paragraph(line, custom_style))

    pdf.build(content)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="CoverLetter.pdf",
        mimetype="application/pdf"
    )

@app.route("/ats-checker", methods=["GET", "POST"])
def ats_checker_page():
    if request.method == "GET":
        return render_template("ats_checker.html")

    file = request.files.get("resume")
    job_description = request.form.get("job_description", "")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    resume_text = extract_pdf_text(file)
    session["ats_resume_text"] = resume_text
    session["ats_job_desc"] = job_description

    prompt = f"""
You are an ATS Resume Expert.
Analyze this resume and give ONLY the ATS score.

Resume:
{resume_text}

Job Description:
{job_description if job_description else "Not provided - do general analysis"}

Return in this EXACT format only — nothing else:

ATS SCORE: XX/100
REASON: One line reason for this score
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an ATS Resume Expert."},
            {"role": "user", "content": prompt}
        ]
    )

    return jsonify({"score": res.choices[0].message.content})


@app.route("/ats-full-report", methods=["POST"])
def ats_full_report():
    resume_text = session.get("ats_resume_text", "")
    job_desc = session.get("ats_job_desc", "")

    prompt = f"""
You are an ATS Resume Expert.
Analyze this resume against the job description.

Resume:
{resume_text}

Job Description:
{job_desc if job_desc else "Not provided - do general analysis"}

Return in this EXACT format:

STRONG POINTS:
- point 1
- point 2
- point 3

WEAK POINTS:
- point 1
- point 2
- point 3

MISSING KEYWORDS:
- keyword 1
- keyword 2
- keyword 3

IMPROVEMENTS:
- improvement 1
- improvement 2
- improvement 3
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an ATS Resume Expert."},
            {"role": "user", "content": prompt}
        ]
    )

    return jsonify({"full_report": res.choices[0].message.content})

@app.route("/download-ats-report", methods=["POST"])
def download_ats_report():
    data = request.get_json()
    text = data.get("text", "")

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    custom_style = ParagraphStyle(
        'ATSStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11.5,
        leading=18,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=8,
        leftIndent=10,
        rightIndent=10
    )

    content = []
    for line in text.split("\n"):
        if line.strip() != "":
            content.append(Paragraph(line, custom_style))

    pdf.build(content)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="ATS_Report.pdf",
        mimetype="application/pdf"
    )

#questions 20  -------------

@app.route("/interview-prep", methods=["GET", "POST"])
def interview_prep_page():
    if request.method == "GET":
        return render_template("interview_prep.html")

    file = request.files.get("resume")
    language = request.form.get("language", "English")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    resume_text = extract_pdf_text(file)

    prompt = f"""
You are an expert Interview Coach.
Read this resume carefully and generate 20 interview questions with detailed answers.

Resume:
{resume_text}

Language: {language}

STRICT RULES:
- First 10 questions: based on skills, experience, education from THIS resume only
- Last 10 questions: common HR questions relevant to this candidate
- Every answer must be specific to THIS candidate — not generic
- If language is Hindi then write in Hinglish (Hindi + English mix)
- If language is English then write in pure English

FORMAT — follow exactly:

Q1: [Question]
A1: [Detailed Answer]

Q2: [Question]
A2: [Detailed Answer]

...till Q20.

Return ONLY questions and answers — nothing else.
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert Interview Coach. Generate specific questions based on the resume provided."},
            {"role": "user", "content": prompt}
        ]
    )

    return jsonify({"result": res.choices[0].message.content})


@app.route("/download-interview-pdf", methods=["POST"])
def download_interview_pdf():
    data = request.get_json()
    text = data.get("text", "")

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    custom_style = ParagraphStyle(
        'InterviewStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11.5,
        leading=18,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=8,
        leftIndent=10,
        rightIndent=10
    )

    content = []
    for line in text.split("\n"):
        if line.strip() != "":
            content.append(Paragraph(line, custom_style))

    pdf.build(content)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="InterviewQuestions.pdf",
        mimetype="application/pdf"
    )

# ===============================
# BLOG PAGE
# ===============================
@app.route("/blog")
def blog():
    return render_template("blog.html")

@app.route("/blog/resume-kaise-banaye")
def blog_resume():
    return render_template("blog_resume.html")

@app.route("/blog/ats-resume")
def blog_ats():
    return render_template("blog_ats.html")


# ==============================
# JD RESUME PAGE
# ==============================
@app.route("/jd-resume")
def jd_resume_page():
    return render_template("jd_resume.html")


# ==============================
# JD START — JD Analyze
# ==============================
@app.route("/api/jd-start", methods=["POST"])
def api_jd_start():

    data     = request.get_json()
    jd_text  = data.get("jd", "")
    language = data.get("language", "English")
    lang_h   = language.lower().startswith("h")

    extract_prompt = f"""
    You are an ATS Resume Expert.
    Read this EXACT job description carefully — word by word.

    Job Description:
    {jd_text}

    Extract information ONLY from the job description above.
    Do NOT add anything that is not in the job description.

    Return ONLY this JSON (no extra text, no markdown):
    {{
      "job_title": "",
      "skills": [],
      "experience_level": "",
      "experience_years": "",
      "responsibilities": [],
      "summary_hint": "",
      "country": ""
    }}

    Rules:
    - job_title: exact job title mentioned in JD
    - skills: Extract EVERY skill keyword from JD — programming languages, frameworks, databases, tools, cloud platforms, methodologies, soft skills, certifications, equipment — EVERYTHING mentioned. Extract from ALL sections — title, requirements, responsibilities, preferred qualifications. Do NOT add skills that are not in JD.
    - experience_level: "fresher" / "1-2 years" / "3-5 years" / "5+ years"
    - experience_years: exact experience text from JD like "3 years" / "2+ years" / "" if not mentioned
    - responsibilities: 3-4 key duties directly from JD
    - summary_hint: 2-3 line ATS summary using ONLY JD keywords
    - country: country name if clearly mentioned in JD, else empty string ""
    """

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """You are an ATS Resume Expert.
    CRITICAL RULES:
    - Read the job description carefully
    - Extract skills ONLY from the provided job description
    - Do NOT invent or add skills not mentioned in JD
    - Return valid JSON only, no markdown, no extra text"""},
            {"role": "user", "content": extract_prompt}
        ]
    )

    ai_text = res.choices[0].message.content.strip()
    ai_text = re.sub(r"```json|```", "", ai_text).strip()

    try:
        jd_analysis = json.loads(ai_text)
    except json.JSONDecodeError:
        return jsonify({"error": "JD analysis failed. Please try again."}), 500

    detected_country   = jd_analysis.get("country", "").strip()
    experience_years   = jd_analysis.get("experience_years", "").strip()

    session["jd_step"] = "experience_type"
    session["jd_data"] = {
        "language"         : language,
        "jd_text"          : jd_text,
        "jd_analysis"      : jd_analysis,
        "job_role"         : jd_analysis.get("job_title", ""),
        "skills"           : ", ".join(jd_analysis.get("skills", [])),
        "summary_hint"     : jd_analysis.get("summary_hint", ""),
        "detected_country" : detected_country,
        "experience_years" : experience_years,
        "apply_country"    : None,
        "experience_type"  : None,
        "full_name"        : None,
        "address"          : None,
        "email"            : None,
        "phone"            : None,
        "total_exp"        : None,
        "companies"        : [],
        "education"        : None,
        "college"          : None,
        "completion_year"  : None,
        "languages"        : None,
        "extra_notes"      : None,
        "final_resume"     : None,
    }

    job_title    = jd_analysis.get("job_title", "this role")
    skills_short = ", ".join(jd_analysis.get("skills", [])[:4])

    if lang_h:
        reply = (
            f"✅ JD analyze ho gaya!\n\n"
            f"🎯 **Role:** {job_title}\n"
            f"🔧 **Skills mili:** {skills_short}...\n\n"
            f"Ye skills automatically resume me jaayengi.\n"
            f"Ab bas aapki personal details chahiye.\n\n"
            f"Aap **fresher** hain ya **experienced**?"
        )
    else:
        reply = (
            f"✅ JD analyzed!\n\n"
            f"🎯 **Role:** {job_title}\n"
            f"🔧 **Skills found:** {skills_short}...\n\n"
            f"These will be auto-added to your resume.\n"
            f"I just need your personal details now.\n\n"
            f"Are you **fresher** or **experienced**?"
        )

    return jsonify({
        "reply"  : reply,
        "chips"  : ["fresher", "experienced"],
        "step"   : "experience_type"
    })

# ==============================
# JD CHAT — Personal Questions
# ==============================
def _ask_experience(data, lang_h):
    experience_years = data.get("experience_years", "")
    exp_type         = data.get("experience_type", "")

    if "exp" in exp_type:
        if experience_years:
            if lang_h:
                reply = (
                    f"JD me **{experience_years}** ka experience manga gaya hai.\n"
                    f"Aapke paas kitne saal ka experience hai?"
                )
            else:
                reply = (
                    f"The JD requires **{experience_years}** of experience.\n"
                    f"How many years of experience do you have?"
                )
        else:
            if lang_h:
                reply = "Aapka total experience kitne saal ka hai?"
            else:
                reply = "How many years of total experience do you have?"

        session["jd_step"] = "total_exp"
        session["jd_data"] = data
        return jsonify({
            "reply"  : reply,
            "example": "3 years / 6 months / 2.5 years  (or: skip)",
            "step"   : "total_exp"
        })
    else:
        session["jd_step"] = "full_name"
        session["jd_data"] = data
        return jsonify({
            "reply"  : "Aapka poora naam kya hai?" if lang_h else "What is your full name?",
            "example": "Rahul Sharma / Priya Singh",
            "step"   : "full_name"
        })


@app.route("/api/jd-chat", methods=["POST"])
def api_jd_chat():

    user_message = request.json.get("message", "").strip()
    step         = session.get("jd_step", "experience_type")
    data         = session.get("jd_data", {})
    lang         = data.get("language", "English")
    lang_h       = lang.lower().startswith("h")
    msg_lower    = user_message.lower()

    def save_and_reply(reply, chips=None, example=None, next_step=None):
        session["jd_data"] = data
        session.modified = True
        if next_step:
            session["jd_step"] = next_step
        resp = {"reply": reply}
        if chips:     resp["chips"] = chips
        if example:   resp["example"] = example
        if next_step: resp["step"] = next_step
        return jsonify(resp)

    # ==============================
    # STEP: EXPERIENCE TYPE
    # ==============================
    if step == "experience_type":

        data["experience_type"] = msg_lower

        detected_country = data.get("detected_country", "")

        if "exp" in msg_lower:
            data["companies"] = []

        if detected_country:
            if lang_h:
                reply = (
                    f"JD me job **{detected_country}** ke liye hai.\n"
                    f"Kya yahi sahi hai, ya koi aur country hai?"
                )
                chips = [detected_country, "Koi aur hai"]
            else:
                reply = (
                    f"I found that this job is in **{detected_country}**.\n"
                    f"Is that correct, or is it a different country?"
                )
                chips = [detected_country, "Different country"]

            return save_and_reply(reply, chips=chips, next_step="country_confirm")
        else:
            if lang_h:
                reply = "JD me country nahi mili, batao kahan apply karna hai?"
            else:
                reply = "I couldn't find a country in the JD. Which country are you applying to?"

            return save_and_reply(
                reply,
                example="India / Germany / UAE / USA",
                next_step="country"
            )

    # ==============================
    # STEP: COUNTRY CONFIRM
    # ==============================
    if step == "country_confirm":

        detected_country = data.get("detected_country", "")

        if (user_message.lower() == detected_country.lower()
                or user_message.lower() in ["yes","haan","ha","correct","sahi"]):
            data["apply_country"] = detected_country
        elif user_message.lower() in ["different country","koi aur hai","no","nahi"]:
            if lang_h:
                reply = "Theek hai, kaunse country me apply kar rahe hain?"
            else:
                reply = "Got it! Which country are you applying to?"
            return save_and_reply(
                reply,
                example="India / Germany / UAE / USA",
                next_step="country"
            )
        else:
            data["apply_country"] = user_message

        return _ask_experience(data, lang_h)

    # ==============================
    # STEP: COUNTRY (manual)
    # ==============================
    if step == "country":
        data["apply_country"] = user_message
        return _ask_experience(data, lang_h)

    # ==============================
    # STEP: TOTAL EXP
    # ==============================
    if step == "total_exp":

        if msg_lower != "skip":
            data["total_exp"] = user_message

        if lang_h:
            reply = (
                "Sabse recent company ka naam kya hai?\n"
                "(skip likhein agar company nahi hai)"
            )
        else:
            reply = (
                "Which company did you work in most recently?\n"
                "(type skip if none)"
            )

        return save_and_reply(
            reply,
            example="TCS / Infosys / self / freelance / skip",
            next_step="company_name"
        )

    # ==============================
    # STEP: COMPANY NAME
    # ==============================
    if step == "company_name":

        if msg_lower == "skip":
            return save_and_reply(
                "Aapka poora naam kya hai?" if lang_h else "What is your full name?",
                example="Rahul Sharma / Priya Singh",
                next_step="full_name"
            )

        if any(w in msg_lower for w in ["self","own","freelance","business","khud"]):
            company = {"name": "Self-Employed"}
        else:
            company = {"name": user_message}

        if "companies" not in data:
            data["companies"] = []

        data["companies"].append(company)

        if lang_h:
            reply = f"Aap **{company['name']}** me kis year se kis year tak the?"
        else:
            reply = f"You worked at **{company['name']}** from which year to which year?"

        return save_and_reply(
            reply,
            example="2021 - 2024 / Jan 2022 - Mar 2024",
            next_step="company_duration"
        )

    # ==============================
    # STEP: COMPANY DURATION
    # ==============================
    if step == "company_duration":

        data["companies"][-1]["duration"] = user_message

        if lang_h:
            reply = "Kya ek aur company add karni hai?"
        else:
            reply = "Do you want to add another company?"

        return save_and_reply(reply, chips=["yes","no"], next_step="add_more_company")

    # ==============================
    # STEP: ADD MORE COMPANY
    # ==============================
    if step == "add_more_company":

        answer = strict_yes_no(user_message)
        if answer is None:
            return jsonify({
                "reply": "⚠ Please answer yes or no",
                "chips": ["yes","no"]
            })

        if answer == "yes":
            return save_and_reply(
                "Agla company ka naam?" if lang_h else "Next company name?",
                example="Wipro / HCL / self",
                next_step="company_name"
            )

        return save_and_reply(
            "Aapka poora naam kya hai?" if lang_h else "What is your full name?",
            example="Rahul Sharma / Priya Singh",
            next_step="full_name"
        )

    # ==============================
    # STEP: FULL NAME
    # ==============================
    if step == "full_name":

        data["full_name"] = clean_text(user_message)

        return save_and_reply(
            "Aapka poora address?" if lang_h else "Your full address?",
            example="Lucknow, Uttar Pradesh, India",
            next_step="address"
        )

    # ==============================
    # STEP: ADDRESS
    # ==============================
    if step == "address":

        data["address"] = user_message

        return save_and_reply(
            "Aapka email address?" if lang_h else "Your email address?",
            example="rahul.sharma@gmail.com",
            next_step="email"
        )

    # ==============================
    # STEP: EMAIL
    # ==============================
    if step == "email":

        if not is_valid_email(user_message):
            return jsonify({
                "reply": "⚠ Sahi email dalein.\n💡 Example: name@gmail.com"
                         if lang_h else
                         "⚠ Please enter a valid email.\n💡 Example: name@gmail.com"
            })

        data["email"] = user_message

        return save_and_reply(
            "Aapka phone number?" if lang_h else "Your phone number?",
            example="+91 9876543210",
            next_step="phone"
        )

    # ==============================
    # STEP: PHONE
    # ==============================
    if step == "phone":

        data["phone"] = user_message

        return save_and_reply(
            "Aapki sabse badi degree ya qualification?" if lang_h
            else "Your highest qualification or degree?",
            example="B.Tech in Computer Science / MBA / 12th Pass",
            next_step="education"
        )

    # ==============================
    # STEP: EDUCATION
    # ==============================
    if step == "education":

        data["education"] = user_message

        return save_and_reply(
            "College ya university ka naam?" if lang_h
            else "College or university name?",
            example="IET Lucknow / Delhi University / AKTU",
            next_step="college"
        )

    # ==============================
    # STEP: COLLEGE
    # ==============================
    if step == "college":

        data["college"] = user_message

        return save_and_reply(
            "Completion year?" ,
            example="2021 / 2023 / Pursuing",
            next_step="completion_year"
        )

    # ==============================
    # STEP: COMPLETION YEAR
    # ==============================
    if step == "completion_year":

        data["completion_year"] = user_message

        return save_and_reply(
            "Aap kaun kaun si languages jaante hain?" if lang_h
            else "Which languages do you know?",
            example="Hindi, English / English, French",
            next_step="languages"
        )

    # ==============================
    # STEP: LANGUAGES → SKILLS
    # ==============================
    if step == "languages":

        data["languages"] = user_message

        jd_skills_list = data.get("jd_analysis", {}).get("skills", [])

        if not jd_skills_list:
            skills_str = data.get("skills", "")
            jd_skills_list = [s.strip() for s in skills_str.split(",") if s.strip()]

        skills_bullet = "\n".join([f"• {s}" for s in jd_skills_list])

        if lang_h:
            reply = (
                f"JD se ye skills mili hain, maine resume me add kar di hain:\n\n"
                f"{skills_bullet}\n\n"
                f"Koi aur skill add karni hai to likh den.\n"
                f"Nahi to **skip** likhen."
            )
        else:
            reply = (
                f"I found these skills from the JD and added them to your resume:\n\n"
                f"{skills_bullet}\n\n"
                f"Want to add any more skills? Type them below.\n"
                f"Otherwise type **skip**."
            )

        return save_and_reply(reply, chips=["skip"], next_step="extra_skills")

    # ==============================
    # STEP: EXTRA SKILLS
    # ==============================
    if step == "extra_skills":

        jd_skills_list = data.get("jd_analysis", {}).get("skills", [])

        if msg_lower != "skip" and user_message.strip():
            extra      = [s.strip() for s in
                          user_message.replace(",", "\n").split("\n")
                          if s.strip()]
            all_skills = jd_skills_list + extra
        else:
            all_skills = jd_skills_list

        boost_prompt = f"""
Job role: {data.get("job_role","")}
Current skills: {", ".join(all_skills)}

Add 2-3 more relevant ATS-friendly skills for this role.
Return ONLY a comma-separated list of the NEW skills to add.
No explanation. No numbering.
"""
        boost_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return only comma-separated skills."},
                {"role": "user",   "content": boost_prompt}
            ]
        )
        extra_gpt  = [s.strip() for s in
                      boost_res.choices[0].message.content.strip().split(",")
                      if s.strip()]

        final_skills   = all_skills + extra_gpt
        data["skills"] = ", ".join(final_skills)

        if lang_h:
            reply = (
                "Bas ek step aur! 🎉\n\n"
                "Resume banane se pehle kuch extra add karna hai?\n\n"
                "• Achievement → \"Coding competition jeeta\"\n"
                "• Hobbies     → \"Cricket, Chess\"\n"
                "• Links       → \"linkedin.com/in/rahul\"\n"
                "• Certificate → \"AWS Certified Developer\"\n\n"
                "Ya likhein: **skip**"
            )
        else:
            reply = (
                "Almost done! 🎉\n\n"
                "Anything extra to add before I generate your resume?\n\n"
                "• Achievement → \"Won coding competition\"\n"
                "• Hobbies     → \"Cricket, Chess\"\n"
                "• Links       → \"linkedin.com/in/rahul\"\n"
                "• Certificate → \"AWS Certified Developer\"\n\n"
                "Or type: **skip**"
            )

        return save_and_reply(reply, chips=["skip"], next_step="extra_notes")

    # ==============================
    # STEP: EXTRA NOTES → GENERATE
    # ==============================
    if step == "extra_notes":

        if msg_lower != "skip":
            data["extra_notes"] = user_message

        jd_analysis         = data.get("jd_analysis", {})
        jd_skills           = data.get("skills", "")
        jd_summary_hint     = jd_analysis.get("summary_hint", "")
        jd_responsibilities = "\n".join(jd_analysis.get("responsibilities", []))
        jd_title            = jd_analysis.get("job_title", "")

        prompt = f"""
Generate a Europass ATS Professional Resume.
This resume MUST score 90+ on ATS for this specific job.

JOB CONTEXT:
- Job Title: {jd_title}
- Required Skills: {jd_skills}
- Key Responsibilities: {jd_responsibilities}
- ATS Summary Hint: {jd_summary_hint}
- Complete JD Text: {data.get("jd_text", "")}

CANDIDATE DATA:
Name: {data.get("full_name","")}
Address: {data.get("address","")}
Email: {data.get("email","")}
Phone: {data.get("phone","")}
Experience Type: {data.get("experience_type","")}
Total Experience: {data.get("total_exp","")}
Companies: {data.get("companies",[])}
Education: {data.get("education","")}
College: {data.get("college","")}
Year: {data.get("completion_year","")}
Languages: {data.get("languages","")}
Extra Notes: {data.get("extra_notes","")}

MANDATORY NUMBERED FORMAT — follow EXACTLY:

1. Name
[full name]

2. Contact Information
Address: [address]
Phone: [phone]
Email: [email]

3. Skills
[Read the COMPLETE JD text word by word — every line, every bullet point]
[Extract EVERY possible ATS keyword without missing any]
[This includes: languages, frameworks, databases, tools, cloud platforms, methodologies, soft skills, equipment, processes, certifications — anything that is a skill]
[Works for ALL job types: Software Developer, Driver, Cook, Welder, Doctor, Teacher, Accountant, Manager — every field]
[Group ALL extracted keywords into smart categories relevant to the job]
[Format STRICTLY: Category Name: skill1, skill2, skill3, skill4]
[Pack multiple related skills in ONE category line — keep each line compact]
[Use as many categories as needed to cover ALL keywords — do not skip any]
[NEVER write descriptions or sentences after skill names]
[NEVER write only skill name alone on a line without a category]
[NEVER miss any keyword from JD]

4. Languages
[Write languages from candidate data]
[NEVER leave empty]
[Format: Hindi, English]

5. Professional Summary
[JD keywords + candidate experience — 5-6 lines minimum]
[Mention job title, years of experience, company names]

6. Education
[degree]
[college]
[year]

7. Work Experience
[Each company separately with JD-matching responsibilities]
[If fresher: write relevant academic projects or internships]

WORK EXPERIENCE FORMAT — STRICTLY FOLLOW:
Company Name — Job Title
Duration
- Responsibility 1
- Responsibility 2

NEVER number companies like "1. Google" or "2. TCS"
NEVER write "(2023-2025)" in brackets after company name
Use ONLY this format:
Google — Software Developer
2023 - 2025
- Wrote clean, testable code...

8. Certifications
[Use ONLY what user provided in extra notes]
[If nothing provided: write exactly: "Please add your certifications here"]
[NEVER invent or assume any certificate]

9. Projects
[If job role is technical/IT/software/engineering:
 Use only projects user mentioned in extra notes
 If none provided: write "Please add your projects here"]
[If job role is non-technical like Driver/Cleaner/Welder/Cook/Helper/Guard/
 Electrician/Plumber/Mason/Delivery/Housekeeping/Mechanic/Labour:
 Write "Not applicable for this role"]
[If Management/Doctor/Teacher/Accountant/HR:
 Use only what user mentioned
 If none: write "Please add relevant projects or achievements here"]
[NEVER invent or assume any project]

EXTRA NOTES SMART EXTRACTION — VERY IMPORTANT:
Read extra_notes carefully and place in correct section:

If user mentions "certificate" or "certified" or "course":
→ Put in section 8. Certifications ONLY

If user mentions "achievement" or "award" or "medal" or "won" or "jeeta" or "prize":
→ Create section: 10. Achievements
→ NEVER put achievements in Certifications

If user mentions "hobby" or "hobbies" or "I like" or "interest":
→ Create section: 11. Hobbies
→ List as bullets

If user mentions "linkedin" or "portfolio" or "github" or "website":
→ Create section: 12. Links
→ List as bullets

THESE ARE SEPARATE SECTIONS — NEVER MIX THEM.
- Hobbies → section 11 (sidebar me jayega template me)
- Links → section 12 (sidebar me jayega template me)
- Achievements → section 10 (right side me jayega)
- Certificate → section 8 only
- NEVER mix achievements with certifications

STRICT RULES:
- Every section MUST start with its number and dot
- Skills MUST contain JD keywords
- Work experience responsibilities MUST use JD language
- Never skip numbering
- Return ONLY resume text, nothing else
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """You are a Europass ATS Resume Expert targeting 90+ ATS score.
        CRITICAL RULES:
        - NEVER use markdown formatting like **bold** or *italic* — plain text only
        - Use EXACT keywords from job description in skills, summary and experience
        - Repeat important JD keywords naturally multiple times
        - Skills must mirror JD language exactly
        - Summary must contain at least 5 JD keywords
        - Work experience bullets must use JD exact phrases
        - Always use numbered format 1. 2. 3. etc.
        - Return resume text only"""},
                {"role": "user",   "content": prompt}
            ]
        )

        final_resume = res.choices[0].message.content
        final_resume = re.sub(r"-{3,}", "", final_resume)
        final_resume = re.sub(r"_{3,}", "", final_resume)
        final_resume = re.sub(r"\*\*(.*?)\*\*", r"\1", final_resume)
        final_resume = re.sub(r"\*(.*?)\*", r"\1", final_resume)

        data["final_resume"]   = final_resume
        session["jd_step"]     = "jd_done"
        session["resume_data"] = data
        session["jd_data"]     = data
        session.modified       = True

        if lang_h:
            instruction = (
                "\n\n--------------------\n"
                "✅ Aapka JD-optimized resume ready hai!\n\n"
                "✏️ **Kuch badalna ho to bas likhein:**\n"
                "→ \"Summary ko aur lamba karo\"\n"
                "→ \"Achievement add karo: Team lead tha\"\n"
                "→ \"Hobbies add karo: Cricket\"\n"
                "→ \"Naya section: Notice Period - 30 din\"\n\n"
                "🎨 Ya **Template** button click karein download ke liye."
            )
        else:
            instruction = (
                "\n\n--------------------\n"
                "✅ Your JD-optimized resume is ready!\n\n"
                "✏️ **Want to edit? Just tell me:**\n"
                "→ \"Make summary longer\"\n"
                "→ \"Add Achievement: Led team of 5\"\n"
                "→ \"Add Hobbies: Cricket\"\n"
                "→ \"Add new section: Notice Period - 30 days\"\n\n"
                "🎨 Or click **Template** button to download."
            )

        final_resume += instruction
        data["final_resume"]   = final_resume
        session["resume_data"] = data
        session["jd_data"]     = data

        return jsonify({
            "reply"     : final_resume,
            "generating": True,
            "step"      : "jd_done"
        })

    # ==============================
    # EDIT MODE
    # ==============================
    if step == "jd_done":

        old_resume = data.get("final_resume","").split("--------------------")[0].strip()

        edit_prompt = f"""
You are a Resume Editor AI.

Current resume:
{old_resume}

User requested: "{user_message}"

STRICT RULES:
- Sections 1-9 keep SAME numbers always
- New sections start from 10 onward
- Return FULL updated resume
- Apply ONLY the requested change
- Keep all other content exactly same
- Maintain numbered format strictly
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Resume Editor AI. Return full updated resume only."},
                {"role": "user",   "content": edit_prompt}
            ]
        )

        updated = res.choices[0].message.content
        updated = re.sub(r"-{3,}", "", updated)
        updated = re.sub(r"_{3,}", "", updated)
        updated = re.sub(r"\*\*(.*?)\*\*", r"\1", updated)
        updated = re.sub(r"\*(.*?)\*", r"\1", updated)

        if lang_h:
            instruction = (
                "\n\n--------------------\n"
                "✅ Resume update ho gaya!\n\n"
                "✏️ **Aur changes chahiye to likhein.**\n"
                "🎨 Ya **Template** button click karein."
            )
        else:
            instruction = (
                "\n\n--------------------\n"
                "✅ Resume updated!\n\n"
                "✏️ **Need more changes? Just tell me.**\n"
                "🎨 Or click **Template** button to download."
            )

        updated += instruction
        data["final_resume"]   = updated
        session["resume_data"] = data
        session["jd_data"]     = data

        return jsonify({"reply": updated})

    return jsonify({"reply": "Something went wrong. Please try again."})

# ==============================
# JD SESSION HELPERS
# ==============================
@app.route("/reset-jd-session", methods=["POST"])
def reset_jd_session():
    session.pop("jd_step",      None)
    session.pop("jd_data",      None)
    session.pop("resume_data",  None)
    return {"status": "reset_done"}


@app.route("/check-jd-resume")
def check_jd_resume():
    data = session.get("jd_data", {})
    return {"ready": bool(data.get("final_resume"))}

if __name__ == "__main__":

    port = int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)