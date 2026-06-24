"""
newsletter.py
-------------
Monta a "Daily Backlog Intelligence" (Markdown) a partir das metricas
determinísticas. NESTA FASE o texto e' gerado por REGRAS (sem IA) — confiavel
e auditavel. Na Fase 2, uma camada de IA enriquece o Resumo Executivo, os
insights, a deteccao de duplicatas e as recomendacoes.

Tambem calcula o diff "o que mudou desde ontem" comparando dois snapshots
normalizados (funciona a partir da 2a execucao).

Secoes marcadas com (IA na Fase 2) ou (comentarios na Fase 1.5) sao
placeholders honestos: dizem o que ainda nao temos, em vez de inventar.
"""

from datetime import datetime, timezone


# Identidades nao-usuario (apps/automacoes) que concluem cards
def _label_pessoa(nome: str | None) -> str:
    if not nome:
        return "(desconhecido)"
    # IDs de aplicacao do Planner nao tem espaco e sao longos
    if " " not in nome and len(nome) > 20:
        return "(automação/sistema)"
    return nome


def compute_changes(prev: dict | None, today: dict) -> dict:
    """Diff entre o backlog de ontem e o de hoje (por id de demanda)."""
    if not prev:
        return {"base": False}

    prev_by_id = {d["id"]: d for d in prev["demands"]}
    today_by_id = {d["id"]: d for d in today["demands"]}

    novas, concluidas, reabertas, mudou_prioridade = [], [], [], []
    for tid, d in today_by_id.items():
        p = prev_by_id.get(tid)
        if not p:
            novas.append(d)
            continue
        if p["status"] != "concluida" and d["status"] == "concluida":
            concluidas.append(d)
        if p["status"] == "concluida" and d["status"] != "concluida":
            reabertas.append(d)
        if p["priority"] != d["priority"]:
            mudou_prioridade.append({"title": d["title"], "de": p["priority"], "para": d["priority"]})

    return {
        "base": True,
        "novas": novas,
        "concluidas": concluidas,
        "reabertas": reabertas,
        "mudou_prioridade": mudou_prioridade,
    }


# ---- Helpers de formatacao --------------------------------------------------

def _fmt_data(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return iso[:10]


def _donos(d: dict) -> str:
    nomes = [_label_pessoa(n) for n in (d.get("assignees") or [])]
    return ", ".join(nomes) if nomes else "**SEM DONO**"


def _linha_demanda(d: dict, mostrar_atraso=False) -> str:
    extra = ""
    if mostrar_atraso and d.get("days_overdue") is not None:
        extra = f" · ⏰ {d['days_overdue']}d atrasada"
    elif d.get("aging_days") is not None:
        extra = f" · {d['aging_days']}d aberta"
    return f"- **{d['title']}** — {_donos(d)} _( {d['priority']}{extra} )_"


# ---- Geracao da newsletter --------------------------------------------------

def build_newsletter(metrics: dict, normalized: dict, changes: dict, my_name: str,
                     insights: dict | None = None,
                     teams_demands: dict | None = None) -> str:
    r = metrics["resumo"]
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    ia = insights or {}
    selo_ia = " 🤖" if insights else ""
    L = []  # linhas

    L.append("# Daily Backlog Intelligence")
    fonte = "Microsoft Planner" + (" · análise enriquecida por IA" if insights else "")
    L.append(f"_Gerado em {now} · fonte: {fonte}_\n")

    # ---------------- Resumo Executivo -----------------
    pct_venc = round(100 * r["vencidas"] / r["abertas"]) if r["abertas"] else 0
    pct_old = round(100 * r["abertas_por_faixa_aging"].get("30+", 0) / r["abertas"]) if r["abertas"] else 0
    L.append(f"## Resumo Executivo{selo_ia}\n")
    if ia.get("resumo_executivo"):
        L.append(ia["resumo_executivo"].strip() + "\n")
        L.append(f"> **Números-chave:** {r['abertas']} abertas · {r['vencidas']} vencidas ({pct_venc}%) · "
                 f"{r['abertas_por_faixa_aging'].get('30+', 0)} paradas +30d · {r['sem_dono']} sem dono.\n")
    else:
        L.append(
        f"O backlog tem **{r['abertas']} demandas abertas** "
        f"({r['concluidas']} já concluídas no histórico). Dessas abertas, "
        f"**{r['vencidas']} estão vencidas ({pct_venc}%)** e "
        f"**{r['abertas_por_faixa_aging'].get('30+', 0)} estão paradas há mais de 30 dias ({pct_old}%)**, "
        f"o que indica envelhecimento relevante do backlog. "
        f"Há **{r['sem_dono']} demanda(s) sem responsável** "
        f"({len(metrics['criticas_sem_dono'])} delas críticas). "
        f"A carga está concentrada: a média é de {metrics['carga_media_por_responsavel']} "
        f"demandas por pessoa, mas há {len(metrics['sobrecarregados'])} responsáveis acima dela. "
        f"_(Resumo aprofundado por IA entra na Fase 2.)_\n"
    )

    # ---------------- O que mudou desde ontem -----------------
    L.append("## O que mudou desde ontem\n")
    if not changes.get("base"):
        L.append("_Primeira execução — sem base anterior para comparar. A partir de amanhã esta seção mostra novas, concluídas, reabertas e mudanças de prioridade._\n")
    else:
        L.append(f"- 🆕 **Novas demandas:** {len(changes['novas'])}")
        L.append(f"- ✅ **Concluídas:** {len(changes['concluidas'])}")
        L.append(f"- 🔁 **Reabertas:** {len(changes['reabertas'])}")
        L.append(f"- 🔀 **Mudaram de prioridade:** {len(changes['mudou_prioridade'])}\n")

    # ---------------- Minha agenda operacional -----------------
    minhas = [d for d in normalized["demands"]
              if d["status"] != "concluida" and my_name in (d["assignees"] or [])]
    minhas.sort(key=lambda d: (not d["is_overdue"], {"urgente": 0, "importante": 1, "media": 2, "baixa": 3}.get(d["priority"], 9), -(d["aging_days"] or 0)))
    L.append("## Minha agenda operacional do dia\n")
    if minhas:
        L.append(f"_{len(minhas)} demandas suas em aberto. Top {min(7, len(minhas))} recomendadas:_\n")
        for d in minhas[:7]:
            L.append(_linha_demanda(d, mostrar_atraso=d["is_overdue"]))
        L.append("")
    else:
        L.append(f"_Nenhuma demanda aberta atribuída a '{my_name}'._\n")

    # ---------------- Alertas críticos -----------------
    L.append("## Alertas críticos\n")
    criticos = [d for d in metrics["vencidas"] if d["priority"] in ("urgente", "importante")][:8]
    if metrics["criticas_sem_dono"]:
        L.append("**Críticas SEM responsável:**")
        for d in metrics["criticas_sem_dono"]:
            L.append(_linha_demanda(d))
        L.append("")
    if criticos:
        L.append("**Vencidas de alta prioridade:**")
        for d in criticos:
            L.append(_linha_demanda(d, mostrar_atraso=True))
        L.append("")
    if not metrics["criticas_sem_dono"] and not criticos:
        L.append("_Sem alertas críticos no momento._\n")

    # ---------------- Bloqueadas -----------------
    L.append(f"## Demandas bloqueadas{selo_ia}\n")
    if ia.get("bloqueadas"):
        L.append("_Bloqueios identificados a partir dos comentários dos cards:_\n")
        for b in ia["bloqueadas"]:
            dep = f" — depende de **{b['depende_de']}**" if b.get("depende_de") else ""
            L.append(f"- **{b.get('titulo', '')}**: {b.get('motivo', '')}{dep}")
        L.append("")
    else:
        L.append("_Nenhum bloqueio com evidência clara nos comentários dos cards abertos._\n")

    # ---------------- Sem responsável -----------------
    L.append("## Demandas sem responsável\n")
    if metrics["sem_dono"]:
        for d in metrics["sem_dono"]:
            L.append(_linha_demanda(d) + f" — _sugestão: direcionar ao time de **{d.get('bucket') or d.get('plan_title')}**_")
        L.append("")
    else:
        L.append("_Todas as demandas abertas têm responsável._\n")

    # ---------------- Demandas no Teams sem card -----------------
    td = (teams_demands or {}).get("demandas_teams") if teams_demands else None
    if td is not None:
        novas_td = [d for d in td if (d.get("ja_rastreada") or "nao").lower() == "nao"]
        L.append("## Demandas no Teams sem card 💬🤖\n")
        if novas_td:
            L.append(f"_{len(novas_td)} possível(is) demanda(s) mencionada(s) no Teams "
                     f"que parecem **não ter card** no Planner:_\n")
            for d in novas_td:
                L.append(f"- **{d.get('assunto', '')}** _(conf. {d.get('confianca', '?')})_ — "
                         f"pedido por {d.get('solicitante', '?')} em _{d.get('origem', '?')}_")
                if d.get("evidencia"):
                    L.append(f"  > {d['evidencia']}")
                if d.get("acao_sugerida"):
                    L.append(f"  _→ {d['acao_sugerida']}_")
            L.append("")
        else:
            L.append("_Nenhuma demanda nova identificada nos chats/canais do período._\n")

    # ---------------- Vencidas -----------------
    L.append("## Demandas vencidas\n")
    if metrics["vencidas"]:
        L.append(f"_{len(metrics['vencidas'])} vencidas. Top 10 por atraso:_\n")
        for d in metrics["vencidas"][:10]:
            L.append(_linha_demanda(d, mostrar_atraso=True))
        L.append("")
    else:
        L.append("_Nenhuma demanda vencida._\n")

    # ---------------- Possíveis duplicadas -----------------
    L.append(f"## Possíveis demandas duplicadas{selo_ia}\n")
    if ia.get("duplicatas"):
        L.append("_Agrupadas por similaridade semântica (IA):_\n")
        for grp in ia["duplicatas"]:
            titulos = " · ".join(grp.get("titulos", []))
            L.append(f"- **{grp.get('tema', 'tema')}** _(confiança {grp.get('confianca', '?')})_: {titulos}")
        L.append("")
    else:
        dups = _duplicatas_simples(normalized)
        if dups:
            L.append("_Detecção simples por título normalizado:_\n")
            for grupo in dups[:8]:
                L.append(f"- **{grupo[0]}** — {len(grupo)} cards com título idêntico/quase idêntico")
            L.append("")
        else:
            L.append("_Nenhuma duplicata óbvia por título._\n")

    # ---------------- Riscos preditivos (IA) -----------------
    if ia.get("riscos_preditivos"):
        L.append("## Riscos preditivos 🤖\n")
        ordem = {"alta": 0, "media": 1, "baixa": 2}
        for risco in sorted(ia["riscos_preditivos"], key=lambda x: ordem.get(x.get("severidade"), 9)):
            sev = (risco.get("severidade") or "?").upper()
            L.append(f"- **[{sev}] {risco.get('titulo', '')}** — {risco.get('hipotese', '')}")
        L.append("")

    # ---------------- Quem resolveu o quê -----------------
    L.append("## Quem resolveu o quê\n")
    res = metrics["resolucao"]
    L.append(f"_Concluídas: {res['concluidas_ultimos_7_dias']} nos últimos 7 dias, "
             f"{res['concluidas_ultimos_30_dias']} em 30 dias. Tempo médio de resolução: "
             f"{res['tempo_medio_resolucao_dias']} dias._\n")
    L.append("**Ranking histórico de resoluções** _(contagem de **baixas** dadas — "
             "quem marcou como concluída, que nem sempre é quem desenvolveu):_")
    for x in res["ranking_total"][:8]:
        L.append(f"- {_label_pessoa(x['responsavel'])}: {x['resolvidas']}")
    L.append("")

    # ---------------- Destaques dos comentários -----------------
    L.append(f"## Destaques dos comentários{selo_ia}\n")
    if ia.get("destaques_comentarios"):
        for dc in ia["destaques_comentarios"]:
            L.append(f"- **{dc.get('titulo', '')}**: {dc.get('destaque', '')}")
        L.append("")
    else:
        L.append("_Sem comentários relevantes nos cards abertos (ou IA desativada)._\n")

    # ---------------- Gargalos -----------------
    L.append("## Gargalos identificados\n")
    L.append("**Áreas (buckets) com mais demandas abertas:**")
    for x in metrics["gargalos_por_area"][:7]:
        L.append(f"- {x['area']}: {x['abertas']}")
    L.append("")

    # ---------------- Visão para coordenação -----------------
    L.append(f"## Visão para coordenação{selo_ia}\n")
    if ia.get("visao_coordenacao"):
        L.append(ia["visao_coordenacao"].strip() + "\n")
    L.append(f"- **Situação geral:** {r['abertas']} abertas, {r['vencidas']} vencidas ({pct_venc}%), {r['abertas_por_faixa_aging'].get('30+', 0)} paradas +30d.")
    L.append("- **Responsáveis sobrecarregados:** " + ", ".join(
        f"{s['responsavel']} ({s['abertas']} abertas, {s['vencidas']} vencidas)" for s in metrics["sobrecarregados"][:5]))
    L.append("- **Maior gargalo de área:** " + (f"{metrics['gargalos_por_area'][0]['area']} ({metrics['gargalos_por_area'][0]['abertas']} abertas)" if metrics["gargalos_por_area"] else "—"))
    L.append(f"- **Risco de envelhecimento:** {len(metrics['parados_30plus'])} demandas paradas há +30 dias.")
    L.append("- **Precisa de decisão:** " + (f"{len(metrics['criticas_sem_dono'])} críticas sem dono" if metrics["criticas_sem_dono"] else "nada urgente sem dono") + ".\n")

    # ---------------- O que precisa de decisão hoje (IA) -----------------
    if ia.get("o_que_decidir_hoje"):
        L.append("## O que precisa de decisão hoje 🤖\n")
        for item in ia["o_que_decidir_hoje"]:
            L.append(f"- {item}")
        L.append("")

    # ---------------- Recomendações -----------------
    L.append(f"## Recomendações do agente{selo_ia}\n")
    if ia.get("recomendacoes"):
        for rec in sorted(ia["recomendacoes"], key=lambda x: x.get("prioridade", 99)):
            alvo = f" _(→ {rec['alvo']})_" if rec.get("alvo") else ""
            L.append(f"- **{rec.get('prioridade', '·')}.** {rec.get('acao', '')}{alvo}")
    else:
        for rec in _recomendacoes(metrics):
            L.append(f"- {rec}")
    rodape = "camada determinística + IA (claude headless)" if insights else "camada determinística"
    L.append(f"\n---\n_Gerado por daily-backlog-agent ({rodape}). Leitura de comentários dos cards na próxima fase._")

    return "\n".join(L)


def _duplicatas_simples(normalized: dict):
    import re
    grupos = {}
    for d in normalized["demands"]:
        if d["status"] == "concluida":
            continue
        chave = re.sub(r"[^a-z0-9]", "", (d["title"] or "").lower())
        grupos.setdefault(chave, []).append(d["title"])
    return [v for v in grupos.values() if len(v) > 1]


def _recomendacoes(metrics: list) -> list[str]:
    recs = []
    if metrics["criticas_sem_dono"]:
        recs.append(f"**Atribuir dono** às {len(metrics['criticas_sem_dono'])} demandas críticas sem responsável ainda hoje.")
    if metrics["sobrecarregados"]:
        top = metrics["sobrecarregados"][0]
        recs.append(f"**Redistribuir carga** de {top['responsavel']} ({top['abertas']} abertas, {top['vencidas']} vencidas) — risco de gargalo em uma só pessoa.")
    if metrics["parados_30plus"]:
        recs.append(f"**Revisar/fechar** as {len(metrics['parados_30plus'])} demandas paradas há +30 dias (muitas podem já estar resolvidas ou obsoletas).")
    if metrics["resumo"]["vencidas"]:
        recs.append(f"**Repactuar prazos** das {metrics['resumo']['vencidas']} demandas vencidas, priorizando as de alta prioridade.")
    if metrics["gargalos_por_area"]:
        g = metrics["gargalos_por_area"][0]
        recs.append(f"**Investigar o gargalo** na área '{g['area']}' ({g['abertas']} abertas) — possível ponto de represamento do fluxo.")
    return recs or ["Backlog sob controle nas dimensões medidas. Manter monitoramento diário."]
