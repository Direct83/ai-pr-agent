from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from ..config import get_openai_model
from ..utils import extract_json

PROMPT = (
    "Ты security-ревьюер. На вход — unified diff PR. Ищи риски:\n"
    "- SQL-инъекции / XSS / Command Injection\n"
    "- Hardcoded секреты, ключи, пароли\n"
    "- Опасные вызовы (eval/exec/new Function и т.п.)\n"
    "- Ошибки авторизации/валидации/безопасных практик\n"
    "- Потенциальные утечки PII\n\n"
    "Ответ СТРОГО JSON:\n"
    "[\n"
    '  {"path":"file","line":123,"body":"почему риск и как исправить"},\n'
    '  {"path":"file","line_match":"фрагмент_строки_из_новой_версии","body":"почему риск и как исправить"}\n'
    "]\n\n"
    "Подсказка по путям: смотри заголовки вида '+++ b/<path>' в diff.\n\n"
    "Diff:\n"
    "<<<DIFF\n{diff}\nDIFF>>>"
)


def run_security_agent(diff: str) -> List[Dict[str, Any]]:
    llm = ChatOpenAI(model=get_openai_model(), temperature=0)
    resp = llm.invoke(PROMPT.format(diff=diff))
    data = extract_json(resp.content or "")
    return data if isinstance(data, list) else []
