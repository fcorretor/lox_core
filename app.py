import streamlit as st
import requests
from geopy.geocoders import Nominatim

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# ==========================================
# Desenvolvido por: SylvaCore & Zarto Express
# Objetivo: Cotação travada para Sulmed sem margem para choro.

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

# --- 2. CREDENCIAIS HARDCODED (O Porteiro) ---
CREDENCIAIS = {
    "sulmed": "lox2026",
    "tiesco": "boss"
}

# --- 3. CONSTANTES FINANCEIRAS (O Lucro) ---
TARIFA_BASE = 15.00
VALOR_POR_KM = 1.20
VALOR_MINUTO_VIAGEM = 0.50
VALOR_MINUTO_ESPERA = 1.11

# --- 4. FUNÇÕES DE ENGENHARIA (O Motor) ---
def calcular_rota_automatica(origem, destino, tempo_espera):
    """Bate na API do satélite para rotas não homologadas."""
    try:
        geolocator = Nominatim(user_agent="lox_b2b_routing_v1")
        loc_origem = geolocator.geocode(origem)
        loc_destino = geolocator.geocode(destino)
        
        if not loc_origem or not loc_destino:
            return "Erro: Endereço inválido. Seja mais específico (Rua, Número, Cidade)."

        # OSRM para traçar a rota exata de carro
        coordenadas = f"{loc_origem.longitude},{loc_origem.latitude};{loc_destino.longitude},{loc_destino.latitude}"
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coordenadas}?overview=false"
        
        resposta = requests.get(url_osrm).json()
        if resposta.get("code") != "Ok":
            return "Erro: Impossível traçar rota veicular."

        # Conversões
        km = resposta['routes'][0]['distance'] / 1000
        
        # FATOR DE TRÂNSITO: Multiplicamos o tempo do satélite por 1.6 para simular Porto Alegre real.
        minutos_via_livre = resposta['routes'][0]['duration'] / 60
        minutos = minutos_via_livre * 1.6 
        
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos * VALOR_MINUTO_VIAGEM) + (tempo_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "minutos": round(minutos, 0), "total": round(custo, 2)}
    except Exception as e:
        return f"Falha no sistema de satélite: {e}"

# --- 5. RENDERIZAÇÃO DAS TELAS ---
def tela_login():
    st.title("🔒 Lox")
    st.markdown("**Sistema Integrado de Roteamento Executivo**")
    st.info("Acesso exclusivo para parceiros corporativos.")
    
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
        st.info("O sistema utilizará rastreamento via satélite para precificar o deslocamento e o tempo de trânsito.")
        origem = st.text_input("Endereço de Embarque Completo")
        destino = st.text_input("Endereço de Desembarque Completo")
        
        if st.button("Calcular Rota via Satélite"):
            if origem and destino:
                with st.spinner("Processando satélites e trânsito..."):
                    resultado = calcular_rota_automatica(origem, destino, tempo_espera)
                
                if isinstance(resultado, dict):
                    st.markdown("### 🧾 Ticket de Cotação Lox (Dinâmico)")
                    st.write(f"**Distância Estimada:** {resultado['km']} km")
                    st.write(f"**Tempo de Trânsito Estimado:** {resultado['minutos']} min")
                    if tempo_espera > 0:
                        st.write(f"**Taxa de Espera Logística ({tempo_espera} min):** R$ {custo_espera_extra:.2f}")
                    st.success(f"## VALOR FINAL ESTIMADO: R$ {resultado['total']:.2f}")
                else:
                    st.error(resultado)
            else:
                st.warning("Preencha origem e destino para o satélite operar.")
                
    st.markdown("---")
    if st.button("Encerrar Sessão", type="primary"):
        st.session_state["autenticado"] = False
        st.rerun()

# --- 6. MÁQUINA DE ESTADO ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    tela_login()
else:
    tela_principal()
