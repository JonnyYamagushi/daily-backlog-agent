"""
teams.py
--------
Coletor de mensagens do Microsoft Teams (canais + chats), para capturar
demandas que ainda nao viraram card no Planner.

Fontes:
  - Canais: /me/joinedTeams -> /teams/{id}/channels -> .../messages (+ replies)
  - Chats:  /me/chats -> /chats/{id}/messages

Permissoes (delegadas): Team.ReadBasic.All, Channel.ReadBasic.All,
ChannelMessage.Read.All, Chat.Read.

A coleta e' limitada a uma JANELA de tempo (dias) e tem travas de seguranca
(max de paginas por fonte) para nao explodir em canais muito movimentados.
A classificacao "isto e' uma demanda?" e a deduplicacao vs Planner ficam na
camada de IA — aqui so coletamos e limpamos o texto.
"""

from datetime import datetime, timezone, timedelta

from ..graph_client import GraphClient
from .comments import clean_html


MAX_PAGES = 10          # por canal/chat (50 msgs por pagina)
MAX_MSG_CHARS = 1200    # trunca corpo de cada mensagem


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _simplify(m: dict, source: str, container: str) -> dict | None:
    # Descarta apenas eventos de sistema (entrou/saiu, renomeou canal, etc.).
    # Mantem "message" e outros tipos (ex.: "unknownFutureValue") desde que
    # tenham texto real — canais usam tipos variados.
    if m.get("messageType") == "systemEventMessage":
        return None
    texto = clean_html((m.get("body") or {}).get("content", ""))
    if not texto:
        return None
    autor = (((m.get("from") or {}).get("user")) or {}).get("displayName")
    return {
        "source": source,            # "canal" | "chat"
        "container": container,       # "Equipe / Canal" ou nome do chat
        "from": autor,
        "created": m.get("createdDateTime"),
        "text": texto[:MAX_MSG_CHARS],
        "web_url": m.get("webUrl"),
    }


def _page_messages(g: GraphClient, base_path: str, cutoff: datetime):
    """Coleta mensagens de um endpoint paginado, parando na janela de tempo."""
    out = []
    data = g.get(base_path, params={"$top": 50})
    pages = 0
    while data and pages < MAX_PAGES:
        antigos_na_pagina = 0
        for m in data.get("value", []):
            created = _parse_dt(m.get("createdDateTime"))
            if created and created < cutoff:
                antigos_na_pagina += 1
                continue
            out.append(m)
        # se a pagina inteira ja e' antiga, provavelmente chegamos ao fim da janela
        if antigos_na_pagina == len(data.get("value", [])) and data.get("value"):
            break
        nxt = data.get("@odata.nextLink")
        if not nxt:
            break
        data = g.get(nxt)
        pages += 1
    return out


def collect_channels(g: GraphClient, cutoff: datetime) -> list[dict]:
    msgs = []
    teams = g.get_all("/me/joinedTeams", params={"$select": "id,displayName"})
    print(f"   equipes: {len(teams)}")
    for team in teams:
        tid, tname = team["id"], team.get("displayName")
        try:
            channels = g.get_all(f"/teams/{tid}/channels", params={"$select": "id,displayName"})
        except Exception as e:
            print(f"   [aviso] canais de '{tname}' ilegiveis: {e}")
            continue
        for ch in channels:
            cid, cname = ch["id"], ch.get("displayName")
            container = f"{tname} / {cname}"
            try:
                raw = _page_messages(g, f"/teams/{tid}/channels/{cid}/messages", cutoff)
            except Exception as e:
                print(f"   [aviso] mensagens de '{container}' ilegiveis: {e}")
                continue
            for m in raw:
                s = _simplify(m, "canal", container)
                if s:
                    msgs.append(s)
                # replies das mensagens dentro da janela
                if (m.get("replies@odata.count") or 0) > 0 or m.get("replies"):
                    try:
                        reps = g.get_all(f"/teams/{tid}/channels/{cid}/messages/{m['id']}/replies")
                        for rp in reps:
                            sr = _simplify(rp, "canal", container)
                            if sr and _parse_dt(sr["created"]) and _parse_dt(sr["created"]) >= cutoff:
                                msgs.append(sr)
                    except Exception:
                        pass
    return msgs


def collect_chats(g: GraphClient, cutoff: datetime) -> list[dict]:
    msgs = []
    chats = g.get_all("/me/chats", params={"$select": "id,topic,chatType"})
    print(f"   chats: {len(chats)}")
    for c in chats:
        cid = c["id"]
        nome = c.get("topic") or f"({c.get('chatType', 'chat')})"
        try:
            raw = _page_messages(g, f"/chats/{cid}/messages", cutoff)
        except Exception as e:
            print(f"   [aviso] chat '{nome}' ilegivel: {e}")
            continue
        for m in raw:
            s = _simplify(m, "chat", nome)
            if s:
                msgs.append(s)
    return msgs


def collect_teams(g: GraphClient, days: int = 3, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    print(f"[teams] coletando canais (ultimos {days} dias)...")
    canais = collect_channels(g, cutoff)
    print(f"[teams] coletando chats (ultimos {days} dias)...")
    chats = collect_chats(g, cutoff)

    todas = canais + chats
    todas.sort(key=lambda x: x["created"] or "")
    print(f"[teams] {len(canais)} msgs de canais + {len(chats)} de chats = {len(todas)} total")
    return {
        "collected_at": now.isoformat(),
        "window_days": days,
        "messages": todas,
    }
