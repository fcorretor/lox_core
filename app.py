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
    nomes_exibicao = {"tiesco": "Francesco", "sulmed": "Sulmed Administrativo"}
    usuario_atual = st.session_state['cliente']
    nome_operador = nomes_exibicao.get(usuario_atual, usuario_atual.capitalize())
    
    st.success(f"Operador Logado: {nome_operador}")
    st.title("🚘 Cotação e Agendamento Lox")
    
    # Sistema de Abas: Separa a Operação da Gestão Financeira B2B
    aba_operacao, aba_financeiro = st.tabs(["🛣️ Agendamento de Rotas", "📊 Gestão de Centros de Custo"])
    
    with aba_operacao:
        st.warning("⏱️ REGRA OPERACIONAL: Agendamentos com antecedência mínima de 1 Turno (4 horas).")
        
        col_data, col_hora = st.columns(2)
        with col_data:
            data_corrida = st.date_input("Data do Traslado")
        with col_hora:
            hora_corrida = st.time_input("Horário do Embarque")
        
        # ARQUITETURA B2B: Expansão para 3 colunas (Centro de Custo Ativo)
        col_pass, col_sol, col_cc = st.columns(3)
        
        with col_pass:
            passageiro = st.text_input("Passageiro / Médico(a):", placeholder="Ex: Dr. XPTO")
        
        with col_sol:
            solicitante = st.text_input("Seu Nome e Contato:", placeholder="Ex: Fulano")
            
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
        st.markdown("---")

        if tipo_rota == "Nova Rota (Sob Demanda)":
            st.markdown("### 📍 Rota Dinâmica")
            col_rua_origem, col_cid_origem = st.columns([3, 1])
            with col_rua_origem:
                rua_origem = st.text_input("Endereço de Embarque (Rua e Nº)", placeholder="Ex: Rua Barros Cassal, 411")
            with col_cid_origem:
                cid_origem = st.selectbox("Cidade (Origem)", CIDADES_RMPA, key="cid_origem")
            origem_completa = f"{rua_origem} - {cid_origem}" if rua_origem else ""

            qtd_paradas = st.selectbox("Paradas Intermediárias:", [0, 1, 2, 3])
            paradas_completas = []
            espera_total = 0
            
            for i in range(qtd_paradas):
                st.markdown(f"**Parada {i+1}**")
                col_r, col_c, col_e = st.columns([5, 3, 2])
                with col_r:
                    p_rua = st.text_input(f"Rua e Nº", key=f"p_rua_{i}")
                with col_c:
                    p_cid = st.selectbox(f"Cidade", CIDADES_RMPA, key=f"p_cid_{i}")
                with col_e:
                    e_min = st.number_input("Espera (min)", min_value=0, step=5, key=f"e_{i}")
                if p_rua:
                    paradas_completas.append(f"{p_rua} - {p_cid}")
                    espera_total += e_min

            col_rua_dest, col_cid_dest = st.columns([3, 1])
            with col_rua_dest:
                rua_dest = st.text_input("Endereço de Desembarque Final (Rua e Nº)")
            with col_cid_dest:
                cid_dest = st.selectbox("Cidade (Destino)", CIDADES_RMPA, key="cid_dest")
            destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
            ida_e_volta = st.checkbox("🔄 Retornar à Base (O desembarque final será igual à Origem)")

            if st.button("Calcular e Agendar", type="primary"):
                enderecos_pesquisa = []
                if origem_completa: enderecos_pesquisa.append(origem_completa)
                enderecos_pesquisa.extend(paradas_completas)
                if destino_completo: enderecos_pesquisa.append(destino_completo)
                if ida_e_volta and origem_completa: enderecos_pesquisa.append(origem_completa)
                
                if len(enderecos_pesquisa) >= 2 and rua_origem and rua_dest:
                    with st.spinner("Processando satélites e gravando no banco..."):
                        resultado = calcular_rota_automatica(enderecos_pesquisa, espera_total)
                    
                    if isinstance(resultado, dict):
                        rota_resumo = " -> ".join(enderecos_pesquisa)
                        
                        # Injeção no Banco com Centro de Custo
                        dados_corrida = {
                            "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                            "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "Data_Traslado": data_corrida.strftime("%d/%m/%Y"),
                            "Hora_Embarque": hora_corrida.strftime("%H:%M"),
                            "Passageiro": passageiro,
                            "Solicitante": solicitante,
                            "Centro_Custo": centro_custo,
                            "Origem": origem_completa,
                            "Destino": destino_completo if not ida_e_volta else f"Retorno para {origem_completa}",
                            "KM_Total": resultado['km'],
                            "Valor_Total": resultado['total'],
                            "Status": "Pendente"
                        }
                        
                        if salvar_no_banco(dados_corrida):
                            st.markdown("### 🧾 Ticket de Cotação Lox")
                            st.success(f"## VALOR FINAL ESTIMADO: R$ {resultado['total']:.2f}")
                            st.info("✅ Registro gravado na Matriz Financeira (Aba Gestão).")
                            
                            mensagem_wa = f"*NOVO AGENDAMENTO - LOX B2B*\n\n*CC:* {centro_custo}\n*Passageiro:* {passageiro}\n*Solicitante:* {solicitante}\n*Data:* {data_corrida.strftime('%d/%m/%Y')} às {hora_corrida.strftime('%H:%M')}\n*Rota:* {rota_resumo}\n*Valor:* R$ {resultado['total']:.2f}"
                            msg_codificada = urllib.parse.quote(mensagem_wa)
                            link_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP_CEO}?text={msg_codificada}"
                            
                            st.markdown(f'<a href="{link_whatsapp}" target="_blank"><button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">📲 ENVIAR AGENDAMENTO VIA WHATSAPP</button></a>', unsafe_allow_html=True)
                    else: st.error(resultado)
                else:
                    st.warning("Preencha Origem e Destino de forma clara.")

        else:
            st.info("Rotas com valores fixos homologados.")
            rota_fixa = st.selectbox("Selecione a Rota:", ["Porto Alegre <-> Braskem Unidade Q2 (Triunfo) [Ida e Volta]", "Porto Alegre <-> Distrito Industrial (Alvorada) [Ida e Volta]"])
            espera_extra = st.number_input("Espera Extra (min)", min_value=0, step=5)

            if st.button("Gerar Pedido de Rota Fixa", type="primary"):
                valor_base = 250.00 if "Braskem" in rota_fixa else 125.00
                valor_final = valor_base + (espera_extra * VALOR_MINUTO_ESPERA)
                
                with st.spinner("Gravando na matriz..."):
                    dados_fixa = {
                        "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "Data_Traslado": data_corrida.strftime("%d/%m/%Y"),
                        "Hora_Embarque": hora_corrida.strftime("%H:%M"),
                        "Passageiro": passageiro,
                        "Solicitante": solicitante,
                        "Centro_Custo": centro_custo,
                        "Origem": rota_fixa,
                        "Destino": "Rota Fixa Homologada",
                        "KM_Total": 0,
                        "Valor_Total": valor_final,
                        "Status": "Pendente"
                    }
                    salvou = salvar_no_banco(dados_fixa)
                
                if salvou:
                    st.success(f"## VALOR FINAL: R$ {valor_final:.2f}")
                    st.info("✅ Registro financeiro gravado com sucesso.")
                    mensagem_wa_fixa = f"*AGENDAMENTO ROTA FIXA - LOX B2B*\n\n*CC:* {centro_custo}\n*Passageiro:* {passageiro}\n*Rota:* {rota_fixa}\n*Valor:* R$ {valor_final:.2f}"
                    st.markdown(f'<a href="https://wa.me/{NUMERO_WHATSAPP_CEO}?text={urllib.parse.quote(mensagem_wa_fixa)}" target="_blank"><button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">📲 ENVIAR AGENDAMENTO VIA WHATSAPP</button></a>', unsafe_allow_html=True)

    with aba_financeiro:
        st.subheader("Auditoria de Despesas por Departamento")
        st.info("Visão exclusiva da diretoria: Mapeamento do custo de transporte por setor (Value-Based Pricing).")
        
        if st.button("Carregar Matriz Financeira"):
            try:
                sheet = conectar_planilha()
                dados_tabela = sheet.get_all_records()
                if dados_tabela:
                    df = pd.DataFrame(dados_tabela)
                    resumo_custos = df.groupby('Centro_Custo')['Valor_Total'].sum().reset_index()
                    resumo_custos.columns = ['Centro de Custo', 'Total Faturado (R$)']
                    st.dataframe(resumo_custos, use_container_width=True)
                else:
                    st.warning("Ainda não há dados processados na base.")
            except Exception as e:
                st.error("Erro ao puxar a malha financeira. Verifique o Google Sheets.")
        if dados_tabela:
        df = pd.DataFrame(dados_tabela)
        
        st.markdown("### 📈 Análise Visual de Impacto")
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.write("Distribuição por Centro de Custo")
            # Gráfico de barras simples com a matriz de valores
            chart_data = df.groupby('Centro_Custo')['Valor_Total'].sum()
            st.bar_chart(chart_data)
            
        with col_chart2:
            st.write("Volume de KM por Departamento")
            km_data = df.groupby('Centro_Custo')['KM_Total'].sum()
            st.area_chart(km_data)
               
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

# ==========================================
# MÁQUINA DE ESTADO DO SISTEMA (Fora de qualquer função)
# ==========================================
if "autenticado" not in st.session_state: 
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]: 
    tela_login()
else: 
    tela_principal()
