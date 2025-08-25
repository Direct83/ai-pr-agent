import sys
from .github_client import get_pr_info, get_pr_diff_text, get_pr_files
from .utils import build_diff_index
from .graph import review_graph


def main(pr_number: int):
    # 1) Метаданные PR (нужен head sha для inline-комментариев)
    pr = get_pr_info(pr_number)
    head_sha = pr["head"]["sha"]

    # 2) Дифф и список файлов
    diff_text = get_pr_diff_text(pr_number)
    files = get_pr_files(pr_number)
    diff_index = build_diff_index(files)

    # 3) Начальное состояние графа
    initial_state = {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "diff_text": diff_text,
        "diff_index": diff_index,
        "raw_comments": []
    }

    # 4) Запуск графа
    review_graph.invoke(initial_state)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.main <PR_NUMBER>")
    main(int(sys.argv[1]))
