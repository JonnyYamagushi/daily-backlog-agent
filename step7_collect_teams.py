"""
step7_collect_teams.py
----------------------
Coleta mensagens do Teams (canais + chats) dos ultimos N dias e salva
data/raw/teams_YYYY-MM-DD.json. Imprime resumo e amostras.

Na PRIMEIRA execucao apos adicionar as permissoes do Teams, vai pedir login
de novo (Device Code) para emitir um token com os novos escopos.

Uso:
    py step7_collect_teams.py            # 3 dias (padrao)
    py step7_collect_teams.py --days 7
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
from src.collectors.teams import collect_teams

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"


def main():
    days = 3
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except (ValueError, IndexError):
            pass

    g = GraphClient()
    data = collect_teams(g, days=days)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = RAW_DIR / f"teams_{date_str}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    msgs = data["messages"]
    print(f"\n[OK] {len(msgs)} mensagens salvas em: {out}")
    print("\nAmostra (ultimas 5):")
    for m in msgs[-5:]:
        print(f"  • [{m['source']}] {m['container']}")
        print(f"    {m['from']} ({(m['created'] or '')[:16]}): {m['text'][:120]}")


if __name__ == "__main__":
    main()
