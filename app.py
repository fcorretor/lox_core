import streamlit as st
import requests
from geopy.geocoders import Nominatim

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# ==========================================
# Desenvolvido por: SylvaCore & Varthoz Express
# Versão: 1.0 (Ouro) - Zero Falhas e Roteamento Multi-Paradas

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

# --- 2. CREDENCIAIS HARDCODED ---
CREDENCIAIS = {
    "sulmed": "lox2026",
    "tiesco": "boss"
}

# --- 3. CONSTANTES FINANCEIRAS (Margem Ajustada para Vida Real) ---
TARIFA_BASE = 20.00
VALOR_POR_KM = 1.50
VALOR_MINUTO_VIAGEM = 0.50
VALOR_MINUTO_ESPERA = 1.11

# --- 4. MOTOR DE ROTEAMENTO (Satélite + Trava Geográfica) ---
def calcular_rota_automatica(enderecos, tempo_espera):
    """Bate na API do satélite para rotas com ou sem paradas intermediárias."""
    try:
        geolocator = Nominatim(user_agent="lox_varthoz_routing_v2")
        coordenadas_list = []
        
        # Geocodifica todos os pontos com a trava do Rio Grande do Sul
        for end in enderecos:
            if end.strip() == "":
                continue
            query = f"{end}, Rio Grande do Sul, Brasil"
            loc = geolocator.geocode(query)
            if not loc:
                return f"Erro: Endereço não reconhecido ({end}). Verifique a digitação."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")

        if len(coordenadas_list) < 2:
            return "Erro: É necessário pelo menos uma origem e um destino válidos."

        # Monta a URL do OSRM para múltiplos pontos (lon,lat;lon,lat;...)
        coords_string = ";".join(coordenadas_list)
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?overview=false"
        
        resposta = requests.get(url_osrm).json()
        if resposta.get("code") != "Ok":
            return "Erro: Impossível traçar rota veicular entre estes pontos."

        # Extração e Conversão (Com Fator de Trânsito Urbano 1.6x)
        km = resposta['routes'][0]['distance'] / 1000
        minutos_via_livre = resposta['routes'][0]['duration'] / 60
        minutos_reais = minutos_via_livre * 1.6 
        
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (tempo_espera * VALOR_MINUTO_ESPERA)
        
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except Exception as e:
        return f"Falha no sistema de satélite: {e}"

# --- 5. RENDERIZAÇÃO DAS TELAS ---
def tela_login():
    st.title("🔒 Lox")
    st.markdown("**Sistema Integrado de Roteamento Executivo**")
    st.info("Acesso exclusivo para parceiros corporativos da Varthoz Express.")
    
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    
    if st.button("Acessar Plataforma"):
        if usuario in CREDENCIAIS and CREDENCIAIS[usuario] == senha:
            st.session_state["autenticado"] = True
            st.session_state["cliente"] = usuario
            st.rerun()
        else:
            st.error("Credenciais inválidas. Acesso bloqueado.")

def tela_principal():
    st.success(f"Operador Logado: {st.session_state['cliente'].upper()}")
    
    st.title("🚘 Cotação de Traslado Lox")
    st.markdown("---")
    
    tipo_rota = st.radio("Selecione a Modalidade de Rota:", ["Rota Homologada (Recorrente)", "Nova Rota (Sob Demanda)"])
    
    tempo_espera = st.number_input("Tempo de Espera no Local (Minutos)", min_value=0, step=5)
    custo_espera_extra = tempo_espera * VALOR_MINUTO_ESPERA

    if tipo_rota == "Rota Homologada (Recorrente)":
        destino_fixo = st.selectbox("Selecione o Destino Fixo:", [
            "Braskem Unidade Q2 (Triunfo) - Fixo",
            "Distrito Industrial (Alvorada) - Fixo",
            "Cia do Aço / ArcelorMittal (Alvorada) - Fixo"
        ])
        
        if st.button("Gerar Cotação Oficial"):
            valor_base = 0
            if "Braskem" in destino_fixo: valor_base = 250.00
            elif "Distrito" in destino_fixo: valor_base = 125.38
            elif "Cia do Aço" in destino_fixo: valor_base = 120.00
            
            valor_final = valor_base + custo_espera_extra
            
            st.markdown("### 🧾 Ticket de Cotação Lox")
            st.write(f"**Destino:** {destino_fixo}")
            st.write(f"**Taxa Base de Deslocamento:** R$ {valor_base:.2f}")
            if tempo_espera > 0:
                st.write(f"**Taxa de Espera Logística ({tempo_espera} min):** R$ {custo_espera_extra:.2f}")
            st.success(f"## VALOR FINAL AUTORIZADO: R$ {valor_final:.2f}")

    else:
        st.info("O sistema utilizará rastreamento via satélite para precificar o deslocamento.")
        
        origem = st.text_input("Endereço de Embarque Completo")
        
        # Sistema Dinâmico de Paradas
        qtd_paradas = st.selectbox("Quantidade de Paradas Intermediárias:", [0, 1, 2, 3])
        paradas = []
        for i in range(qtd_paradas):
            p = st.text_input(f"Endereço da Parada {i+1}")
            paradas.append(p)
            
        destino = st.text_input("Endereço de Desembarque Final")
        
       if st.button("Calcular Rota via Satélite"):
            enderecos_completos = [origem] + [p for p in paradas if p] + [destino]
            
            # Validação básica
            if origem and destino:
