import os
import re
import json
import io
import razorpay
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
import io
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

    # 🔥 FIX: If English → no translation
    if lang.strip().lower().startswith("e"):
        return question

    # 🔥 Only Hindi users get translation
    prompt = f"""
Translate this question naturally into user's language.

User language: {lang}

Rules:
- Hindi → Hinglish style
- English → Full English

Question: {question}

Return ONLY translated question.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}]
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

# ===============================
# API Chat Endpoint
# ===============================
@app.route("/api/chat", methods=["POST"])
def api_chat():
    user_message = request.json.get("message", "").strip()

    step = session.get("step", "language")
    data = session.get("resume_data", {})

    msg_lower = user_message.lower()

    if user_message == "__start__":
        session["step"] = "language"
        session["resume_data"] = {}
        return jsonify({"reply": "👋 Which language do you want? (English / Hindi)"})


    # ===============================
    # STEP 1: Language
    # ===============================
    if step == "language":
        data["language"] = user_message
        session["step"] = "country"

        q = "Great! Which country are you applying for?"
        return jsonify({"reply": ask_in_language(data["language"], q)})

    # STEP 2: Apply Country
    # ===============================
    if step == "country":
        data["apply_country"] = user_message
        session["step"] = "job_role"

        q = "What job role are you applying for?"

        return jsonify({
            "reply": ask_in_language(data["language"], q)
        })

    # ===============================
    # STEP 3: Job Role
    # ===============================
    if step == "job_role":
        data["job_role"] = user_message
        session["step"] = "experience_type"

        q = "Are you fresher or experienced?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 4: Experience Type
    # ===============================
    if step == "experience_type":
        data["experience_type"] = user_message.lower()

        if "exp" in data["experience_type"]:
            data["companies"] = []
            session["step"] = "total_exp"
            q = "How many years of total experience do you have? (or type: skip)"
            return jsonify({"reply": ask_in_language(data["language"], q)})

        session["step"] = "full_name"
        q = "What is your full name?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 4A: Total Experience
    # ===============================
    if step == "total_exp":

        if user_message.lower() == "skip":
            session["step"] = "full_name"
            q = "What is your full name?"
            return jsonify({"reply": ask_in_language(data["language"], q)})

        data["total_exp"] = user_message
        session["step"] = "company_name"

        q = "Which company did you work in most recently? (type:company name/ skip / self / business)"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 4B: Company Name (SELF-EMPLOYED FIX)
    # ===============================
    if step == "company_name":

        if user_message.lower() == "skip":
            session["step"] = "full_name"
            q = "What is your full name?"
            return jsonify({"reply": ask_in_language(data["language"], q)})

        if (
            "khud" in msg_lower
            or "own" in msg_lower
            or "self" in msg_lower
            or "freelance" in msg_lower
            or "business" in msg_lower
        ):
            company = {"name": "Self-Employed"}
        else:
            company = {"name": user_message}

        data["companies"].append(company)

        session["step"] = "company_duration"
        q = "In this company, you worked from which year to which year?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 4C: Company Duration
    # ===============================
    if step == "company_duration":
        data["companies"][-1]["duration"] = user_message
        session["step"] = "add_more_company"

        translated = ask_in_language(data["language"], "Do you want to add another company?")
        return jsonify({"reply": translated + " (yes/no)"})


    # ===============================
    # STEP 4D: Add More Company
    # ===============================
    if step == "add_more_company":
        answer = strict_yes_no(user_message)

        if answer is None:
            return jsonify({"reply": "⚠ Please answer only: yes or no"})

        if answer == "yes":
            session["step"] = "company_name"
            q = "Next company name?"
            return jsonify({"reply": ask_in_language(data["language"], q)})

        session["step"] = "full_name"
        q = "What is your full name?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 5: Name
    # ===============================
    if step == "full_name":
        data["full_name"] = clean_text(user_message)
        session["step"] = "address"

        q = "What is your full address?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 6: Address
    # ===============================
    if step == "address":
        data["address"] = user_message

        if "india" in user_message.lower():
            data["current_country"] = "India"

        session["step"] = "email"
        q = "Email address?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 7: Email
    # ===============================
    if step == "email":

        if not is_valid_email(user_message):
            return jsonify({"reply": "⚠ Please enter a valid email address (example: name@gmail.com)"})

        data["email"] = user_message
        session["step"] = "phone"

        q = "Phone number?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 8: Phone → Education
    # ===============================
    if step == "phone":
        data["phone"] = user_message
        session["step"] = "education"

        q = "What is your highest qualification or degree?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 9: Education
    # ===============================
    if step == "education":
        data["education"] = user_message
        session["step"] = "college"

        q = "Which college/university did you study in?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 10: College
    # ===============================
    if step == "college":
        data["college"] = user_message
        session["step"] = "completion_year"

        q = "What is your completion year?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 11: Completion Year → Languages
    # ===============================
    if step == "completion_year":
        data["completion_year"] = user_message
        session["step"] = "languages"

        q = "Which languages do you know?"
        return jsonify({"reply": ask_in_language(data["language"], q)})


    # ===============================
    # STEP 12: Languages
    # ===============================
    if step == "languages":
        data["languages"] = user_message
        session["step"] = "skills"

        q = "Do you know your skills or should I generate ATS-friendly skills? (type: generate)"
        return jsonify({"reply": ask_in_language(data["language"], q)})


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

        session["step"] = "extra_notes"

        q = "Any extra notes? (Certificate, Availability)"
        return jsonify({"reply": ask_in_language(data["language"], q)})


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

        --------------------------------------------------

        FIXED SECTIONS (Never change numbers)

        1. Name

        Write full name only under heading.
        Heading MUST always appear.
        Never skip this heading.

        Example:
        1. Name
        Suhel

        --------------------------------------------------

        2. Contact Information

        Write in this format only:

        Address: ___
        Phone: ___
        Email: ___

        Do NOT merge into one line.
        Do NOT change order.

        --------------------------------------------------

        3. Skills

        Rules:

        • Use bullet points only.
        • Never number skills.
        • Summarize skills into 5–6 main lines.
        • Categorize if technical role.
        • Keep ATS-friendly keywords.

        Example:

        • Programming Languages: Java, Python, C++
        • Web Development: HTML, CSS, JavaScript
        • Database Management: SQL, MySQL
        • Tools: Git, Docker
        • Soft Skills: Communication, Teamwork

        --------------------------------------------------

        4. Languages

        Write like:

        • Hindi (Native)
        • English (Fluent)

        --------------------------------------------------

        5. Professional Summary

        Write in paragraph format.
        Strong ATS Europass tone.

        IMPORTANT ADDITIONAL RULES:

        • Mention total years of experience if provided.
        • Mention company names if user worked in companies.
        • Mention job role.
        • Highlight technical strengths.
        • Minimum 4–6 lines summary.

        Example tone:

        “Software Engineer with 5 years of experience working at Google and Microsoft…”

        --------------------------------------------------

        6. Education

        Write in this format:

        Degree  
        Institution  
        Completion Year  

        STRICT EDUCATION RULES:

        • Do NOT compress into one line.
        • Do NOT bullet education.
        • Maintain vertical Europass format.
        • Degree must appear first.
        • Institution second.
        • Year third.
        • Use full university name if provided.
        • Do NOT shorten institution names.

        --------------------------------------------------

        7. Work Experience

        If fresher → write professionally.

        If experienced → follow STRICT rules:

        WORK EXPERIENCE RULES:

        • Show EACH company separately.
        • Company name MUST appear.
        • Duration MUST appear.
        • Role MUST appear.
        • Add 2–3 responsibility points.
        • Use bullet points for responsibilities.

        FORMAT EXAMPLE:

        Software Engineer — Google  
        2022 – 2025  

        • Developed scalable applications  
        • Worked on cloud systems  

        Software Engineer — Microsoft  
        2020 – 2022  

        • Built enterprise software  
        • Improved performance  

        Do NOT merge multiple companies into one paragraph.

        --------------------------------------------------

        8. Certifications

        Rules:

        • Write only user-provided certificates.
        • If user gave certificate in extra notes → move here.
        • Never place certificates in extra notes.
        • If none → write placeholder.

        CERTIFICATION EXPANSION RULE:

        • Expand certificate slightly if possible.
        • Mention issuing body if known.
        • Example:

        O Level Certificate — NIELIT

        If body unknown → keep professional format.

        --------------------------------------------------

        9. Projects

        If none → write placeholder.

        If provided → bullet format.

        --------------------------------------------------

        10. (Reserved for future dynamic sections)

Do NOT generate References section
unless user specifically provides it.
        --------------------------------------------------

        DYNAMIC SECTIONS RULE

        If user provides any extra info like:

        • Achievements  
        • Awards  
        • Availability  
        • Visa Status  
        • Notice Period  
        • Volunteer Work  
        • Publications  

        Create NEW numbered sections starting from 10 onward.

        Example:

        10. Achievements  
        11. Availability  

        Do NOT create “Extra Notes” heading.

        --------------------------------------------------

        NUMBER STABILITY RULE (VERY IMPORTANT)

        • Fixed sections 1–10 must ALWAYS keep same numbers.
        • Never renumber them.
        • Even if content removed → number stays reserved.

        Example:

        If Certifications removed:

        8. Certifications  
        (Removed as per user request)

        Do NOT shift Projects to 8.

        --------------------------------------------------

        EDIT SAFETY RULE

        If user later edits resume:

        • Remove section → keep number + heading.
        • Update section → update only that section.
        • Add new info → create new number 11+.
        • Never disturb other sections.

        --------------------------------------------------

        STRICT RULES

        • Never merge sections.
        • Never skip numbering.
        • Never renumber after deletion.
        • Never convert bullets into numbers.
        • Follow Europass ATS format.
        • Follow user answers exactly.

        --------------------------------------------------

        User Data:
        {data}

        Return ONLY resume text.
        """

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Europass ATS Resume Expert."},
                {"role": "user", "content": prompt}
            ]
        )

        final_resume = res.choices[0].message.content
        final_resume = re.sub(r"-{3,}", "", final_resume)
        final_resume = re.sub(r"_{3,}", "", final_resume)
        data["final_resume"] = final_resume


        # ==================================================
        # ✅ FIXED JSON CONVERTER (RESPONSIBILITIES INCLUDED)
        # ==================================================
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
         "extra_sections":[
           {{
             "title":"",
             "content":[]
           }}
         ]
        }}

        Return ONLY JSON.
        """

        json_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": json_prompt}
            ]
        )

        ai_text = json_res.choices[0].message.content.strip()

        # =========================
        # EMPTY RESPONSE CHECK
        # =========================
        if not ai_text:

            return jsonify({
                "error": "AI response empty. Please retry."
            }), 500

        # =========================
        # SAFE JSON PARSE
        # =========================
        try:

            data["resume_json"] = json.loads(ai_text)
        except json.JSONDecodeError:
            return jsonify({
                "error": "AI returned invalid JSON. Retry."
            }), 500

        # ✅ Final Professional Instruction Message

        if data["language"].lower().startswith("h"):
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Aapka resume text format me ready hai.\n"
                "Aap yahan content add ya edit kar sakte hain.\n"
                "⚠ Agar koi section hatana ho to template select karne ke baad manually remove karein.\n"
                "Warna 🎨 Template icon par click karke design choose karein."
            )
        else:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Your resume is ready in text format.\n"
                "You may edit or add content here.\n"
                "⚠ If you want to remove any section, please remove it manually after selecting a template.\n"
                "Otherwise click 🎨 Template icon to select a design."
            )

        final_resume += instruction_msg
        session["resume_data"] = data

        return jsonify({"reply": final_resume})


    # ===============================
    # EDIT MODE AFTER RESUME
    # ===============================
    if step == "done":

        old_resume = data.get("final_resume", "").split("--------------------")[0].strip()

        edit_prompt = f"""
        You are a Resume Editor AI.

        Here is the current numbered resume:

        {old_resume}

        User requested this update:

        "{user_message}"

        --------------------------------------------------

        STRICT NUMBER PROTECTION RULES:

        Sections 1–9 are FIXED.

        NEVER change their numbers.
        NEVER move them.
        NEVER merge them.
        NEVER delete numbering.

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

        --------------------------------------------------

        EDIT RULES:

        • If user adds a NEW heading → create NEW section.
        • Always place NEW section AFTER section 9.
        • Start numbering from 10 onward.
        • Do NOT insert new data inside existing sections.
        • Do NOT replace Projects.
        • Do NOT shift Summary.
        • Do NOT cut any section content.

        --------------------------------------------------

        DYNAMIC SECTION RULE:

        Examples of new headings:

        • Achievements
        • Awards
        • Availability
        • Visa Status
        • Notice Period
        • Volunteer Work

        They must appear like:

        10. Achievements  
        11. Awards  

        --------------------------------------------------

        OUTPUT RULES:

        • Return FULL updated resume.
        • Keep ALL existing text unchanged.
        • Apply ONLY requested edit.
        • Maintain numbering stability.
        """

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Resume Editor AI."},
                {"role": "user", "content": edit_prompt}
            ]
        )

        updated_resume = res.choices[0].message.content
        data["final_resume"] = updated_resume
        # ✅ Add instruction message again after edit

        if data["language"].lower().startswith("h"):
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Resume update ho gaya hai.\n"
                "Aap aur edit/add kar sakte hain.\n"
                "⚠ Agar koi section hatana ho to template select karne ke baad manually remove karein.\n"
                "Warna 🎨 Template icon par click karke design choose karein."
            )
        else:
            instruction_msg = (
                "\n\n--------------------\n"
                "✅ Resume updated successfully.\n"
                "You may edit or add more content.\n"
                "⚠ If you want to remove any section, please remove it manually after selecting a template.\n"
                "Otherwise click 🎨 Template icon to select a design."
            )

        updated_resume += instruction_msg

        session["resume_data"] = data

        return jsonify({"reply": updated_resume})

    return jsonify({"reply": "Something went wrong."})

# ===============================
# 🔥 NUMBER RESUME PARSER
# ===============================
def parse_numbered_resume(text):

    sections = {}

    # 🔥 Strict heading match (line start only)
    pattern = r"^\s*(\d+)\.\s+(.+)$"

    matches = list(re.finditer(pattern, text, re.MULTILINE))

    for i in range(len(matches)):

        start = matches[i].end()

        number = matches[i].group(1).strip()
        title = matches[i].group(2).strip()

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

    data = session.get("resume_data", {})

    if data.get("final_resume"):
        return {"ready": True}
    else:
        return {"ready": False}
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

    if row:
        last_payment_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")

        if datetime.now() - last_payment_time < timedelta(minutes=30):
            return jsonify({
                "skip_payment": True
            })

    try:
        data = request.get_json()
        print("DATA RECEIVED:", data)

        include_cover = data.get("cover_letter", False)
        amount = 5900 if include_cover else 4900

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
        # 1️⃣ Signature Verify
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })

        # 2️⃣ Fetch payment details from Razorpay (extra security)
        payment = razorpay_client.payment.fetch(razorpay_payment_id)

        amount = payment["amount"]
        download_token = str(uuid.uuid4())
        # ✅ Amount validation
        if amount not in [4900, 5900]:
            return jsonify({"status": "invalid_amount"}), 400

        # Detect cover letter purchase
        include_cover = True if amount == 5900 else False

        # 3️⃣ Save payment in database
        conn = sqlite3.connect("payments.db")
        c = conn.cursor()

        # Prevent duplicate payment insert
        c.execute("SELECT * FROM payments WHERE payment_id = ?", (razorpay_payment_id,))
        existing = c.fetchone()

        if existing:
            conn.close()
            return jsonify({"status": "already_recorded"})

        c.execute("""
            INSERT INTO payments 
            (order_id, payment_id, signature, amount, cover_letter,download_token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
            amount,
            include_cover,
            download_token,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        session["paid"] = True
        session["paid_time"] = datetime.now().isoformat()
        session.modified = True

        return jsonify({"status": "success",
                        "token":download_token})

    except Exception as e:
        print("VERIFY ERROR:",e)

        return jsonify({"status": "failed", "error":str(e)}), 400

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
def download_resume():
    # 🔒 Payment check
    if not session.get("paid"):
        return jsonify({
            "error": "Payment required"
        }), 403

    data = request.get_json()
    template_path = data.get("template")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--single-process", "--disable-gpu"]
        )
        context = browser.new_context(viewport={"width": 1200, "height": 1600})

        session_cookie = request.cookies.get("session")

        if session_cookie:
            context.add_cookies([{
                "name": "session",
                "value": session_cookie,
                "domain": request.host.split(":")[0],
                "path": "/"
            }])

        page = context.new_page()
        page.set_default_timeout(60000)

        edited_html = data.get("html")

        if not edited_html:
            return "NO edited content found", 400

        # 🔥 यहाँ fallback नहीं चाहिए
        page.goto(
            f"http://{request.host}{template_path}",
            wait_until="networkidle"
        )
        page.add_style_tag(content="""
            .watermark-preview {
                display: none !important;
            }
        """)

        if edited_html:
            page.evaluate("""
                (htmlContent) => {
                    const container = document.querySelector(".container");
                    container.outerHTML = htmlContent;

                    document.querySelectorAll('.watermark-preview')
                .forEach(el => el.remove());
                }
            """, edited_html)

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
        page.close()
        context.close()
        browser.close()



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
    resume_data["edited_html"] = html_content
    resume_data["template_path"] = template_path

    session["resume_data"] = resume_data
    session.modified = True

    return {"status": "saved"}


import os
from flask import request, jsonify

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload-photo", methods=["POST"])
def upload_photo():
    file = request.files.get("photo")

    if not file:
        return jsonify({"status": "error"})

    filepath = os.path.join("static/uploads", "profile.jpg")
    file.save(filepath)

    session["photo_url"] = "/static/uploads/profile.jpg"

    return jsonify({
        "status": "success",
        "url": "/static/uploads/profile.jpg"
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
if __name__ == "__main__":

    port = int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)