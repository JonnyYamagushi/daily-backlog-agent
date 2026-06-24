"""
step6_comments.py
-----------------
Coleta os comentarios das tasks abertas (+ concluidas recentes) a partir do
snapshot mais recente e salva data/comments/comments_YYYY-MM-DD.json.

Uso:
    py step6_comments.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.graph_client import GraphClient
from src.collectors.comments import collect_comments

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
COM_DIR = ROOT / "data" / "comments"


def _latest_snapshot() -> Path:
    files = sorted(RAW_DIR.glob("snapshot_*.json"))
    if not files:
        raise FileNotFoundError("Sem snapshot. Rode step2/run_all antes.")
    return files[-1]


def main():
    src = _latest_snapshot()
    snapshot = json.loads(src.read_text(encoding="utf-8"))

    g = GraphClient()
    comments = collect_comments(g, snapshot)

    COM_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = COM_DIR / f"comments_{date_str}.json"
    out.write_text(json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")

    total_posts = sum(len(v) for v in comments.values())
    print(f"\n[OK] {len(comments)} cards com comentarios | {total_posts} posts no total")
    print(f"[OK] Salvo em: {out}\n")

    # amostra
    by_id = {t["id"]: t for p in snapshot["plans"] for t in p["tasks"]}
    print("Amostra (ultimo comentario de 3 cards):")
    for tid, posts in list(comments.items())[:3]:
        titulo = by_id.get(tid, {}).get("title", tid)
        ultimo = posts[-1]
        print(f"  • {titulo}")
        print(f"    [{ultimo['from']} em {ultimo['created']}] {ultimo['text'][:160]}")


if __name__ == "__main__":
    main()
