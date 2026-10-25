"""Roteamento (Nominatim + OSRM) e precificação — mesma fórmula da v6.1."""
import requests
import streamlit as st
from geopy.geocoders import Nominatim

from .config import (FATOR_TRANSITO, TARIFA_BASE, VALOR_MINUTO_ESPERA,
                     VALOR_MINUTO_VIAGEM, VALOR_POR_KM)


@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar(endereco):
    loc = Nominatim(user_agent="lox_routing_b2b_v10", timeout=10).geocode(f"{endereco}, Rio Grande do Sul, Brasil")
    return (loc.latitude, loc.longitude) if loc else None


def compor_preco(km, minutos, espera):
    return {
        "base": TARIFA_BASE,
        "km": round(km * VALOR_POR_KM, 2),
        "tempo": round(minutos * VALOR_MINUTO_VIAGEM, 2),
        "espera": round(espera * VALOR_MINUTO_ESPERA, 2),
    }


def calcular_rota_automatica(enderecos, total_minutos_espera):
    """Retorna dict com km, minutos, total, composição e geometria — ou str de erro."""
    try:
        pontos = []
        for end in enderecos:
            if not end or not end.strip():
                continue
            c = geocodificar(end)
            if not c:
                return f"Erro: Endereço não localizado ({end})."
            pontos.append(c)
        if len(pontos) < 2:
            return "Erro: Necessário origem e destino válidos."

        coords = ";".join(f"{lon},{lat}" for lat, lon in pontos)
        url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=simplified&geometries=geojson"
        resp = requests.get(url, timeout=10).json()
        if resp.get("code") != "Ok":
            return "Erro ao traçar rota veicular."

        rota = resp["routes"][0]
        km = rota["distance"] / 1000
        minutos = (rota["duration"] / 60) * FATOR_TRANSITO
        comp = compor_preco(km, minutos, total_minutos_espera)
        return {
            "km": round(km, 1), "minutos": round(minutos, 0),
            "total": round(TARIFA_BASE + km * VALOR_POR_KM + minutos * VALOR_MINUTO_VIAGEM
                           + total_minutos_espera * VALOR_MINUTO_ESPERA, 2),
            "composicao": comp,
            "pontos": pontos, "trajeto": rota["geometry"]["coordinates"],
        }
    except Exception as e:
        return f"Falha no ecossistema de roteamento: {e}"
