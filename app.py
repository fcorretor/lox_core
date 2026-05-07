import streamlit as st
import traceback
import requests
from geopy.geocoders import Nominatim
from datetime import datetime
import urllib.parse
import json
import gspread
import pandas as pd # Necessário para a matriz do Centro de Custos

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 3.0 - Arquitetura de Custos
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}
NUMERO_WHATSAPP_CEO = "5551998186611" 

TARIFA_BASE = 20.00
VALOR_POR_KM = 1.80
VALOR_MINUTO_VIAGEM = 0.50
VALOR_MINUTO_ESPERA = 1.11

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul", 
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão"
]

# 1. NOVA ESTRUTURA DE CENTROS DE CUSTO
CENTROS_DE_CUSTO = [
    "Operacional (Polo Petroquímico)", 
    "Medicina do Trabalho", 
    "Diretoria/Executivo", 
    "Comercial"
]

def conectar_planilha():
    """
    Engenharia de Conexão: Modo Produção (Varthoz HQ)
    Extrai as credenciais diretamente do mapeamento TOML do Streamlit,
    blindando a aplicação contra falhas de I/O de arquivos locais.
    """
    try:
        # Extração determinística das chaves aninhadas no secrets.toml
        # Monta o dicionário em tempo de execução (Bootstrapping)
        credentials_dict = {
            "type": st.secrets["connections"]["gsheets"]["type"],
            "project_id": st.secrets["connections"]["gsheets"]["project_id"],
            "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
            "private_key": st.secrets["connections"]["gsheets"]["private_key"],
            "client_email": st.secrets["connections"]["gsheets"]["client_email"],
            "client_id": st.secrets["connections"]["gsheets"]["client_id"],
            "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
            "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["connections"]["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["connections"]["gsheets"]["client_x509_cert_url"],
            "universe_domain": st.secrets["connections"]["gsheets"].get("universe_domain", "googleapis.com")
        }
        
        # Autenticação direta via dicionário na memória
        client = gspread.service_account_from_dict(credentials_dict)
        
        # Conexão com o alvo B2B
        sheet = client.open_by_key("1rwrlPpSCc89nc12fP26oCNhWUhKtiKVbIOiCbFWqV44").worksheet("Página1")
        return sheet

    except KeyError as k_err:
        st.error("Erro Crítico: Chave ausente no secrets.toml.")
        print(f"[FALHA DE ARQUITETURA] Chave não encontrada: {k_err}")
        return None
    except Exception as e:
        st.error("Falha no handshake com o Google Cloud IAM.")
        print("\n--- ERRO CABELUDO DE CONEXÃO ---")
        traceback.print_exc()
        print("--------------------------------\n")
        return None

def salvar_no_banco(dados):
    """Atualizado para suportar a coluna Centro_Custo"""
    try:
        sheet = conectar_planilha()
        if sheet:
            # ATENÇÃO: Adicione a coluna 'Centro_Custo' na sua planilha Google
            linha = [
                dados["ID"], dados["Data_Agendamento"], dados["Data_Traslado"], 
                dados["Hora_Embarque"], dados["Passageiro"], dados["Solicitante"], 
                dados["Centro_Custo"], # <--- NOVA VARIÁVEL AQUI
                dados["Origem"], dados["Destino"], dados["KM_Total"], 
                dados["Valor_Total"], dados["Status"]
            ]
            sheet.append_row(linha)
            return True
        return False
    except Exception as e:
        st.error(f"Erro de I/O na nuvem: {e}")
        return False

def calcular_rota_automatica(enderecos, total_minutos_espera):
    try:
        # ARQUITETURA VARTHOZ: Aumentando o timeout para 10 segundos.
        # Isso impede o 'ReadTimeoutError' exibido no teu print.
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
        
        # Injeção de timeout também na requisição HTTP da rota
        resposta = requests.get(url_osrm, timeout=10).json() 
        if resposta.get("code") != "Ok": return "Erro ao traçar rota veicular."

        km = resposta['routes'][0]['distance'] / 1000
        minutos_reais = (resposta['routes'][0]['duration'] / 60) * 1.6
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except requests.exceptions.Timeout:
        return "Falha Crítica: O satélite de roteamento não respondeu a tempo. Tente novamente."
    except Exception as e:
        return f"Falha no ecossistema de roteamento: {e}"

def tela_login():
    st.title("🔒 Lox")
    st.markdown("**Sistema Integrado de Roteamento Executivo**")
    st.info("Acesso exclusivo para parceiros corporativos da Plataforma Lox.")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Acessar Plataforma"):
        if usuario in CREDENCIAIS and CREDENCIAIS[usuario] == senha:
            st.session_state["autenticado"] = True
            st.session_state["cliente"] = usuario
            st.rerun()
        else:
            st.error("Credenciais inválidas.")

def tela_principal():
    usuario_atual = st.session_state['cliente']
    
    # Sistema de Abas: Separa a Operação da Gestão Financeira
    aba_operacao, aba_financeiro = st.tabs(["🚘 Agendamento de Rotas", "📊 Gestão de Centros de Custo"])
    
    with aba_operacao:
        st.warning("⏱️ REGRA OPERACIONAL: Agendamentos com antecedência mínima de 1 Turno (4 horas).")
        
        col_data, col_hora = st.columns(2)
    with col_data:
        data_corrida = st.date_input("Data do Traslado")
    with col_hora:
        hora_corrida = st.time_input("Horário do Embarque")
    
    # ARQUITETURA B2B: Expansão para 3 colunas para incluir o Centro de Custo
    col_pass, col_sol, col_cc = st.columns(3)
    
    with col_pass:
        passageiro = st.text_input("Nome do Passageiro / Médico(a):", placeholder="Ex: Dr. XPTO")
    
    with col_sol:
        solicitante = st.text_input("Seu Nome e Contato (Para envio da NF):", placeholder="Ex: Fulano")
        
    with col_cc:
        CENTROS_DE_CUSTO = [
            "Operacional (Polo Petroquímico)", 
            "Medicina do Trabalho", 
            "Diretoria/Executivo", 
            "Comercial",
            "Outros"
        ]
        centro_custo = st.selectbox("Centro de Custo:", CENTROS_DE_CUSTO)

    st.markdown("---")
    tipo_rota = st.radio("Selecione a Modalidade do Traslado:", ["Nova Rota (Sob Demanda)", "Rota Homologada (Frequente)"])
    
    # IMPORTANTE: Quando fores montar o dicionário 'dados_corrida' lá embaixo para salvar no banco,
    # não esqueça de adicionar a chave: "Centro_Custo": centro_custo,

        # ... [MANTENHA A TUA LÓGICA DE ROTAS (DINÂMICA E FIXA)] ...
        # Na hora de montar o dicionário 'dados_corrida' e 'dados_fixa', adicione o parâmetro:
        # "Centro_Custo": centro_custo,

    with aba_financeiro:
        st.subheader("Auditoria de Despesas por Departamento")
        st.info("Aqui a Sulmed enxerga onde o dinheiro está alocado, validando a assimetria da nossa precificação.")
        
        if st.button("Carregar Matriz Financeira"):
            try:
                sheet = conectar_planilha()
                dados_tabela = sheet.get_all_records()
                if dados_tabela:
                    df = pd.DataFrame(dados_tabela)
                    
                    # Agrupamento matemático de custos
                    resumo_custos = df.groupby('Centro_Custo')['Valor_Total'].sum().reset_index()
                    resumo_custos.columns = ['Centro de Custo', 'Total Faturado (R$)']
                    
                    st.dataframe(resumo_custos, use_container_width=True)
                else:
                    st.warning("Sem dados processados.")
            except Exception as e:
                st.error("Erro ao puxar a malha financeira.")
                
    # ==========================================
    # SEÇÃO FAQ - O IMPACTO VISUAL DE SUPORTE
    # ==========================================
    st.markdown("---")
    with st.expander("❓ Perguntas Frequentes (FAQ) - Suporte Operacional"):
        st.markdown("""
        **1. O que é o Portal Lox?** É o sistema de gestão logística da Varthoz Express para a Sulmed.
        **2. Por que o valor é diferente?** O Lox opera com **Tarifa Dinâmica Zero**. O preço é fixo.
        **3. Qual a antecedência?** Solicitamos no mínimo **1 Turno (4 horas)** de antecedência.
        **4. Como recebo a Nota Fiscal?** Após o traslado, o Recibo Oficial é enviado com assinatura digital Gov.br.
        """)

    st.markdown("---")
    if st.button("Encerrar Sessão"):
        st.session_state["autenticado"] = False
        st.rerun()

if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if not st.session_state["autenticado"]: tela_login()
else: tela_principal()
