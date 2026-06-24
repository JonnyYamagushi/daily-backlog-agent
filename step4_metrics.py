"""
step4_metrics.py
----------------
Le o backlog normalizado mais recente, calcula as metricas determinísticas
e salva data/metrics/metrics_YYYY-MM-DD.json. Imprime os principais numeros.

Uso:
    py step4_metrics.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.metrics import compute_metrics

ROOT = Path(__file__).resolve().parent
NORM_DIR = ROOT / "data" / "normalized"
MET_DIR = ROOT / "data" / "metrics"


def _latest_normalized() -> Path:
    files = sorted(NORM_DIR.glob("backlog_*.json"))
    if not files:
        raise FileNotFoundError("Nenhum backlog normalizado. Rode step3 antes.")
    return files[-1]


def main():
    src = _latest_normalized()
    normalized = json.loads(src.read_text(encoding="utf-8"))
    m = compute_metrics(normalized)

    MET_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = MET_DIR / f"metrics_{date_str}.json"
    out.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    r = m["resumo"]
    print(f"\n[OK] Fonte: {src.name}")
    print(f"[OK] Metricas: {out}")
    print("\n=============== PRINCIPAIS METRICAS ===============")
    print(f" Abertas: {r['abertas']} | Vencidas: {r['vencidas']} | Sem dono: {r['sem_dono']}")
    print(f" Prioridade (abertas): {r['abertas_por_prioridade']}")
    print(f" Aging (abertas): {r['abertas_por_faixa_aging']}")
    print(f" Criticas sem dono: {len(m['criticas_sem_dono'])}")
    print(f" Parados +30 dias: {len(m['parados_30plus'])}")
    print(f" Carga media/responsavel: {m['carga_media_por_responsavel']}")

    print("\n Top 5 carga (responsavel | abertas | vencidas | aging medio):")
    for x in m["backlog_por_responsavel"][:5]:
        print(f"   {x['responsavel'][:22]:22s} | {x['abertas']:3d} | {x['vencidas']:3d} | {x['aging_medio']}")

    print(f"\n Sobrecarregados (> media {m['carga_media_por_responsavel']}): "
          + ", ".join(s["responsavel"] for s in m["sobrecarregados"]))

    print("\n Resolucao:")
    res = m["resolucao"]
    print(f"   concluidas 7d: {res['concluidas_ultimos_7_dias']} | 30d: {res['concluidas_ultimos_30_dias']}"
          f" | tempo medio: {res['tempo_medio_resolucao_dias']} dias")
    print("   Top resolvedores (historico):")
    for x in res["ranking_total"][:5]:
        print(f"     {x['resolvidas']:4d}  {x['responsavel']}")

    print("\n Top gargalos por area (bucket):")
    for x in m["gargalos_por_area"][:5]:
        print(f"   {x['abertas']:3d}  {x['area']}")
    print("==================================================\n")


if __name__ == "__main__":
    main()
