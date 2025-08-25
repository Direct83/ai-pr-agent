import json
import re
from typing import Dict, List, Any, Tuple, Optional
from .config import REVIEW_ONLY_PREFIXES


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


def path_included(path: str) -> bool:
    """true, если файл попадает под белый список префиксов (по умолчанию: только src/)."""
    path = (path or "").lstrip("./")
    return any(path.startswith(pref.rstrip("/") + "/") or path == pref.rstrip("/") for pref in REVIEW_ONLY_PREFIXES)


def build_filtered_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """вернёт только те элементы из /pulls/{n}/files, чей filename начинается с разрешённых префиксов."""
    out: List[Dict[str, Any]] = []
    for f in files:
        fn = f.get("filename") or ""
        if path_included(fn):
            out.append(f)
    return out


def build_diff_text_from_files(files: List[Dict[str, Any]]) -> str:
    """
    Склеиваем дифф только по выбранным файлам.
    Добавляем заголовок '+++ b/<path>' перед патчем, чтобы агенты знали путь.
    """
    parts: List[str] = []
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        parts.append(f"+++ b/{path}\n{patch}\n")
    return "\n".join(parts)


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

    Формат входа: [{"path", "line_match", "body"}].
    Поддерживается только привязка по содержимому новой версии через "line_match".
    Числовые координаты "line" намеренно игнорируются, чтобы исключить
    постановку комментариев к удалённым или смещённым строкам.

    Формат выхода: [{"path", "line", "body"}] — с вычисленным номером строки
    в НОВОЙ версии файла.
    """
    resolved: List[Dict[str, Any]] = []
    for it in agent_items:
        path = it.get("path")
        body = it.get("body") or it.get("message")
        if not path or not body:
            continue

        candidates = diff_index.get(path) or []
        line_match = (it.get("line_match") or "").strip()

        # 1) Сопоставляем только по содержимому новой версии
        if line_match:
            best: Optional[int] = None
            # точное вхождение
            for new_line, text in candidates:
                if line_match in text:
                    best = new_line
                    break
            # послабление: игнорируем пробелы
            if best is None and line_match:
                lm_norm = re.sub(r"\s+", "", line_match)
                for new_line, text in candidates:
                    if lm_norm in re.sub(r"\s+", "", text):
                        best = new_line
                        break
            if best is not None:
                resolved.append({"path": path, "line": best, "body": body})
                continue

        # 2) Если нет line_match и сопоставления не получилось — пропускаем элемент
        # Чисто числовые координаты небезопасны (съезжают из‑за удалений выше).
        continue
    return resolved


def merge_by_line_match(agent_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Объединяет элементы с одинаковыми (path, line_match) в один, склеивая body через пробел.
    Порядок сохраняется по первому появлению каждой пары (path, line_match).
    """
    if not agent_items:
        return []

    # Сбор частей по ключу (path, line_match)
    key_to_parts: Dict[Tuple[str, str], List[str]] = {}
    key_to_proto: Dict[Tuple[str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str]] = []

    for it in agent_items:
        path = it.get("path") or ""
        lm = (it.get("line_match") or "").strip()
        body = (it.get("body") or it.get("message") or "").strip()
        if path and lm and body:
            key = (path, lm)
            if key not in key_to_parts:
                key_to_parts[key] = []
                key_to_proto[key] = dict(it)
                order.append(key)
            key_to_parts[key].append(body)
        else:
            # Сохраняем элементы без line_match как есть (вставим их позже по порядку)
            # Пометим уникальный ключ, чтобы затем корректно восстановить порядок
            pass

    # Формируем объединённые элементы, сохраняя порядок первых появлений ключей
    merged_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for key in order:
        proto = key_to_proto[key]
        parts = key_to_parts.get(key) or []
        combined_body = " ".join(parts).strip()
        new_item = dict(proto)
        new_item["body"] = combined_body
        merged_by_key[key] = new_item

    # Восстанавливаем исходный порядок обходом входного списка и вставляем
    # объединённые элементы один раз на первое вхождение соответствующего key
    seen_keys: set[Tuple[str, str]] = set()
    result: List[Dict[str, Any]] = []
    for it in agent_items:
        path = it.get("path") or ""
        lm = (it.get("line_match") or "").strip()
        body = (it.get("body") or it.get("message") or "").strip()
        if path and lm and body:
            key = (path, lm)
            if key in merged_by_key and key not in seen_keys:
                result.append(merged_by_key[key])
                seen_keys.add(key)
            # повторные элементы того же ключа пропускаем (они уже объединены)
        else:
            # Элемент без line_match — оставляем как есть
            result.append(it)

    return result
