import streamlit as st
import requests
from geopy.geocoders import Nominatim
from datetime import datetime

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 1.2 - Ida e Volta, Espera Individual e Gerador de Recibos
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="centered")

CREDENCIAIS = {"sulmed": "lox2026", "tiesco": "boss"}

TARIFA_BASE = 20.00
VALOR_POR_KM = 1.50
VALOR_MINUTO_VIAGEM = 0.50
VALOR_MINUTO_ESPERA = 1.11

def calcular_rota_automatica(enderecos, total_minutos_espera):
    try:
        geolocator = Nominatim(user_agent="lox_varthoz_routing_v3")
        coordenadas_list = []
        
        for end in enderecos:
            if end.strip() == "": continue
            query = f"{end}, Rio Grande do Sul, Brasil"
            loc = geolocator.geocode(query)
            if not loc: return f"Erro: Endereço não reconhecido ({end})."
            coordenadas_list.append(f"{loc.longitude},{loc.latitude}")

        if len(coordenadas_list) < 2: return "Erro: Necessário origem e destino."

        coords_string = ";".join(coordenadas_list)
        url_osrm = f"http://router.project-osrm.org/route/v1/driving/{coords_string}?overview=false"
        
        resposta = requests.get(url_osrm).json()
        if resposta.get("code") != "Ok": return "Erro ao traçar rota."

        km = resposta['routes'][0]['distance'] / 1000
        minutos_reais = (resposta['routes'][0]['duration'] / 60) * 1.6 
        
        custo = TARIFA_BASE + (km * VALOR_POR_KM) + (minutos_reais * VALOR_MINUTO_VIAGEM) + (total_minutos_espera * VALOR_MINUTO_ESPERA)
        
        return {"km": round(km, 1), "minutos": round(minutos_reais, 0), "total": round(custo, 2)}
    except Exception as e:
        return f"Falha no sistema: {e}"

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
            st.error("Credenciais inválidas.")

def tela_principal():
    st.success(f"Operador Logado: {st.session_state['cliente'].upper()}")
    st.title("🚘 Cotação de Traslado Lox")
    st.markdown("---")
    
    tipo_rota = st.radio("Selecione a Modalidade de Rota:", ["Nova Rota (Sob Demanda)", "Rota Homologada (Recorrente)"])
    
    if tipo_rota == "Nova Rota (Sob Demanda)":
        st.info("Preencha a rota. O sistema calculará o deslocamento e os tempos de espera logísticos.")
        
        passageiro = st.text_input("Nome do Passageiro / Médico(a):", placeholder="Ex: Dr. João Beal")
        origem = st.text_input("Endereço de Embarque Completo")
        
        qtd_paradas = st.selectbox("Quantidade de Paradas Intermediárias:", [0, 1, 2, 3])
        paradas = []
        espera_total = 0
        detalhes_paradas = []
        
        for i in range(qtd_paradas):
            st.markdown(f"**Parada {i+1}**")
            col1, col2 = st.columns([3, 1])
            with col1:
                p = st.text_input(f"Endereço da Parada {i+1}", key=f"p_{i}")
            with col2:
                e = st.number_input("Espera (min)", min_value=0, step=5, key=f"e_{i}")
            if p:
                paradas.append(p)
                espera_total += e
                detalhes_paradas.append(f"Parada {i+1}: {p} (Espera: {e} min)")

        destino = st.text_input("Endereço de Desembarque Final")
        ida_e_volta = st.checkbox("🔄 Retornar à Base (Ida e Volta para a Origem)")
        
        if st.button("Calcular Rota via Satélite"):
            enderecos_completos = [origem] + paradas
            if destino: enderecos_completos.append(destino)
            if ida_e_volta and origem: enderecos_completos.append(origem)
            
            if len(enderecos_completos) >= 2:
                with st.spinner("Processando satélites e trânsito..."):
                    resultado = calcular_rota_automatica(enderecos_completos, espera_total)
                
                if isinstance(resultado, dict):
                    st.markdown("### 🧾 Ticket de Cotação Lox (Dinâmico)")
                    st.info("A tarifa dinâmica Varthoz contempla deslocamento executivo, custos operacionais e tempo estimado de rota.")
                    if espera_total > 0:
                        st.write(f"**Taxa de Espera Logística Total ({espera_total} min):** R$ {(espera_total * VALOR_MINUTO_ESPERA):.2f}")
                    st.success(f"## VALOR FINAL ESTIMADO: R$ {resultado['total']:.2f}")
                    
                    # GERADOR DE RECIBO (Padrão PDF Tiesco)
                    st.markdown("---")
                    st.markdown("### 📄 Rascunho para Recibo / NF")
                    hoje = datetime.now().strftime("%d/%m/%Y")
                    rota_texto = " -> ".join(enderecos_completos)
                    espera_texto = " | ".join(detalhes_paradas) if detalhes_paradas else "Sem espera em paradas."
                    
                    recibo_rascunho = f"""RECIBO DE PRESTAÇÃO DE SERVIÇOS E REEMBOLSO DE DESPESAS
N°: ___/2026
Data de Emissão: {hoje}

TOMADOR DO SERVIÇO:
Razão Social: SULMED ASSISTÊNCIA MÉDICA LTDA.
CNPJ: 90.747.908/0001-56

DESCRIÇÃO DETALHADA DOS SERVIÇOS:
Serviços de logística e transporte executivo de pessoal ({passageiro}), realizados em veículo particular, conforme detalhamento abaixo:

Data da Operação: {hoje}
Rota Executada: {rota_texto}
Detalhes de Espera: {espera_texto}

Valor pelos serviços prestados: R$ {resultado['total']:.2f}

Declaro que a quitação se dará mediante o crédito em conta.

DADOS PARA PAGAMENTO:
Chave PIX: [REDACTED-PIX-CPF]
Banco: 0260 - Nu Pagamentos S.A. - Instituição de Pagamento
Favorecido: Francesco de Andrade Apratto
CPF: [REDACTED-PIX-CPF]
Gestão Logística & Projetos
"""
                    st.text_area("Copie o texto abaixo para o seu PDF:", value=recibo_rascunho, height=350)
                else:
                    st.error(resultado)
            else:
                st.warning("Preencha ao menos origem e destino.")

    else:
        st.warning("Rotas Homologadas (Em manutenção para migração ao formato 1.2)")

    st.markdown("---")
    if st.button("Encerrar Sessão", type="primary"):
        st.session_state["autenticado"] = False
        st.rerun()

if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if not st.session_state["autenticado"]: tela_login()
else: tela_principal()
