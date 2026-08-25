import streamlit as st
import PyPDF2
import requests
import google.generativeai as genai
import json

def extract_text_from_pdf(file):
    """Reads the uploaded PDF and extracts raw text."""
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted
    return text

def fetch_live_jobs_adzuna(keywords, location, min_salary, app_id, app_key):
    """Fetches live job listings from the Adzuna API."""
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 10,
        "what": keywords,
        "where": location,
        "salary_min": min_salary,
        "content-type": "application/json"
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        jobs = []
        for job in data.get("results", []):
            jobs.append({
                "title": job.get("title", "Unknown Title"),
                "company": job.get("company", {}).get("display_name", "Unknown Company"),
                "location": job.get("location", {}).get("display_name", location),
                "salary_range": f"${int(job.get('salary_min', 0)):,} - ${int(job.get('salary_max', 0)):,}" if job.get('salary_min') else "Salary not listed",
                "description": job.get("description", "No description provided."),
                "apply_url": job.get("redirect_url", "#")
            })
        return jobs
    else:
        st.error(f"Error fetching jobs from Adzuna: {response.status_code}")
        return []

def calculate_match_score(resume_text, job_description, api_key):
    """Sends the resume and job description to Gemini to calculate a fit score."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
    
    prompt = f"""
    You are an expert technical recruiter. I will provide a candidate's RESUME TEXT and a JOB DESCRIPTION.
    Compare the candidate's skills and experience to the job requirements.
    
    RESUME TEXT:
    {resume_text}
    
    JOB DESCRIPTION:
    {job_description}
    
    Provide your evaluation strictly in the following JSON format:
    {{
        "score": <an integer between 0 and 100 representing the match percentage>,
        "reasoning": "<a 2-sentence explanation of why they are a good or bad fit, highlighting missing or matching key skills>"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        return result
    except Exception as e:
        return {"score": 0, "reasoning": f"Error analyzing match: {str(e)}"}

# --- User Interface Setup ---
st.set_page_config(page_title="Live AI Job Matcher", layout="wide")
st.title("Live AI-Powered Job Matcher")
st.write("Upload your resume and let the AI score your fit for active roles.")

# Securely load API keys from Streamlit Secrets
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    adzuna_id = st.secrets["ADZUNA_APP_ID"]
    adzuna_key = st.secrets["ADZUNA_APP_KEY"]
except KeyError:
    st.error("API keys are missing. Please configure Streamlit Secrets in your cloud dashboard to continue.")
    st.stop()

# Input Parameters
col1, col2, col3 = st.columns(3)
with col1:
    keywords_input = st.text_input("Job Title / Keywords", value="Manufacturing Engineer")
with col2:
    locations_input = st.text_input("Desired Location", value="Chandler, AZ")
with col3:
    salary_expectation = st.number_input("Minimum Salary ($)", min_value=0, value=110000, step=5000)

uploaded_resume = st.file_uploader("Upload Resume (PDF)", type=["pdf"])

# Run Search
if st.button("Find Matches", type="primary"):
    if not uploaded_resume:
        st.error("Please upload a PDF resume.")
    else:
        # Step 1: Parse the Resume
        with st.spinner("Extracting text from resume..."):
            resume_text = extract_text_from_pdf(uploaded_resume)
            
        # Step 2: Fetch Jobs
        with st.spinner(f"Fetching live '{keywords_input}' jobs in {locations_input}..."):
            jobs = fetch_live_jobs_adzuna(keywords_input, locations_input, salary_expectation, adzuna_id, adzuna_key)
            
        if not jobs:
            st.warning("No jobs found matching your criteria. Try broadening your search.")
        else:
            # Step 3: Score Matches via LLM
            with st.spinner("AI is analyzing your fit for these roles (this may take a minute)..."):
                for job in jobs:
                    evaluation = calculate_match_score(resume_text, job["description"], gemini_key)
                    job["match_score"] = evaluation.get("score", 0)
                    job["reasoning"] = evaluation.get("reasoning", "No reasoning provided.")
                
                # Sort jobs by highest match score
                jobs = sorted(jobs, key=lambda x: x["match_score"], reverse=True)
                
                st.success("Analysis complete!")
                st.markdown("---")
                
                # Step 4: Display Results
                for job in jobs:
                    st.subheader(f"{job['title']} @ {job['company']}")
                    
                    score = job['match_score']
                    color = "green" if score >= 80 else "orange" if score >= 50 else "red"
                    
                    st.markdown(f"""
                    - **Location:** {job['location']}
                    - **Estimated Salary:** {job['salary_range']}
                    - **AI Match Score:** :{color}[**{score}%**]
                    
                    **AI Feedback:** {job['reasoning']}
                    """)
                    
                    st.link_button(f"Apply to {job['company']}", job['apply_url'])
                    st.markdown("---")
