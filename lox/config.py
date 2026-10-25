"""Parâmetros de negócio e leitura dos Secrets.

Tudo que é sensível (PIX, CPF, senhas, SMTP) vem de st.secrets — painel do
Streamlit Cloud ou .streamlit/secrets.toml local, ambos fora do git.
"""
from datetime import datetime, timedelta, timezone

import streamlit as st

# ==========================================
# MATRIZ FINANCEIRA (inalterada desde a v6.1)
# ==========================================
TARIFA_BASE = 14.00
VALOR_POR_KM = 1.80
VALOR_MINUTO_VIAGEM = 0.25
VALOR_MINUTO_ESPERA = 1.20
FATOR_TRANSITO = 1.6          # OSRM subestima o tempo real na RMPA
ANTECEDENCIA_MIN_HORAS = 4    # SLA de acionamento: 1 turno

ROTAS_HOMOLOGADAS = {
    "Porto Alegre <-> Braskem (Triunfo)": {"valor": 250.00, "destino": "Triunfo (Braskem)"},
    "Porto Alegre <-> Distrito Industrial (Alvorada)": {"valor": 125.00, "destino": "Alvorada (Distrito Industrial)"},
}

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul",
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "Santo Antônio da Patrulha",
    "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão",
]

CENTROS_DE_CUSTO = [
    "Operacional (Polo Petroquímico)",
    "Medicina do Trabalho",
    "Diretoria/Executivo",
    "Comercial",
    "Outros",
]

# ==========================================
# ESQUELETO (features prontas, desligadas por padrão)
# ==========================================
FEATURE_FLAGS = {
    "sulmed_selfservice_ativo": False,
    "notificacao_whatsapp_ativa": False,
}

NUMERO_WHATSAPP_CEO = "5551998186611"

# Brasil sem horário de verão desde 2019: UTC-3 fixo. O Streamlit Cloud roda em UTC.
BRT = timezone(timedelta(hours=-3))


def agora():
    return datetime.now(BRT).replace(tzinfo=None)


def _secao(nome):
    try:
        return dict(st.secrets[nome])
    except Exception:
        return {}


def credenciais():
    """Usuários do portal. Preferir [auth] nos Secrets; o fallback mantém os logins atuais."""
    return _secao("auth") or {"sulmed": "lox2026", "tiesco": "boss"}


def prestador():
    s = _secao("lox")
    return {
        "nome": s.get("nome", "Francesco de Andrade Apratto"),
        "assinatura": s.get("assinatura", "Gestão Logística & Projetos"),
        "cpf": s.get("cpf_prestador", "CPF_NAO_CONFIGURADO_NOS_SECRETS"),
        "pix": s.get("pix_key", "PIX_NAO_CONFIGURADO_NOS_SECRETS"),
        "banco": s.get("banco", "0260 Nu Pagamentos S.A."),
        "cidade": s.get("cidade", "Porto Alegre/RS"),
        "recibo_inicial": int(s.get("recibo_inicial", 1)),
    }


def tomador():
    s = _secao("tomador")
    return {
        "razao": s.get("razao", "SULMED ASSISTÊNCIA MÉDICA LTDA."),
        "cnpj": s.get("cnpj", "90.747.908/0001-56"),
    }


def email():
    s = _secao("email")
    return {
        "host": s.get("smtp_host", "smtp.gmail.com"),
        "porta": int(s.get("smtp_port", 587)),
        "usuario": s.get("smtp_user", ""),
        "senha": s.get("smtp_pass", ""),
        "destino": s.get("destino", ""),
        "cc": s.get("cc", ""),
    }


def gsheets_configurado():
    try:
        return "gsheets" in st.secrets["connections"]
    except Exception:
        return False
