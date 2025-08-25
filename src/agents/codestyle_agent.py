from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from ..config import get_openai_model
from ..utils import extract_json

PROMPT = (
    "Ты строгий ревьюер code style. На вход — unified diff PR (несколько файлов).\n"
    "Нужно найти нарушения code style проекта и привязать комментарии к строкам новой версии.\n\n"
    "Правила ответа:\n"
    "- Верни СТРОГО JSON-массив объектов:\n"
    "[\n"
    '  {"path":"relative/file/path.ext","line":123,"body":"кратко суть проблемы"},\n'
    '  {"path":"relative/file/path.ext","line_match":"ТОЧНЫЙ_ФРАГМЕНТ_СТРОКИ_ИЗ_НОВОЙ_ВЕРСИИ","body":"кратко суть проблемы"}\n'
    "]\n"
    "- Если уверен в номере строки — укажи \"line\".\n"
    "- Если не уверен — укажи \"line_match\" (короткий точный фрагмент, без префикса '+' и пробелов).\n"
    "- Комментарии короткие, без воды, по делу.\n\n"
    "Подсказка по путям: смотри заголовки вида '+++ b/<path>' в diff.\n\n"
    "Diff:\n"
    "<<<DIFF\n{diff}\nDIFF>>>"
)


def run_codestyle_agent(diff: str) -> List[Dict[str, Any]]:
    llm = ChatOpenAI(model=get_openai_model(), temperature=0)
    resp = llm.invoke(PROMPT.format(diff=diff))
    data = extract_json(resp.content or "")
    return data if isinstance(data, list) else []
