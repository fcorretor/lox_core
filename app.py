import streamlit as st
import traceback
import requests
from geopy.geocoders import Nominatim
from datetime import datetime, date
import urllib.parse
import gspread
import pandas as pd
from fpdf import FPDF
import tempfile
import os

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 6.1 - Arquitetura Purificada & Anti-Crash
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="wide")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}
NUMERO_WHATSAPP_CEO = "5551998186611"

TARIFA_BASE = 14.00
VALOR_POR_KM = 1.80
VALOR_MINUTO_VIAGEM = 0.25
VALOR_MINUTO_ESPERA = 1.20

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul", 
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "Santo Antônio da Patrulha",
    "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão"
]

CENTROS_DE_CUSTO = [
    "Operacional (Polo Petroquímico)", 
    "Medicina do Trabalho", 
    "Diretoria/Executivo", 
    "Comercial", 
    "Outros"
]

def sanitizar_texto_fpdf(texto):
    if not texto:
        return ""
    substituicoes = {
        "ã": "a", "á": "a", "à": "a", "â": "a",
        "ẽ": "e", "é": "e", "ê": "e",
        "ĩ": "i", "í": "i",
        "õ": "o", "ó": "o", "ô": "o",
        "ũ": "u", "ú": "u",
        "ç": "c",
        "Ã": "A", "Á": "A", "À": "A", "Â": "A",
        "Ẽ": "E", "É": "E", "Ê": "E",
        "Ĩ": "I", "Í": "I",
        "Õ": "O", "Ó": "O", "Ô": "O",
        "Ũ": "U", "Ú": "U",
        "Ç": "C"
    }
    for orig, sub in substituicoes.items():
        texto = texto.replace(orig, sub)
    return texto.encode('latin-1', 'replace').decode('latin-1')

def conectar_planilha():
    try:
        if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
            st.warning("Aviso: Configuração de st.secrets não localizada. Modo offline ativo.")
            return None
            
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
    except Exception as e:
        st.error(f"Falha técnica na conexão com banco de dados: {e}")
        return None

def salvar_no_banco(dados):
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
        st.error(f"Erro ao salvar registro: {e}")
        return False

def calcular_rota_automatica(enderecos, total_minutos_espera):
    try:
        geolocator = Nominatim(user_agent="lox_routing_b2b_v10", timeout=10) 
        coordenadas_list = []
        for end in enderecos:
            if not end or end.strip() == "": continue
            query = f"{end}, Rio Grande do Sul, Brasil"
            loc = geolocator.geocode(query)
            if not loc: return f"Erro: Endereço não localizado ({end})."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")

        if len(coordenadas_list) < 2: return "Erro: Necessário origem e destino válidos."

        coords_string = ";".join(coordenadas_list)
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?overview=false"
        resposta = requests.get(url_osrm, timeout=10).json() 
        if resposta.get("code") != "Ok": return "Erro ao traçar rota veicular."

        km = resposta['routes'][0]['distance'] / 1000
        minutos_reais = (resposta['routes'][0]['duration'] / 60) * 1.6
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except Exception as e:
        return f"Falha no ecossistema de roteamento: {e}"

def gerar_recibo_texto(dados, espera_total, enderecos=None):
    data_emissao = datetime.now().strftime("%d/%m/%Y")
    
    if dados['Destino'] == "Rota Fixa Homologada":
        if "(Ida)" in dados['Hora_Embarque']:
            h_ida = dados['Hora_Embarque'].split("(Ida)")[0].strip()
            h_volta = dados['Hora_Embarque'].split("|")[1].replace("(Volta)", "").strip()
            destino_clean = "Triunfo (Braskem)" if "Braskem" in dados['Origem'] else "Alvorada (Distrito Industrial)"
            detalhe_rota = f"IDA (Saída {h_ida}): Porto Alegre -> {destino_clean}\nVOLTA (Saída {h_volta}): {destino_clean} -> Porto Alegre\nRef. Rota: {dados['Origem']}"
        else:
            detalhe_rota = f"Rota Homologada   : {dados['Origem']}"
            
    elif enderecos and len(enderecos) >= 2:
        linhas_trajeto = [f"Embarque         : {enderecos[0]}"]
        is_circular = (enderecos[-1] == enderecos[0] and len(enderecos) > 1)
        
        if is_circular:
            miolo = enderecos[1:-1]
            if len(miolo) == 1:
                linhas_trajeto.append(f"Destino          : {miolo[0]}")
            elif len(miolo) > 1:
                for idx, p in enumerate(miolo[:-1]):
                    linhas_trajeto.append(f"Parada {idx+1}         : {p}")
                linhas_trajeto.append(f"Destino          : {miolo[-1]}")
            linhas_trajeto.append(f"Retorno          : {enderecos[-1]}")
        else:
            miolo = enderecos[1:-1]
            for idx, p in enumerate(miolo):
                linhas_trajeto.append(f"Parada {idx+1}         : {p}")
            linhas_trajeto.append(f"Destino          : {enderecos[-1]}")
            
        detalhe_rota = "\n".join(linhas_trajeto)
    else:
        detalhe_rota = f"Embarque         : {dados['Origem']}\nDestino          : {dados['Destino']}"

    if espera_total > 0:
        custo_espera = espera_total * VALOR_MINUTO_ESPERA
        linha_espera = f"Espera Técnica   : {espera_total} minutos (Índice: R$ {VALOR_MINUTO_ESPERA:.2f}/min | Subtotal: R$ {custo_espera:.2f})"
    else:
        linha_espera = "Espera Técnica   : 0 minutos"

    recibo = f"""=====================================================================
RECIBO DE PRESTAÇÃO DE SERVIÇOS E REEMBOLSO DE DESPESAS
=====================================================================
Nº da Transação : {dados['ID']}
Data de Emissão : {data_emissao}

TOMADOR DO SERVIÇO:
Razão Social: SULMED ASSISTÊNCIA MÉDICA LTDA.
Solicitante: {dados['Solicitante']} (Centro de Custo: {dados['Centro_Custo']})
---------------------------------------------------------------------
DESCRIÇÃO DETALHADA DOS SERVIÇOS:
Serviços de logística e transporte executivo de pessoal.
Data do Traslado: {dados['Data_Traslado']} às {dados['Hora_Embarque']}
Passageiro(s)   : {dados['Passageiro']}
{detalhe_rota}
{linha_espera}
---------------------------------------------------------------------
VALOR TOTAL PELOS SERVIÇOS PRESTADOS: R$ {dados['Valor_Total']:.2f}
---------------------------------------------------------------------
FRANCESCO DE ANDRADE APRATTO
====================================================================="""
    return recibo

def gerar_html_dinamico(texto_recibo):
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: monospace; font-size: 14px; padding: 20px; }}
        pre {{ white-space: pre-wrap; }}
    </style>
</head>
<body onload="setTimeout(function(){{ window.print(); }}, 500);">
<pre>{texto_recibo}</pre>
</body>
</html>"""
    return html_content.encode('utf-8')

def tela_login():
    st.title("🔒 Lox | Login Corporativo")
    st.info("Autenticação exigida para emissão e auditoria.")
    
    with st.form("form_login"):
        usuario = st.text_input("Usuário").strip().lower()
        senha = st.text_input("Senha", type="password").strip()
        submit = st.form_submit_button("Acessar Painel")
        
        if submit:
            if usuario in CREDENCIAIS and CREDENCIAIS[usuario] == senha:
                st.session_state["autenticado"] = True
                st.session_state["cliente"] = usuario
                st.rerun()
            else:
                st.error("Credenciais inválidas. Acesso negado.")

def modulo_passageiros():
    nomes_exibicao = {"tiesco": "Francesco", "sulmed": "Sulmed Administrativo"}
    usuario_atual = st.session_state.get('cliente', 'tiesco')
    st.success(f"Operador Logado: {nomes_exibicao.get(usuario_atual, usuario_atual.capitalize())}")
    st.title("🚘 Cotação e Agendamento Lox")
    
    aba_operacao, aba_financeiro = st.tabs(["🛣️ Operação (Rotas)", "📊 Gestão Financeira (CC)"])
    
    with aba_operacao:
        col_data, col_hora_ida, col_hora_volta = st.columns(3)
        with col_data: data_corrida = st.date_input("Data do Traslado", date.today())
        with col_hora_ida: hora_corrida = st.time_input("Horário de Ida", step=60)
        with col_hora_volta: 
            tem_volta = st.checkbox("Incluir Hora da Volta?")
            hora_retorno = st.time_input("Horário da Volta", step=60) if tem_volta else None
            
        hora_db_str = f"{hora_corrida.strftime('%H:%M')} (Ida) | {hora_retorno.strftime('%H:%M')} (Volta)" if hora_retorno else hora_corrida.strftime("%H:%M")
        
        col_pass, col_sol, col_cc = st.columns(3)
        with col_pass: passageiro = st.text_input("Passageiro / Médico(a):", placeholder="Ex: Dr. XPTO")
        with col_sol: solicitante = st.text_input("Seu Nome e Contato:", placeholder="Ex: Fulano")
        with col_cc: centro_custo = st.selectbox("Centro de Custo:", CENTROS_DE_CUSTO)

        st.markdown("---")
        tipo_rota = st.radio("Selecione a Modalidade do Traslado:", ["Nova Rota (Sob Demanda)", "Rota Homologada (Frequente)"])
        st.markdown("---")

        if tipo_rota == "Nova Rota (Sob Demanda)":
            col_rua_origem, col_cid_origem = st.columns([3, 1])
            with col_rua_origem: rua_origem = st.text_input("Endereço de Embarque (Rua e Nº)")
            with col_cid_origem: cid_origem = st.selectbox("Cidade (Origem)", CIDADES_RMPA, key="cid_origem")
            origem_completa = f"{rua_origem} - {cid_origem}" if rua_origem else ""

            qtd_paradas = st.selectbox("Paradas Intermediárias:", [0, 1, 2, 3])
            paradas_completas = []
            espera_total = 0
            
            for i in range(qtd_paradas):
                col_r, col_c, col_e = st.columns([5, 3, 2])
                with col_r: p_rua = st.text_input("Rua e Nº", key=f"p_rua_{i}")
                with col_c: p_cid = st.selectbox("Cidade", CIDADES_RMPA, key=f"p_cid_{i}")
                with col_e: e_min = st.number_input("Espera (min)", min_value=0, step=5, key=f"e_{i}")
                if p_rua:
                    paradas_completas.append(f"{p_rua} - {p_cid}")
                    espera_total += e_min

            col_rua_dest, col_cid_dest = st.columns([3, 1])
            with col_rua_dest: rua_dest = st.text_input("Endereço de Desembarque Final")
            with col_cid_dest: cid_dest = st.selectbox("Cidade (Destino)", CIDADES_RMPA, key="cid_dest")
            destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
            ida_e_volta = st.checkbox("🔄 Retornar à Base")

            if st.button("Calcular e Agendar", type="primary"):
                enderecos_brutos = []
                if origem_completa: enderecos_brutos.append(origem_completa)
                enderecos_brutos.extend(paradas_completas)
                if destino_completo: enderecos_brutos.append(destino_completo)
                if ida_e_volta and origem_completa: enderecos_brutos.append(origem_completa)
                
                enderecos_pesquisa = []
                for end in enderecos_brutos:
                    if not enderecos_pesquisa or enderecos_pesquisa[-1] != end:
                        enderecos_pesquisa.append(end)
                
                if len(enderecos_pesquisa) >= 2 and rua_origem and rua_dest:
                    with st.spinner("Processando geolocalização e matriz financeira..."):
                        resultado = calcular_rota_automatica(enderecos_pesquisa, espera_total)
                    
                    if isinstance(resultado, dict):
                        dados_corrida = {
                            "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                            "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "Data_Traslado": data_corrida.strftime("%d/%m/%Y"),
                            "Hora_Embarque": hora_db_str,
                            "Passageiro": passageiro,
                            "Solicitante": solicitante,
                            "Centro_Custo": centro_custo,
                            "Origem": origem_completa,
                            "Destino": f"{enderecos_pesquisa[-1]} (I/V)" if ida_e_volta else enderecos_pesquisa[-1],
                            "KM_Total": resultado['km'],
                            "Valor_Total": resultado['total'],
                            "Status": "Pendente"
                        }
                        
                        salvar_no_banco(dados_corrida)
                        st.success(f"## VALOR FINAL: R$ {resultado['total']:.2f}")
                        texto_recibo = gerar_recibo_texto(dados_corrida, espera_total, enderecos_pesquisa)
                        st.download_button(label="📄 Gerar Recibo B2B (Auto-PDF)", data=gerar_html_dinamico(texto_recibo), file_name="recibo.html", mime="text/html")
                    else: st.error(resultado)
                else: st.warning("Preencha Origem e Destino para cálculo da rota.")

        else:
            rota_fixa = st.selectbox("Selecione a Rota:", ["Porto Alegre <-> Braskem (Triunfo)", "Porto Alegre <-> Distrito Industrial (Alvorada)"])
            espera_extra = st.number_input("Espera Extra (min)", min_value=0, step=5)

            if st.button("Gerar Pedido", type="primary"):
                valor_base = 250.00 if "Braskem" in rota_fixa else 125.00
                valor_final = valor_base + (espera_extra * VALOR_MINUTO_ESPERA)
                
                dados_fixa = {
                    "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "Data_Traslado": data_corrida.strftime("%d/%m/%Y"),
                    "Hora_Embarque": hora_db_str, "Passageiro": passageiro, "Solicitante": solicitante,
                    "Centro_Custo": centro_custo, "Origem": rota_fixa, "Destino": "Rota Fixa Homologada",
                    "KM_Total": 0, "Valor_Total": valor_final, "Status": "Pendente"
                }
                salvar_no_banco(dados_fixa)
                st.success(f"## VALOR FINAL: R$ {valor_final:.2f}")

    with aba_financeiro:
        if st.button("Carregar Matriz"):
            sheet = conectar_planilha()
            if sheet:
                dados_brutos = sheet.get_all_values()
                if len(dados_brutos) > 1:
                    df = pd.DataFrame(dados_brutos[1:], columns=dados_brutos[0])
                    if 'Valor_Total' in df.columns:
                        df['Valor_Total'] = pd.to_numeric(df['Valor_Total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                        st.dataframe(df.groupby('Centro_Custo')['Valor_Total'].sum().reset_index(), use_container_width=True)

# ==========================================
# MÓDULO 2: LOGÍSTICA B2B (SULMED)
# ==========================================
def gerar_pdf_entregas(id_os, data_em, cliente, desc, valor_b, valor_a, valor_t):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        
        pdf.cell(190, 10, txt=sanitizar_texto_fpdf("Recibo de Operacao Logistica e Distribuicao B2B"), ln=True, align='C')
        
        pdf.set_font("Arial", size=12)
        pdf.ln(10)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf(f"Ordem de Servico: {id_os}"), ln=True)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf(f"Data de Emissao: {data_em}"), ln=True)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf(f"Tomador: {cliente}"), ln=True)
        pdf.multi_cell(190, 8, txt=sanitizar_texto_fpdf(f"Escopo/Roteiro: {desc}"))
        
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf("Composicao Financeira:"), ln=True)
        pdf.set_font("Arial", size=12)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf(f"SLA Base: R$ {valor_b:.2f}"), ln=True)
        pdf.cell(190, 8, txt=sanitizar_texto_fpdf(f"Taxa de Anomalia/Retorno: R$ {valor_a:.2f}"), ln=True)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(190, 10, txt=sanitizar_texto_fpdf(f"TOTAL A PAGAR: R$ {valor_t:.2f}"), ln=True)
        
        pdf.ln(10)
        pdf.set_font("Arial", size=10)
        pdf.cell(190, 6, txt=sanitizar_texto_fpdf("Quitacao mediante PIX: [REDACTED-PIX-CPF]"), ln=True)
        pdf.cell(190, 6, txt=sanitizar_texto_fpdf("Francesco de Andrade Apratto"), ln=True)
        
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        pdf.output(path)
        return path
    except Exception as e:
        st.error(f"Erro na renderização do vetor FPDF: {e}")
        return None

def modulo_entregas():
    st.title("📦 Emissor de Faturamento B2B (Sulmed)")
    st.info("Geração estrita de documentos corporativos em formato PDF padrão auditoria.")
    
    with st.form("form_faturamento_b2b"):
        id_os = st.text_input("ID da Ordem de Serviço", f"OS-{datetime.now().strftime('%Y%m%d')}-SUL")
        data_emissao = st.date_input("Data de Emissão", date.today())
        cliente = st.text_input("Tomador do Serviço", "SULMED ASSISTÊNCIA MÉDICA LTDA")
        descricao = st.text_area("Roteiro e Ocorrências", "Coleta (...) -> Entrega (...) -> Re-entrega (...)")
        
        col1, col2 = st.columns(2)
        with col1: v_base = st.number_input("Valor Base (R$)", min_value=0.0, value=0.0, step=5.0)
        with col2: v_taxa = st.number_input("Taxas de Anomalia (R$)", min_value=0.0, value=0.0, step=5.0)
        
        submit = st.form_submit_button("Gerar PDF de Cobrança")
        
        if submit:
            if v_base <= 0:
                st.warning("Insira o valor base do serviço para processar o faturamento.")
            else:
                v_total = v_base + v_taxa
                caminho_pdf = gerar_pdf_entregas(id_os, data_emissao.strftime('%d/%m/%Y'), cliente, descricao, v_base, v_taxa, v_total)
                if caminho_pdf:
                    with open(caminho_pdf, "rb") as f:
                        pdf_bytes = f.read()
                    st.success(f"Faturamento Processado: R$ {v_total:.2f}")
                    st.download_button(
                        label="⬇️ Baixar PDF Assinável (Gov.br)",
                        data=pdf_bytes,
                        file_name=f"{id_os}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )

# ==========================================
# ROTEADOR DE ARQUITETURA
# ==========================================
def roteador_principal():
    st.sidebar.title("SylvaCore | Lox")
    st.sidebar.markdown("---")
    
    modalidade = st.sidebar.radio(
        "Selecione o Módulo:",
        ["Traslado (Passageiros)", "Logística B2B (Faturamento)"]
    )
    
    if modalidade == "Traslado (Passageiros)":
        modulo_passageiros()
    elif modalidade == "Logística B2B (Faturamento)":
        modulo_entregas()
        
    st.sidebar.markdown("---")
    if st.sidebar.button("Encerrar Sessão"):
        st.session_state["autenticado"] = False
        st.rerun()

# ==========================================
# EXECUÇÃO DA APLICAÇÃO (ISOLAMENTO DE ERRO)
# ==========================================
if __name__ == "__main__":
    try:
        if "autenticado" not in st.session_state: 
            st.session_state["autenticado"] = False

        if not st.session_state["autenticado"]: 
            tela_login()
        else: 
            roteador_principal()
    except Exception as fatal_error:
        st.error("⚠️ Falha Crítica de Execução na Aplicação")
        st.code(traceback.format_exc())
