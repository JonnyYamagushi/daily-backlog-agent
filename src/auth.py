"""
auth.py
-------
Responsável APENAS por autenticar no Microsoft Graph usando MSAL com
Device Code Flow (login delegado, em seu nome).

Como funciona:
- Na 1ª execução: imprime um código e uma URL. Você abre no navegador,
  cola o código e loga. O MSAL grava um cache de token em data/cache/.
- Nas execuções seguintes (inclusive agendadas): o token é renovado
  silenciosamente via refresh token, sem pedir login de novo.

Não há client secret aqui de propósito: usamos "cliente público" (mais
simples e seguro para um app que roda na sua máquina).
"""

import os
import json
import atexit
from pathlib import Path

import msal
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
SCOPES = os.getenv(
    "GRAPH_SCOPES",
    "Tasks.Read Group.Read.All User.Read User.ReadBasic.All "
    "Team.ReadBasic.All Channel.ReadBasic.All ChannelMessage.Read.All Chat.Read",
).split()

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Cache do token fica fora do controle de versão (.gitignore cobre data/cache/)
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "token_cache.bin"


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text(encoding="utf-8"))
    atexit.register(lambda: _save_cache(cache))
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")


def get_token() -> str:
    """Retorna um access_token válido para o Microsoft Graph."""
    if not TENANT_ID or not CLIENT_ID:
        raise RuntimeError(
            "TENANT_ID/CLIENT_ID ausentes. Copie .env.example para .env e preencha."
        )

    cache = _load_cache()
    app = msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache
    )

    # 1) Tenta renovar silenciosamente a partir de uma conta já em cache
    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # 2) Se não houver token válido, faz o Device Code Flow
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                "Falha ao iniciar device flow: " + json.dumps(flow, indent=2)
            )
        print("\n=== LOGIN MICROSOFT ===")
        print(flow["message"])  # contém URL + código
        print("=======================\n")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(
            "Falha na autenticação:\n" + json.dumps(result, indent=2)
        )

    return result["access_token"]
