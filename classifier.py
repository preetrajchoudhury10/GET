import re

GET_TITLE_PATTERNS = [
    r"graduate\s+engineer\s+trainee", r"graduate\s+engineering\s+trainee",
    r"graduate\s+trainee", r"\bget\b[\s\-]*(?:engineer|it|role)?",
    r"engineering\s+trainee", r"engineer\s+trainee", r"trainee\s+engineer",
    r"graduate\s+engineer", r"fresher\s+engineer", r"engineer\s+fresher",
    r"entry\s+level\s+engineer", r"junior\s+engineer",
    r"software\s+engineering\s+trainee", r"technology\s+trainee",
    r"technical\s+trainee", r"diploma\s+trainee", r"\bdet\b",
    r"management\s+trainee", r"graduate\s+apprentice", r"apprentice\s+trainee",
    r"assistant\s+engineer", r"system\s+engineer", r"systems?\s+engineer",
]

GET_EXCLUDE_PATTERNS = [
    r"\bsenior\b", r"\bsr[\.\s]", r"\blead\b", r"\bprincipal\b",
    r"\bstaff\b", r"\barchitect\b", r"\bmanager\b", r"\bdirector\b",
    r"\bvice\s+president\b", r"\bvp\b", r"\bhead\b",
    r"\bII\b", r"\bIII\b", r"\bIV\b", r"\bV\b",
    r"\(\s*\d+\s*\)", r"\d+\s*\+", r"\d+\s*(?:to|-)\s*\d+\s*(?:years?|yrs?)",
    r"\bintern\b", r"\binternship\b",
]

EXPERIENCE_RE = re.compile(
    r"(\d+)\s*(?:\+|to|-)?\s*(?:\d+)?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:relevant\s*)?(?:experience|exp\b)",
    re.IGNORECASE,
)

IT_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", ".net", "php",
    "sql", "mysql", "postgresql", "mongodb", "dbms", "nosql",
    "data structures", "algorithms", "dsa", "oops", "object oriented",
    "html", "css", "react", "angular", "vue", "node.js", "nodejs",
    "spring boot", "django", "flask", "fastapi", "rest api", "graphql",
    "microservices", "aws", "azure", "gcp", "cloud", "docker", "kubernetes",
    "jenkins", "terraform", "linux", "unix", "bash", "git", "github",
    "machine learning", "deep learning", "tensorflow", "pytorch", "nlp",
    "computer vision", "llm", "genai", "pandas", "numpy", "spark", "hadoop",
    "etl", "power bi", "tableau", "snowflake", "databricks", "data science",
    "data analyst", "data engineer", "selenium", "automation testing",
    "manual testing", "api testing", "android", "ios", "flutter",
    "react native", "swift", "kotlin", "scala", "golang", "rust", "devops",
    "ci/cd", "cybersecurity", "information security", "sap",
    "salesforce", "big data", "software development", "software engineer",
    "coding", "programming", "debugging", "full stack", "backend",
    "frontend", "web development", "application development",
    "computer science", "information technology", "it infrastructure",
    "network administration", "database administrator", "erp",
]

CORE_KEYWORDS = [
    "mechanical", "autocad", "solidworks", "catia", "creo", "ansys",
    "thermodynamics", "hvac", "hvac design", "cad", "cam", "cnc",
    "gd&t", "machine design", "automotive", "manufacturing", "production",
    "quality control", "quality assurance", "lean manufacturing",
    "six sigma", "civil", "structural", "surveying", "estimation",
    "site engineer", "construction", "concrete", "autocad civil",
    "electrical", "circuit design", "power systems", "transformer",
    "switchgear", "plc", "scada", "instrumentation", "control panel",
    "vlsi", "verilog", "vhdl", "embedded systems", "pcb", "microcontroller",
    "firmware", "electronics", "communication engineering", "rf",
    "chemical", "process engineering", "petrochemical", "refinery",
    "distillation", "heat exchanger", "metallurgy", "welding",
    "foundry", "textile", "aerospace", "aeronautical", "automobile",
    "mechatronics", "industrial engineering", "safety engineer",
    "environmental engineering", "mining", "petroleum", "polymer",
    "maintenance engineer", "plant operations", "utilities",
]


def is_get_title(title):
    t = title.lower()
    for pat in GET_EXCLUDE_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return False
    for pat in GET_TITLE_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def is_entry_level_description(description, max_years=3):
    if not description:
        return True
    for m in EXPERIENCE_RE.findall(description):
        try:
            if int(m) > max_years:
                return False
        except (TypeError, ValueError):
            continue
    return True


NON_ENG_TITLE_KEYWORDS = [
    "sales", "marketing", "hospitality", "paramedical", "nursing", "pharma",
    "hr ", "human resources", "finance", "accounting", "legal", "operations",
    "business development", "telecaller", "relationship", "insurance",
]


def classify(job):
    """Return 'GET[IT]' or 'GET[Non-IT]' for a job already known to be a GET role."""
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()

    if any(kw in title for kw in NON_ENG_TITLE_KEYWORDS):
        return "GET[Non-IT]"

    it_score = sum(1 for kw in IT_KEYWORDS if kw in title) * 3
    it_score += sum(1 for kw in IT_KEYWORDS if kw in desc)
    core_score = sum(1 for kw in CORE_KEYWORDS if kw in title) * 3
    core_score += sum(1 for kw in CORE_KEYWORDS if kw in desc)

    if it_score >= core_score:
        return "GET[IT]"
    return "GET[Non-IT]"


def classify_job(job):
    """Full pipeline: is it a GET role, and IT or Non-IT. Returns tag or None."""
    if not is_get_title(job.get("title", "")):
        return None
    if not is_entry_level_description(job.get("description", "")):
        return None
    return classify(job)
