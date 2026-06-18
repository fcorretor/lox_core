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
# Versão: 5.14 - Clean Output & Print Header Bypass
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

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

def conectar_planilha():
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
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except requests.exceptions.Timeout:
        return "Falha Crítica: O satélite não respondeu a tempo."
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
            detalhe_rota = f"Rota Homologada  : {dados['Origem']}"
            
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

    # Aviso inútil de assinatura removido da formatação bruta
    recibo = f"""=====================================================================
RECIBO DE PRESTAÇÃO DE SERVIÇOS E REEMBOLSO DE DESPESAS
=====================================================================
Nº da Transação : {dados['ID']}
Data de Emissão : {data_emissao}

TOMADOR DO SERVIÇO:
Razão Social: SULMED ASSISTÊNCIA MÉDICA LTDA.
CNPJ: 90.747.908/0001-56
Solicitante: {dados['Solicitante']} (Centro de Custo: {dados['Centro_Custo']})
---------------------------------------------------------------------
DESCRIÇÃO DETALHADA DOS SERVIÇOS:
Serviços de logística e transporte executivo de pessoal, realizados em
veículo particular, conforme detalhamento abaixo:

Data do Traslado: {dados['Data_Traslado']} às {dados['Hora_Embarque']}
Passageiro(s)   : {dados['Passageiro']}
{detalhe_rota}
{linha_espera}
---------------------------------------------------------------------
VALOR TOTAL PELOS SERVIÇOS PRESTADOS: R$ {dados['Valor_Total']:.2f}
---------------------------------------------------------------------
Declaro que a quitação se dará mediante o crédito em conta.

DADOS PARA PAGAMENTO:
Chave PIX: [REDACTED-PIX-CPF]
Banco: 0260 - Nu Pagamentos S.A. - Instituição de Pagamento
Favorecido: Francesco de Andrade Apratto
CPF: [REDACTED-PIX-CPF]

---------------------------------------------------------------------
FRANCESCO DE ANDRADE APRATTO
Gestão Logística & Projetos
====================================================================="""
    return recibo

def gerar_html_dinamico(texto_recibo):
    """
    CSS @page { margin: 0; } desativa os cabeçalhos/rodapés automáticos do navegador.
    body { padding: 15mm; } recompõe a margem interna do PDF para não colar o texto na borda.
    """
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Recibo B2B Varthoz</title>
    <style>
        body {{ font-family: 'Courier New', Courier, monospace; font-size: 14px; line-height: 1.3; color: #000; background: #fff; padding: 20px; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; font-family: inherit; border: none; overflow: hidden; margin: 0; }}
        @media print {{
            @page {{ margin: 0; size: A4 portrait; }}
            body {{ padding: 20mm; }} 
        }}
    </style>
</head>
<body onload="setTimeout(function(){{ window.print(); }}, 500);">
<pre>
{texto_recibo}
</pre>
</body>
</html>"""
    return html_content.encode('utf-8')

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
    
    aba_operacao, aba_financeiro = st.tabs(["🛣️ Operação (Rotas)", "📊 Gestão Financeira (CC)"])
    
    with aba_operacao:
        st.warning("⏱️ REGRA OPERACIONAL: Agendamentos com antecedência mínima de 1 Turno (4 horas).")
        
        col_data, col_hora_ida, col_hora_volta = st.columns(3)
        with col_data: data_corrida = st.date_input("Data do Traslado")
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
            st.markdown("### 📍 Rota Dinâmica")
            col_rua_origem, col_cid_origem = st.columns([3, 1])
            with col_rua_origem: rua_origem = st.text_input("Endereço de Embarque (Rua e Nº)", placeholder="Ex: Rua Barros Cassal, 411")
            with col_cid_origem: cid_origem = st.selectbox("Cidade (Origem)", CIDADES_RMPA, key="cid_origem")
            origem_completa = f"{rua_origem} - {cid_origem}" if rua_origem else ""

            qtd_paradas = st.selectbox("Paradas Intermediárias:", [0, 1, 2, 3])
            paradas_completas = []
            espera_total = 0
            
            for i in range(qtd_paradas):
                st.markdown(f"**Parada {i+1}**")
                col_r, col_c, col_e = st.columns([5, 3, 2])
                with col_r: p_rua = st.text_input(f"Rua e Nº", key=f"p_rua_{i}")
                with col_c: p_cid = st.selectbox(f"Cidade", CIDADES_RMPA, key=f"p_cid_{i}")
                with col_e: e_min = st.number_input("Espera (min)", min_value=0, step=5, key=f"e_{i}")
                if p_rua:
                    paradas_completas.append(f"{p_rua} - {p_cid}")
                    espera_total += e_min

            col_rua_dest, col_cid_dest = st.columns([3, 1])
            with col_rua_dest: rua_dest = st.text_input("Endereço de Desembarque Final (Rua e Nº)")
            with col_cid_dest: cid_dest = st.selectbox("Cidade (Destino)", CIDADES_RMPA, key="cid_dest")
            destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
            ida_e_volta = st.checkbox("🔄 Retornar à Base (O desembarque final será igual à Origem)")

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
                    with st.spinner("Processando satélites e gravando no banco..."):
                        resultado = calcular_rota_automatica(enderecos_pesquisa, espera_total)
                    
                    if isinstance(resultado, dict):
                        rota_resumo = " -> ".join(enderecos_pesquisa)
                        dados_corrida = {
                            "ID": datetime.now().strftime("%Y%m%d%H%M%S"),
                            "Data_Agendamento": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "Data_Traslado": data_corrida.strftime("%d/%m/%Y"),
                            "Hora_Embarque": hora_db_str,
                            "Passageiro": passageiro,
                            "Solicitante": solicitante,
                            "Centro_Custo": centro_custo,
                            "Origem": origem_completa,
                            "Destino": f"{enderecos_pesquisa[-1]} (Ida e Volta)" if ida_e_volta else enderecos_pesquisa[-1],
                            "KM_Total": resultado['km'],
                            "Valor_Total": resultado['total'],
                            "Status": "Pendente"
                        }
                        
                        if salvar_no_banco(dados_corrida):
                            st.success(f"## VALOR FINAL ESTIMADO: R$ {resultado['total']:.2f}")
                            texto_recibo = gerar_recibo_texto(dados_corrida, espera_total, enderecos_pesquisa)
                            
                            html_bytes = gerar_html_dinamico(texto_recibo)
                            st.download_button(
                                label="📄 Gerar Recibo B2B (Auto-PDF)",
                                data=html_bytes,
                                file_name=f"Francesco_NF_RPSRD{dados_corrida['ID']}.html",
                                mime="text/html",
                                type="primary",
                                use_container_width=True
                            )
                            
                            st.markdown("### Pré-visualização do Recibo")
                            st.code(texto_recibo, language="markdown")
                            
                            mensagem_wa = f"*NOVO AGENDAMENTO - LOX B2B*\n\n*CC:* {centro_custo}\n*Passageiro:* {passageiro}\n*Solicitante:* {solicitante}\n*Data:* {data_corrida.strftime('%d/%m/%Y')}\n*Horários:* {hora_db_str}\n*Rota:* {rota_resumo}\n*Valor:* R$ {resultado['total']:.2f}"
                            msg_codificada = urllib.parse.quote(mensagem_wa)
                            link_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP_CEO}?text={msg_codificada}"
                            
                            st.markdown(f'<a href="{link_whatsapp}" target="_blank"><button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">📲 APROVAR E ENVIAR WHATSAPP</button></a>', unsafe_allow_html=True)
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
                        "Hora_Embarque": hora_db_str,
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
                    texto_recibo_fixo = gerar_recibo_texto(dados_fixa, espera_extra)
                    
                    html_bytes_fixo = gerar_html_dinamico(texto_recibo_fixo)
                    st.download_button(
                        label="📄 Gerar Recibo B2B (Auto-PDF)",
                        data=html_bytes_fixo,
                        file_name=f"Francesco_NF_RPSRD{dados_fixa['ID']}.html",
                        mime="text/html",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.markdown("### Pré-visualização do Recibo")
                    st.code(texto_recibo_fixo, language="markdown")

                    mensagem_wa_fixa = f"*AGENDAMENTO ROTA FIXA - LOX B2B*\n\n*CC:* {centro_custo}\n*Passageiro:* {passageiro}\n*Horários:* {hora_db_str}\n*Rota:* {rota_fixa}\n*Valor:* R$ {valor_final:.2f}"
                    st.markdown(f'<a href="https://wa.me/{NUMERO_WHATSAPP_CEO}?text={urllib.parse.quote(mensagem_wa_fixa)}" target="_blank"><button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">📲 APROVAR E ENVIAR WHATSAPP</button></a>', unsafe_allow_html=True)

    with aba_financeiro:
        st.subheader("Auditoria de Despesas por Departamento")
        st.info("Visão exclusiva da diretoria: Mapeamento do custo de transporte por setor (Value-Based Pricing).")
        
        if st.button("Carregar Matriz Financeira"):
            try:
                sheet = conectar_planilha()
                if sheet:
                    dados_brutos = sheet.get_all_values()
                    if len(dados_brutos) > 1:
                        df = pd.DataFrame(dados_brutos[1:], columns=dados_brutos[0])
                        df = df.loc[:, df.columns != '']
                        
                        if 'Valor_Total' in df.columns:
                            df['Valor_Total'] = pd.to_numeric(df['Valor_Total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                        if 'KM_Total' in df.columns:
                            df['KM_Total'] = pd.to_numeric(df['KM_Total'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                        
                        st.markdown("### 📈 Análise Visual de Impacto")
                        col_chart1, col_chart2 = st.columns(2)
                        
                        with col_chart1:
                            st.write("Distribuição por Centro de Custo")
                            if 'Valor_Total' in df.columns:
                                st.bar_chart(df.groupby('Centro_Custo')['Valor_Total'].sum())
                            
                        with col_chart2:
                            st.write("Volume de KM por Departamento")
                            if 'KM_Total' in df.columns:
                                st.area_chart(df.groupby('Centro_Custo')['KM_Total'].sum())
                            
                        if 'Valor_Total' in df.columns:
                            resumo_custos = df.groupby('Centro_Custo')['Valor_Total'].sum().reset_index()
                            resumo_custos.columns = ['Centro de Custo', 'Total Faturado (R$)']
                            st.dataframe(resumo_custos, use_container_width=True)
                    else:
                        st.warning("Ainda não há dados processados na base.")
                else:
                    st.error("Falha ao conectar com o banco de dados (Google Sheets).")
            except Exception as e:
                st.error(f"Erro de processamento da malha financeira: {e}")

    st.markdown("---")
    if st.button("Encerrar Sessão"):
        st.session_state["autenticado"] = False
        st.rerun()

if "autenticado" not in st.session_state: 
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]: 
    tela_login()
else: 
    tela_principal()
