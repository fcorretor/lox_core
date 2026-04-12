import streamlit as st
import requests
from geopy.geocoders import Nominatim
from datetime import datetime
import urllib.parse

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 1.6 - Retorno das Rotas Homologadas (Fixas)
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}
NUMERO_WHATSAPP_CEO = "5551998186611" # <-- MEU NÚMERO AQUI DENTRO DAS ASPAS

TARIFA_BASE = 20.00
VALOR_POR_KM = 1.80
VALOR_MINUTO_VIAGEM = 0.50
VALOR_MINUTO_ESPERA = 1.11

CIDADES_RMPA = [
    "Porto Alegre", "Alvorada", "Cachoeirinha", "Canoas", "Eldorado do Sul", 
    "Esteio", "Gravataí", "Guaíba", "Novo Hamburgo", "São Leopoldo", "Sapucaia do Sul", "Triunfo", "Viamão"
]

def calcular_rota_automatica(enderecos, total_minutos_espera):
    try:
        geolocator = Nominatim(user_agent="lox_routing_v7")
        coordenadas_list = []
        for end in enderecos:
            if end.strip() == "": continue
            query = f"{end}, Rio Grande do Sul, Brasil"
            loc = geolocator.geocode(query)
            if not loc: return f"Erro: Endereço não localizado pelo satélite ({end}). Verifique a rua."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")

        if len(coordenadas_list) < 2: return "Erro: Necessário origem e destino."

        coords_string = ";".join(coordenadas_list)
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?overview=false"
        resposta = requests.get(url_osrm).json()
        if resposta.get("code") != "Ok": return "Erro ao traçar rota veicular."

        km = resposta['routes'][0]['distance'] / 1000
        minutos_reais = (resposta['routes'][0]['duration'] / 60) * 1.6
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except Exception as e:
        return f"Falha no sistema de satélite: {e}"

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
    st.success(f"Operador Logado: {st.session_state['cliente'].upper()}")
    st.title("🚘 Cotação e Agendamento Lox")
    st.markdown("---")
    
    st.warning("⏱️ **REGRA OPERACIONAL:** Agendamentos devem ser solicitados com antecedência mínima de 1 Turno (4 horas).")
    col_data, col_hora = st.columns(2)
    with col_data:
        data_corrida = st.date_input("Data do Traslado")
    with col_hora:
        hora_corrida = st.time_input("Horário do Embarque")
    passageiro = st.text_input("Nome do Passageiro / Médico(a):", placeholder="Ex: Francesco Apratto")
    
    st.markdown("---")
    tipo_rota = st.radio("Selecione a Modalidade do Traslado:", ["Nova Rota (Sob Demanda)", "Rota Homologada (Frequente)"])
    st.markdown("---")

    # ==========================================
    # MODALIDADE 1: ROTA DINÂMICA (SATÉLITE)
    # ==========================================
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
        detalhes_paradas = []
        
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
                end_completo = f"{p_rua} - {p_cid}"
                paradas_completas.append(end_completo)
                espera_total += e_min
                detalhes_paradas.append(f"Parada {i+1}: {end_completo} (Espera: {e_min} min)")

        col_rua_dest, col_cid_dest = st.columns([3, 1])
        with col_rua_dest:
            rua_dest = st.text_input("Endereço de Desembarque Final (Rua e Nº)")
        with col_cid_dest:
            cid_dest = st.selectbox("Cidade (Destino)", CIDADES_RMPA, key="cid_dest")
        destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
        ida_e_volta = st.checkbox("🔄 Retornar à Base (O desembarque final será igual à Origem)")

        if st.button("Calcular e Gerar Pedido", type="primary"):
            enderecos_pesquisa = []
            if origem_completa: enderecos_pesquisa.append(origem_completa)
            enderecos_pesquisa.extend(paradas_completas)
            if destino_completo: enderecos_pesquisa.append(destino_completo)
            if ida_e_volta and origem_completa: enderecos_pesquisa.append(origem_completa)
            
            if len(enderecos_pesquisa) >= 2 and rua_origem and rua_dest:
                with st.spinner("Processando satélites e trânsito..."):
                    resultado = calcular_rota_automatica(enderecos_pesquisa, espera_total)
                
                if isinstance(resultado, dict):
                    st.markdown("### 🧾 Ticket de Cotação Lox")
                    if espera_total > 0:
                        st.write(f"**Taxa de Espera Total ({espera_total} min):** R$ {(espera_total * VALOR_MINUTO_ESPERA):.2f}")
                    st.success(f"## VALOR FINAL ESTIMADO: R$ {resultado['total']:.2f}")
                    
                    rota_resumo = " -> ".join(enderecos_pesquisa)
                    mensagem_wa = f"*NOVO AGENDAMENTO - PORTAL LOX*\n\n" \
                                  f"*Passageiro:* {passageiro}\n" \
                                  f"*Data:* {data_corrida.strftime('%d/%m/%Y')} às {hora_corrida.strftime('%H:%M')}\n\n" \
                                  f"*Rota:* {rota_resumo}\n" \
                                  f"*Espera Programada:* {espera_total} min\n" \
                                  f"*Valor Aprovado:* R$ {resultado['total']:.2f}\n\n" \
                                  f"Confirma o agendamento, Francesco?"
                    msg_codificada = urllib.parse.quote(mensagem_wa)
                    link_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP_CEO}?text={msg_codificada}"
                    
                    st.markdown(f"""
                    <a href="{link_whatsapp}" target="_blank">
                    <button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">
                    📲 ENVIAR AGENDAMENTO PARA O WHATSAPP LOX
                    </button>
                    </a>
                    """, unsafe_allow_html=True)
                    
                    if st.session_state['cliente'] == 'tiesco':
                        st.markdown("---")
                        st.markdown("### 🔒 Rascunho para Recibo / NF (Visão Interna)")
                        hoje = datetime.now().strftime("%d/%m/%Y")
                        espera_texto = " | ".join(detalhes_paradas) if detalhes_paradas else "Sem espera em paradas."
                        recibo_rascunho = f"""RECIBO DE PRESTAÇÃO DE SERVIÇOS E REEMBOLSO DE DESPESAS\nN°: ___/2026\nData de Emissão: {hoje}\n\nTOMADOR DO SERVIÇO:\nRazão Social: SULMED ASSISTÊNCIA MÉDICA LTDA.\nCNPJ: 90.747.908/0001-56\n\nDESCRIÇÃO DETALHADA DOS SERVIÇOS:\nServiços de logística e transporte executivo de pessoal ({passageiro}), realizados em veículo particular, conforme detalhamento abaixo:\n\nData da Operação: {data_corrida.strftime('%d/%m/%Y')} (Horário: {hora_corrida.strftime('%H:%M')})\nRota Executada: {rota_resumo}\nDetalhes de Espera: {espera_texto}\n\nValor pelos serviços prestados: R$ {resultado['total']:.2f}\n\nDeclaro que a quitação se dará mediante o crédito em conta.\n\nDADOS PARA PAGAMENTO:\nChave PIX: [REDACTED-PIX-CPF]\nBanco: 0260 - Nu Pagamentos S.A. - Instituição de Pagamento\nFavorecido: Francesco de Andrade Apratto\nCPF: [REDACTED-PIX-CPF]\nGestão Logística & Projetos"""
                        st.text_area("Copie o texto abaixo para o seu PDF:", value=recibo_rascunho, height=350)
                else:
                    st.error(resultado)
            else:
                st.warning("Preencha a Rua de Origem e a Rua de Destino para calcular.")

    # ==========================================
    # MODALIDADE 2: ROTA HOMOLOGADA (FIXA)
    # ==========================================
    else:
        st.info("Rotas com valores fixos já negociados e aprovados.")
        rota_fixa = st.selectbox("Selecione a Rota Homologada:", [
            "Porto Alegre <-> Braskem Unidade Q2 (Triunfo) [Ida e Volta]",
            "Porto Alegre <-> Distrito Industrial / Cia do Aço (Alvorada) [Ida e Volta]"
        ])
        
        espera_extra = st.number_input("Tempo de Espera Extra no Local (min) - Opcional", min_value=0, step=5)

        if st.button("Gerar Pedido de Rota Fixa", type="primary"):
            # Valores baseados nas tuas Notas Fiscais
            if "Braskem" in rota_fixa:
                valor_base = 250.00
            else:
                valor_base = 125.00
                
            custo_espera = espera_extra * VALOR_MINUTO_ESPERA
            valor_final = valor_base + custo_espera
            
            st.markdown("### 🧾 Ticket de Cotação Lox")
            st.write(f"**Valor Base da Rota:** R$ {valor_base:.2f}")
            if espera_extra > 0:
                st.write(f"**Espera Logística Extra ({espera_extra} min):** R$ {custo_espera:.2f}")
            st.success(f"## VALOR FINAL: R$ {valor_final:.2f}")
            
            mensagem_wa_fixa = f"*NOVO AGENDAMENTO - PORTAL LOX (ROTA FIXA)*\n\n" \
                               f"*Passageiro:* {passageiro}\n" \
                               f"*Data:* {data_corrida.strftime('%d/%m/%Y')} às {hora_corrida.strftime('%H:%M')}\n\n" \
                               f"*Rota:* {rota_fixa}\n" \
                               f"*Espera Adicional:* {espera_extra} min\n" \
                               f"*Valor Aprovado:* R$ {valor_final:.2f}\n\n" \
                               f"Confirma o agendamento, Francesco?"
            msg_codificada_fixa = urllib.parse.quote(mensagem_wa_fixa)
            link_whatsapp_fixo = f"https://wa.me/{NUMERO_WHATSAPP_CEO}?text={msg_codificada_fixa}"
            
            st.markdown(f"""
            <a href="{link_whatsapp_fixo}" target="_blank">
            <button style="width:100%; background-color:#25D366; color:white; padding:15px; border:none; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer;">
            📲 ENVIAR AGENDAMENTO PARA O WHATSAPP LOX
            </button>
            </a>
            """, unsafe_allow_html=True)
            
            if st.session_state['cliente'] == 'tiesco':
                st.markdown("---")
                st.markdown("### 🔒 Rascunho para Recibo / NF (Visão Interna)")
                hoje = datetime.now().strftime("%d/%m/%Y")
                texto_espera_fixa = f"Espera no local: {espera_extra} min" if espera_extra > 0 else "Sem tempo de espera excedente."
                recibo_rascunho_fixo = f"""RECIBO DE PRESTAÇÃO DE SERVIÇOS E REEMBOLSO DE DESPESAS\nN°: ___/2026\nData de Emissão: {hoje}\n\nTOMADOR DO SERVIÇO:\nRazão Social: SULMED ASSISTÊNCIA MÉDICA LTDA.\nCNPJ: 90.747.908/0001-56\n\nDESCRIÇÃO DETALHADA DOS SERVIÇOS:\nServiços de logística e transporte executivo de pessoal ({passageiro}), realizados em veículo particular, conforme detalhamento abaixo:\n\nData da Operação: {data_corrida.strftime('%d/%m/%Y')} (Horário: {hora_corrida.strftime('%H:%M')})\nRota Executada: {rota_fixa}\nDetalhes: {texto_espera_fixa}\n\nValor pelos serviços prestados: R$ {valor_final:.2f}\n\nDeclaro que a quitação se dará mediante o crédito em conta.\n\nDADOS PARA PAGAMENTO:\nChave PIX: [REDACTED-PIX-CPF]\nBanco: 0260 - Nu Pagamentos S.A. - Instituição de Pagamento\nFavorecido: Francesco de Andrade Apratto\nCPF: [REDACTED-PIX-CPF]\nGestão Logística & Projetos"""
                st.text_area("Copie o texto abaixo para o seu PDF:", value=recibo_rascunho_fixo, height=350)

    st.markdown("---")
    if st.button("Encerrar Sessão"):
        st.session_state["autenticado"] = False
        st.rerun()

if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if not st.session_state["autenticado"]: tela_login()
else: tela_principal()
