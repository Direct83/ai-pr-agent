import json
import re
from typing import Dict, List, Any, Tuple, Optional


def extract_json(text: str):
    """
    Надёжно извлекаем JSON-массив из ответа LLM.
    1) Пробуем распарсить весь текст.
    2) Ищем блок формата fenced-кода (```json ... ```), но без жёсткой привязки.
    3) Иначе берём подстроку между первой '[' и последней ']'.
    Возвращаем [] при неудаче.
    """
    if not text:
        return []
    # Попытка №1: весь текст
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        pass
    # Попытка №2: fenced-подобный блок
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, list) else []
        except Exception:
            pass
    # Попытка №3: массив верхнего уровня
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        sub = text[start:end+1]
        try:
            data = json.loads(sub)
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def build_diff_index(files: List[Dict[str, Any]]) -> Dict[str, List[Tuple[int, str]]]:
    """
    Строим индекс строк НОВОЙ версии по каждому файлу на основе unified patch
    из /pulls/{number}/files.
    Возвращаем: { "path": [(new_line_number, line_text_without_prefix), ...] }.
    """
    index: Dict[str, List[Tuple[int, str]]] = {}
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        lines = patch.splitlines()
        cur_new = None
        acc: List[Tuple[int, str]] = []
        for ln in lines:
            if ln.startswith("@@"):
                # пример заголовка: @@ -a,b +c,d @@
                m = re.search(r"\+(\d+)", ln)
                cur_new = int(m.group(1)) if m else None
            elif cur_new is not None:
                if ln.startswith("+"):
                    acc.append((cur_new, ln[1:]))
                    cur_new += 1
                elif ln.startswith(" "):
                    acc.append((cur_new, ln[1:]))
                    cur_new += 1
                elif ln.startswith("-"):
                    # удалённая строка — номер новой версии не увеличиваем
                    pass
        index[path] = acc
    return index


def resolve_positions(agent_items: List[Dict[str, Any]], diff_index: Dict[str, List[Tuple[int, str]]]) -> List[Dict[str, Any]]:
    """
    Преобразуем элементы агента к виду для GitHub inline-комментов.
    Вход: [{"path","line"|"line_match","body"}]
    Выход: [{"path","line","body"}]
    Если line не задан — ищем line_match в тексте новой версии и ставим соответствующий номер строки.
    """
    resolved: List[Dict[str, Any]] = []
    for it in agent_items or []:
        path = it.get("path")
        body = it.get("body") or it.get("message")
        if not path or not body:
            continue
        # 1) если указан точный номер
        if isinstance(it.get("line"), int):
            resolved.append({"path": path, "line": int(it["line"]), "body": body})
            continue
        # 2) поиск по подстроке новой версии
        candidates = diff_index.get(path) or []
        line_match = (it.get("line_match") or "").strip()
        if line_match:
            best: Optional[int] = None
            for new_line, text in candidates:
                if line_match in text:
                    best = new_line
                    break
            if best is None and candidates:
                best = candidates[0][0]
            if best is not None:
                resolved.append({"path": path, "line": best, "body": body})
                continue
        # 3) fallback — первая строка файла или 1
        fallback = candidates[0][0] if candidates else 1
        resolved.append({"path": path, "line": fallback, "body": body})
    return resolved
