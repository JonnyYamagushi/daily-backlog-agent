"""
comments.py
-----------
Coletor de COMENTARIOS dos cards do Planner.

Os comentarios nao estao na API do Planner: cada task tem um
`conversationThreadId` que aponta para um thread de conversa do Grupo M365
(Exchange). Lemos via:
    GET /groups/{group_id}/threads/{conversationThreadId}/posts
(permissao Group.Read.All, que ja temos).

Escopo: por padrao coletamos comentarios apenas de tasks ABERTAS e das
concluidas RECENTEMENTE (janela configuravel) — assim a coleta diaria fica
rapida (a maioria dos 1000+ threads historicos e' irrelevante para o dia).

Limpeza: o corpo vem em HTML e o Planner injeta uma tabela oculta
(x_jSanity_hideInPlanner) com boilerplate. Removemos isso e extraimos texto.
"""

import re
import html
from datetime import datetime, timezone

from ..graph_client import GraphClient


_JSANITY = re.compile(r"<table[^>]*jSanity[^>]*>.*", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_html(body_html: str | None) -> str:
    if not body_html:
        return ""
    t = _JSANITY.sub("", body_html)      # corta o boilerplate do Planner em diante
    t = _TAGS.sub(" ", t)                # remove tags
    t = html.unescape(t)                 # decodifica entidades (&nbsp; etc.)
    t = _WS.sub(" ", t).strip()          # normaliza espacos
    return t


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _recent(value, days: int, now: datetime) -> bool:
    dt = _parse_dt(value)
    return bool(dt and (now - dt).days <= days)


def collect_comments(g: GraphClient, snapshot: dict,
                     include_completed_days: int = 14,
                     now: datetime | None = None) -> dict:
    """Retorna {task_id: [ {from, created, text}, ... ]} para tasks relevantes."""
    now = now or datetime.now(timezone.utc)
    result: dict[str, list] = {}
    alvos = 0

    for plan in snapshot.get("plans", []):
        gid = plan.get("group_id")
        if not gid:
            continue
        for t in plan.get("tasks", []):
            cid = t.get("conversationThreadId")
            if not cid:
                continue

            concluida = t.get("percentComplete", 0) == 100
            if concluida and not _recent(t.get("completedDateTime"), include_completed_days, now):
                continue  # concluida ha muito tempo -> ignora

            alvos += 1
            try:
                posts = g.get_all(f"/groups/{gid}/threads/{cid}/posts")
            except Exception as e:
                print(f"   [aviso] thread {cid[:12]}... ilegivel: {e}")
                continue

            comentarios = []
            for po in posts:
                texto = clean_html((po.get("body") or {}).get("content", ""))
                if not texto:
                    continue
                comentarios.append({
                    "from": ((po.get("from") or {}).get("emailAddress") or {}).get("name"),
                    "created": po.get("createdDateTime"),
                    "text": texto,
                })
            if comentarios:
                comentarios.sort(key=lambda c: c["created"] or "")
                result[t["id"]] = comentarios

    print(f"[comentarios] {alvos} card(s) candidatos, {len(result)} com comentarios.")
    return result
