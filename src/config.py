import os
from dotenv import load_dotenv

# Загружаем .env для локальной разработки
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# GitHub (в GitHub Actions GITHUB_REPOSITORY подставится автоматически)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # 'owner/repo' или None

# Ник-упоминание агента
BOT_MENTION = os.getenv("BOT_MENTION", "@ai")

REVIEW_ONLY_PREFIXES = [p.strip() for p in os.getenv("REVIEW_ONLY_PREFIXES", "src/").split(",") if p.strip()]

def require_var(name: str, value: str | None):
    if not value:
        raise RuntimeError(f"Ожидалась переменная окружения {name}")
    return value

def get_openai_model() -> str:
    return OPENAI_MODEL
