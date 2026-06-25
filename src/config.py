import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Groq
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "llama3-70b-8192"

# Paths
BASE_DIR = Path(__file__).parent.parent
CHROMA_DIR = BASE_DIR / ".codeguard_db"
CHROMA_DIR.mkdir(exist_ok=True)

# Chunking
MAX_CHUNK_LINES = 60
OVERLAP_LINES = 10
TOP_K_CONTEXT = 8

# Collections
COLLECTION_NAME = "codebase"
