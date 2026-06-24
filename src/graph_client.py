"""
graph_client.py
---------------
Wrapper fino sobre a API do Microsoft Graph.

- Anexa o token em todas as requisições.
- get():     uma chamada simples.
- get_all(): segue a paginação (@odata.nextLink) e devolve a lista completa.
- Trata 429 (throttling) respeitando o Retry-After.
"""

import time
import requests

from .auth import get_token

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {get_token()}"})

    def get(self, path: str, params: dict | None = None) -> dict:
        url = path if path.startswith("http") else f"{GRAPH}{path}"
        for attempt in range(5):
            r = self.session.get(url, params=params)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return r.json()

    def get_all(self, path: str, params: dict | None = None) -> list:
        items: list = []
        data = self.get(path, params=params)
        items.extend(data.get("value", []))
        while "@odata.nextLink" in data:
            data = self.get(data["@odata.nextLink"])
            items.extend(data.get("value", []))
        return items
