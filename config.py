"""
Configuració del generador de presentacions MENAG.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carregar variables d'entorn
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Paths del projecte
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / "cache"
IMAGES_EXTRACTED_DIR = CACHE_DIR / "images" / "extracted"
IMAGES_GENERATED_DIR = CACHE_DIR / "images" / "generated"

# Configuració d'extracció d'imatges
MIN_IMAGE_WIDTH = 200  # píxels
MIN_IMAGE_HEIGHT = 200  # píxels

# Configuració de models
CLAUDE_MODEL = "claude-opus-4-5-20251101"  # Opus 4.5 per estructurar i orquestrar
GEMINI_ANALYSIS_MODEL = "gemini-3-flash-preview"  # Per analitzar imatges (Google AI Studio)
GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"  # Nano Banana per generar imatges (Google AI Studio)

# Configuració d'API
MAX_TOKENS = 32000  # Tokens màxims per evitar truncament (augmentat per presentacions llargues)
API_TIMEOUT = 600  # Timeout en segons (10 minuts per presentacions grans)

# Configuració de presentació
TARGET_SLIDES = 20
TARGET_DURATION_MINUTES = 20

# Validar que les API keys existeixen
def validate_config():
    """Valida que la configuració sigui correcta."""
    errors = []

    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY no està configurada a .env")

    if not GOOGLE_API_KEY:
        errors.append("GOOGLE_API_KEY no està configurada a .env")

    if errors:
        raise ValueError("Errors de configuració:\n" + "\n".join(errors))

    # Crear directoris si no existeixen
    for dir_path in [INPUT_DIR, OUTPUT_DIR, IMAGES_EXTRACTED_DIR, IMAGES_GENERATED_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

    return True
