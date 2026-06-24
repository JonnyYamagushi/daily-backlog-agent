"""
step3_normalize.py
------------------
Le o snapshot cru mais recente (data/raw/snapshot_*.json), normaliza e salva
data/normalized/backlog_YYYY-MM-DD.json. Imprime um resumo de validacao.

Uso:
    py step3_normalize.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.normalize import normalize_snapshot

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
NORM_DIR = ROOT / "data" / "normalized"


def _latest_snapshot() -> Path:
    files = sorted(RAW_DIR.glob("snapshot_*.json"))
    if not files:
        raise FileNotFoundError("Nenhum snapshot em data/raw/. Rode step2 antes.")
    return files[-1]


def main():
    src = _latest_snapshot()
    snapshot = json.loads(src.read_text(encoding="utf-8"))
    result = normalize_snapshot(snapshot)

    NORM_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = NORM_DIR / f"backlog_{date_str}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    demands = result["demands"]
    abertas = [d for d in demands if d["status"] != "concluida"]
    status = Counter(d["status"] for d in demands)
    faixa_abertas = Counter(d["age_bucket"] for d in abertas)
    prio_abertas = Counter(d["priority"] for d in abertas)

    print(f"\n[OK] Fonte: {src.name}")
    print(f"[OK] Normalizado: {out}")
    print("\n=========== VALIDACAO DA NORMALIZACAO ===========")
    print(f" Demandas (total)......: {result['total']}")
    print(f" Por status............: {dict(status)}")
    print(f" Abertas...............: {len(abertas)}")
    print(f"   - sem responsavel...: {sum(1 for d in abertas if not d['has_owner'])}")
    print(f"   - vencidas..........: {sum(1 for d in abertas if d['is_overdue'])}")
    print(f"   - faixa de aging....: {dict(faixa_abertas)}")
    print(f"   - por prioridade....: {dict(prio_abertas)}")
    print("=================================================\n")

    print("Amostra (3 demandas abertas mais antigas):")
    for d in sorted(abertas, key=lambda x: x["aging_days"] or 0, reverse=True)[:3]:
        dono = ", ".join(d["assignees"]) or "SEM DONO"
        print(f"  - [{d['aging_days']}d | {d['priority']}] {d['title']}  ->  {dono}")


if __name__ == "__main__":
    main()
