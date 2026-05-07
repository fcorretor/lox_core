import streamlit as st
import traceback
import requests
from geopy.geocoders import Nominatim
from datetime import datetime
import urllib.parse
import gspread
import pandas as pd

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 5.0 - Final B2B (Full Business Logic + Zero Trust)
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}
NUMERO_WHATSAPP_CEO = "5551998186611" 

# Tarifa Híbrida Inteligente (Value-Based Pricing B2B)
TARIFA_BASE = 14.00
VALOR_POR_KM = 1.85
VALOR_MINUTO_VIAGEM = 0.30
VALOR_MINUTO_ESPERA = 1.11

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul", 
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão"
]

CENTROS_DE_CUSTO = [
    "Operacional (Polo Petroquímico)", 
    "Medicina do Trabalho", 
    "Diretoria/Executivo", 
    "Comercial", 
    "Outros"
]

def conectar_planilha():
    """Proteção de Secrets e Conexão IAM (Arquitetura Blindada)"""
    try:
        creds = st.secrets["connections"]["gsheets"]
        credentials_dict = {
            "type": creds["type"],
            "project_id": creds["project_id"],
            "private_key_id": creds["private_key_id"],
            "private_key": creds["private_key"],
            "client_email": creds["client_email"],
            "client_id": creds["client_id"],
            "auth_uri": creds["auth_uri"],
            "token_uri": creds["token_uri"],
            "auth_provider_x509_cert_url": creds["auth_provider_x509_cert_url"],
            "client_x509_cert_url": creds["client_x509_cert_url"],
            "universe_domain": creds.get("universe_domain", "googleapis.com")
        }
        client = gspread.service_account_from_dict(credentials_dict)
        sheet = client.open_by_key("1rwrlPpSCc89nc12fP26oCNhWUhKtiKVbIOiCbFWqV44").worksheet("Página1")
        return sheet
    except KeyError:
        st.warning("⚠️ Modo demonstração: secrets.toml não configurado ou chaves ausentes.")
        return None
    except Exception as e:
        st.error(f"Falha técnica na conexão: {e}")
        return None

def salvar_no_banco(dados):
    """Persistência de Dados (Indentação Determinística 4 espaços)"""
    try:
        sheet = conectar_planilha()
        if sheet:
            linha = [
                dados["ID"], dados["Data_Agendamento"], dados["Data_Traslado"], 
                dados["Hora_Embarque"], dados["Passageiro"], dados["Solicitante"], 
                dados["Centro_Custo"], dados["Origem"], dados["Destino"], 
                dados["KM_Total"], dados["Valor_Total"], dados["Status"]
            ]
            sheet.append_row(linha)
            return True
        return False
    except Exception as e:
        st.error(f"Erro de I/O na nuvem: {e}")
        return False

def calcular_rota_automatica(enderecos, total_minutos_espera):
    """Engine de Inteligência Espacial OSRM"""
    try:
        geolocator = Nominatim(user_agent="lox_routing_b2b_v10", timeout=10) 
        coordenadas_list = []
        for end in enderecos:
            if end.strip() == "": continue
            query = f"{end}, Rio Grande do Sul, Brasil"
            loc = geolocator.geocode(query)
            if not loc: return f"Erro: Endereço não localizado ({end})."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")

        if len(coordenadas_list) < 2: return "Erro: Necessário origem e destino."

        coords_string = ";".join(coordenadas_list)
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?overview=false"
        resposta = requests.get(url_osrm, timeout=10).json() 
        if resposta.get("code") != "Ok": return "Erro ao traçar rota veicular."

        km = resposta['routes'][0]['distance'] / 1000
        minutos_reais = (resposta['routes'][0]['duration'] / 60) * 1.6
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "minutos":
