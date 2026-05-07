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
# Versão: 4.1 - Produção Blindada (Varthoz HQ)
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}
NUMERO_WHATSAPP_CEO = "5551998186611" 

TARIFA_BASE = 10.00
VALOR_POR_KM = 1.30
VALOR_MINUTO_VIAGEM = 0.30
VALOR_MINUTO_ESPERA = 1.50

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul", 
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão"
]

CENTROS_DE_CUSTO = ["Operacional (Polo Petroquímico)", "Medicina do Trabalho", "Diretoria/Executivo", "Comercial", "Outros"]

def conectar_planilha():
    """Proteção de Secrets e Conexão IAM"""
    try:
        # PROTEÇÃO DE ACESSO A SECRETS SOLICITADA
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
    """Indentação de 4 espaços por nível - Blindada"""
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
    try:
        geolocator = Nominatim(user_agent="lox_routing_b2b_v10", timeout=10) 
        coordenadas_list = []
        for end in enderecos:
            if end.strip() == "": continue
            loc = geolocator.geocode(f"{end}, Rio Grande do Sul, Brasil")
            if not loc: return f"Erro: Localização não encontrada ({end})."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")
        
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{';'.join(coordenadas_list)}?overview=false"
        res = requests.get(url_osrm, timeout=10).json()
        if res.get("code") != "Ok": return "Erro no satélite."
        
        km = res['routes'][0]['distance'] / 1000
        minutos = (res['routes'][0]['duration'] / 60) * 1.6
        total = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "total": round(total, 2)}
    except Exception as e: return f"Falha: {e}"

def tela_login():
    st.title("🔒 Lox Portal")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Acessar"):
        if usuario in CREDENCIAIS and CREDENCIAIS[usuario] == senha:
            st.session_state["autenticado"], st.session_state["cliente"] = True, usuario
            st.rerun()
        else: st.error("Acesso Negado.")

def tela_principal():
    usuario_atual = st.session_state['cliente']
    st.success(f"Operador: {usuario_atual.upper()}")
    st.title("🚘 Cotação e Agendamento Lox")
    
    aba_op, aba_fin = st.tabs(["🛣️ Operação", "📊 Financeiro"])
    
    with aba_op:
        col_d, col_h = st.columns(2)
        with col_d: data_t = st.date_input("Data")
        with col_h: hora_t = st.time_input("Hora")
        
        c1, c2, c3 = st.columns(3)
        with c1: pass_n = st.text_input("Passageiro")
        with c2: sol_n = st.text_input("Solicitante")
        with c3: cc_n = st.selectbox("Centro de Custo", CENTROS_DE_CUSTO)
        
        r_origem = st.text_input("Origem (Rua e Nº)")
        r_dest = st.text_input("Destino (Rua e Nº)")
        
        if st.button("Agendar Viagem", type="primary"):
            if r_origem and r_dest:
                res = calcular_rota_automatica([r_origem, r_dest], 0)
                if isinstance(res, dict):
                    dados = {
                        "ID": datetime.now().strftime("%Y%m%d%H%M%S"), "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "Data_Traslado": data_t.strftime("%d/%m/%Y"), "Hora_Embarque": hora_t.strftime("%H:%M"),
                        "Passageiro": pass_n, "Solicitante": sol_n, "Centro_Custo": cc_n,
                        "Origem": r_origem, "Destino": r_dest, "KM_Total": res['km'], "Valor_Total": res['total'], "Status": "Pendente"
                    }
                    if salvar_no_banco(dados): st.success(f"Ticket Gerado: R$ {res['total']}")
                else: st.error(res)

    with aba_fin:
        if st.button("Carregar Matriz Financeira"):
            try:
                sheet = conectar_planilha()
                if sheet:
                    dados_brutos = sheet.get_all_values()
                    if len(dados_brutos) > 1:
                        df = pd.DataFrame(dados_brutos[1:], columns=dados_brutos[0])
                        # VALIDAÇÃO DE COLUNAS SOLICITADA
                        if 'Valor_Total' in df.columns:
                            df['Valor_Total'] = pd.to_numeric(df['Valor_Total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                        if 'KM_Total' in df.columns:
                            df['KM_Total'] = pd.to_numeric(df['KM_Total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                        
                        st.bar_chart(df.groupby('Centro_Custo')['Valor_Total'].sum())
                        st.dataframe(df, use_container_width=True)
                        return True # Retorno solicitado
                    return False # Retorno solicitado (sem dados)
                return False # Retorno solicitado (sem conexão)
            except Exception as e:
                st.error(f"Erro: {e}")
                return False # Retorno solicitado (erro)

    if st.button("Sair"):
        st.session_state["autenticado"] = False
        st.rerun()

if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if not st.session_state["autenticado"]: tela_login()
else: tela_principal()
