from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from ..config import get_openai_model
from ..utils import extract_json
from pathlib import Path

PROMPT = (
    "Ты строгий ревьюер code style. На вход — unified diff PR (несколько файлов).\n"
    "Правила проекта (применяй при анализе):\n"
    "<<<RULES\n{rules}\nRULES>>>\n\n"
    "Нужно найти нарушения code style проекта и привязать комментарии к строкам НОВОЙ версии.\n\n"
    "Правила ответа:\n"
    "- Верни СТРОГО JSON-массив объектов:\n"
    "[\n"
    '  {"path":"relative/file/path.ext","line_match":"ТОЧНЫЙ_ФРАГМЕНТ_СТРОКИ_ИЗ_НОВОЙ_ВЕРСИИ","body":"кратко суть проблемы"}\n'
    "]\n"
    "- Возвращай только объекты с полем \"line_match\". Поле \"line\" НЕ ИСПОЛЬЗУЙ.\n"
    "- \"line_match\" — короткий фрагмент, встречающийся в новой версии без префикса '+'.\n"
    "Подсказка по путям: смотри заголовки вида '+++ b/<path>' в diff.\n\n"
    "Diff:\n"
    "<<<DIFF\n{diff}\nDIFF>>>"
)


def run_codestyle_agent(diff: str) -> List[Dict[str, Any]]:
    llm = ChatOpenAI(model=get_openai_model(), temperature=0)
    rules_text = Path(".github/ai-review.json").read_text(encoding="utf-8")
    prompt_text = PROMPT.replace("{diff}", diff).replace("{rules}", rules_text)
    resp = llm.invoke(prompt_text)
    data = extract_json(getattr(resp, "content", ""))
    return data if isinstance(data, list) else []
