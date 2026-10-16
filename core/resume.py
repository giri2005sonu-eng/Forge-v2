"""Resume reader for the recommendation helper. Plain code, no AI: the same file always gives the same result.

Privacy: the file is parsed in memory. Only the detected skills (each with a short evidence snippet) are kept.
The raw text is never stored, cached to disk or sent to any API."""
import io
import re

from .data import PROJECTS

MAX_BYTES = 5_000_000
MAX_CHARS = 60_000
# skill -> (label, regex, interest tag or None, counts toward electronics experience)
SKILLS = {
    "arduino": ("Arduino", r"\barduino\b|\batmega\d*\b", None, True),
    "esp32": ("ESP32 / ESP8266", r"\besp-?32\b|\besp-?8266\b", "wireless", True),
    "embedded": ("Embedded / firmware", r"\bembedded\b|\bfirmware\b|\bmicrocontrollers?\b|\bstm32\b|\brtos\b", None, True),
    "sensors": ("Sensors", r"\bsensors?\b|\bultrasonic\b|\bhc-?sr04\b|\binfrared\b|\blidar\b|\bimu\b", "sensors", True),
    "motor_control": ("Motors / PID control", r"\bpid\b|\bpwm\b|\bmotor drivers?\b|\bl298n?\b|\btb6612\w*|\bmotor control\b", "mechanics", True),
    "pcb_soldering": ("Soldering / PCB", r"\bsolder\w*|\bpcb\b|\bkicad\b|\baltium\b", None, True),
    "line_following": ("Line following", r"line[- ]follow(?:er|ers|ing)\b", "sensors", False),
    "obstacle_avoidance": ("Obstacle avoidance", r"obstacle[- ](?:avoid\w*|detect\w*)", "sensors", False),
    "bluetooth": ("Bluetooth", r"\bbluetooth\b|\bhc-?0[56]\b|\bble\b", "wireless", False),
    "wireless_other": ("Wi-Fi / MQTT / LoRa", r"\bwi-?fi\b|\bmqtt\b|\blora\b", "wireless", False),
    "python": ("Python", r"\bpython\b", None, False),
    "ml": ("Machine learning", r"\bmachine learning\b|\bdeep learning\b|\bneural\b|\btensorflow\b|\bpytorch\b|\bscikit", "ai", False),
    "vision": ("Computer vision", r"\bopencv\b|\bcomputer vision\b|\byolo\b", "ai", False),
    "ros": ("ROS", r"(?-i:\bROS ?2?\b)", None, False),
    "cad": ("CAD / 3D printing", r"\bcad\b|\bsolidworks\b|\bfusion 360\b|\b3d[- ]print\w*|\bfreecad\b", "mechanics", False),
}
_RX = {name: re.compile(spec[1], re.I) for name, spec in SKILLS.items()}

# Skills each project actually exercises. Every project in core.data.PROJECTS must be listed (a test enforces this).
PROJECT_SKILLS = {
    "line_follower": {"line_following", "sensors", "motor_control", "arduino", "embedded"},
    "obstacle_avoider": {"obstacle_avoidance", "sensors", "motor_control", "arduino", "embedded"},
    "bluetooth_car": {"bluetooth", "esp32", "motor_control", "wireless_other", "embedded"},
}
# The skill that means "you have already done something like this project".
DIRECT = {"line_follower": "line_following", "obstacle_avoider": "obstacle_avoidance", "bluetooth_car": "bluetooth"}


def extract_text(name, data):
    """Return plain text from a PDF, DOCX or TXT upload. Raises ValueError with a message safe to show the user."""
    if len(data) > MAX_BYTES:
        raise ValueError("File is larger than 5 MB.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext == "pdf":
        from pypdf import PdfReader
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        except Exception as error:
            raise ValueError(f"Could not read this PDF ({type(error).__name__}).") from error
    elif ext == "docx":
        import docx
        try:
            document = docx.Document(io.BytesIO(data))
        except Exception as error:
            raise ValueError(f"Could not read this DOCX ({type(error).__name__}).") from error
        cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
        text = "\n".join([p.text for p in document.paragraphs] + cells)
    elif ext in ("txt", "md"):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Upload a PDF, DOCX or TXT file.")
    text = text[:MAX_CHARS].strip()
    if not text:
        raise ValueError("No readable text found. Scanned or image-only resumes are not supported.")
    return text


def _snippet(text, match, pad=32):
    return " ".join(text[max(0, match.start() - pad):match.end() + pad].split())


def analyze(text):
    """Find known skills. Returns {skills: {name: evidence}, level: 1-3 or None, interests: [tags]}. Raw text is not kept."""
    skills = {}
    for name, rx in _RX.items():
        match = rx.search(text)
        if match:
            skills[name] = _snippet(text, match)
    hardware = sum(1 for name in skills if SKILLS[name][3])
    level = 3 if hardware >= 4 else 2 if hardware >= 1 else None
    interests = list(dict.fromkeys(SKILLS[name][2] for name in skills if SKILLS[name][2]))
    return dict(skills=skills, level=level, interests=interests)


def affinity(project_key, R):
    """0-1: how much of what this project exercises shows up on the resume. The project's own skill counts double."""
    if not R:
        return 0.0
    needed = PROJECT_SKILLS.get(project_key, set())
    direct = DIRECT.get(project_key)
    weight = lambda name: 2 if name == direct else 1
    total = sum(weight(name) for name in needed)
    return sum(weight(name) for name in needed & set(R["skills"])) / total if total else 0.0


def matches(project_key, R):
    """[(label, evidence)] for this project's skills found on the resume, in a stable order."""
    if not R:
        return []
    found = PROJECT_SKILLS.get(project_key, set()) & set(R["skills"])
    return [(SKILLS[name][0], R["skills"][name]) for name in sorted(found)]


def already_mentions(project_key, R):
    """True if the resume already mentions the exact thing this project builds."""
    return bool(R) and DIRECT.get(project_key) in R["skills"]
