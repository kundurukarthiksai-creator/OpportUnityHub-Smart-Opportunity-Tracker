import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("config")

# Load environment variables from .env if it exists
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    load_dotenv(override=True) # standard lookup
    logger.warning("No .env file found at project root. Using system/environment variables.")

# Suppress some verbose library logging
logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

class Settings:
    # Supabase config
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Security & Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-temporary-dev-key-change-it")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

    # AI Configurations
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini").lower() # default to gemini if both or neither configured

    def validate(self):
        """Validate critical configuration parameters and log errors."""
        missing = []
        if not self.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not self.SUPABASE_KEY:
            missing.append("SUPABASE_KEY")
        if not self.GOOGLE_CLIENT_ID or not self.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_ID/SECRET")
        if not self.GEMINI_API_KEY and not self.OPENAI_API_KEY:
            missing.append("GEMINI_API_KEY or OPENAI_API_KEY")
        
        if missing:
            logger.error(
                f"CRITICAL MISSING CONFIGURATION(S): {', '.join(missing)}. "
                "Please configure these in your .env file."
            )
            return False
        return True

settings = Settings()
settings.validate()
