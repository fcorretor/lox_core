import os
import traceback
import urllib.parse
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from lox import VERSAO
from lox import config as cfg
from lox import documentos as doc
from lox import mailer
from lox.pricing import calcular_rota_automatica
from lox.storage import obter_store, proximo_numero_recibo

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 7.0 - Ciclo completo: cotação -> recibo -> gov.br -> e-mail -> pagamento
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="wide")

PASTA_ASSINADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recibos")
ASSINADOR_GOVBR = "https://assinador.iti.br"
VALIDADOR_GOVBR = "https://validar.iti.gov.br"

ETAPAS_RECIBO = ["Emitido", "Assinado", "Enviado", "Pago"]
ICONE_STATUS = {"Pendente": "🟡", "Faturado": "🔵", "Faturado (externo)": "⚪", "Pago": "🟢",
                "Emitido": "📝", "Assinado": "✍️", "Enviado": "📨"}

CSS = """
<style>
  [data-testid="stMetric"] { background: var(--secondary-background-color); border: 1px solid rgba(15,76,129,.12);
      border-radius: 12px; padding: 14px 16px; }
  [data-testid="stMetricLabel"] p { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; opacity: .75; }
  .lox-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 4px 0 16px; }
  .lox-kpi { background: #fff; border: 1px solid rgba(15,76,129,.12); border-radius: 12px; padding: 14px 16px;
      display: flex; flex-direction: column; gap: 2px; }
  .lox-kpi span { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; opacity: .65; font-weight: 600; }
  .lox-kpi b { font-size: 1.55rem; color: #0F4C81; white-space: nowrap; }
  .lox-kpi small { opacity: .6; }
  .lox-hero { padding: 4px 0 10px; }
  .lox-hero h1 { margin: 0; font-size: 1.9rem; }
  .lox-hero p { margin: 2px 0 0; opacity: .7; }
  .lox-preco { white-space: nowrap; font-size: 2.4rem; font-weight: 800; color: #0F4C81; line-height: 1.1; }
  .lox-chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600;
      background: rgba(15,76,129,.08); color: #0F4C81; margin-right: 6px; }
  .lox-etapas { display: flex; gap: 6px; margin: 6px 0 14px; flex-wrap: wrap; }
  .lox-etapa { flex: 1; min-width: 110px; text-align: center; padding: 8px 6px; border-radius: 10px; font-size: .85rem;
      background: rgba(120,130,145,.10); color: rgba(20,32,46,.55); font-weight: 600; }
  .lox-etapa.ok { background: #E3F2EA; color: #1E7D4F; }
  .lox-etapa.atual { background: #0F4C81; color: #fff; }
  section[data-testid="stSidebar"] .lox-marca { font-size: 1.35rem; font-weight: 800; letter-spacing: .02em; }
</style>
"""


# ==========================================
# UTILITÁRIOS
# ==========================================

def cabecalho(titulo, subtitulo=""):
    st.markdown(f'<div class="lox-hero"><h1>{titulo}</h1><p>{subtitulo}</p></div>', unsafe_allow_html=True)


def kpis(itens):
    html = "".join(f'<div class="lox-kpi"><span>{r}</span><b>{v}</b><small>{s}</small></div>' for r, v, s in itens)
    st.markdown(f'<div class="lox-kpis">{html}</div>', unsafe_allow_html=True)


def para_data(serie):
    return pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce")


def store():
    return obter_store()


def notificar_operador(mensagem):
    """
    ESQUELETO: ponto único de notificação automática.
    Hoje desativado (FEATURE_FLAGS["notificacao_whatsapp_ativa"] = False).
    Quando ativar: plugar aqui uma API de WhatsApp (WhatsApp Business Cloud API,
    Twilio ou Z-API) usando NUMERO_WHATSAPP_CEO como destino.
    """
    if not cfg.FEATURE_FLAGS["notificacao_whatsapp_ativa"]:
        return False
    return False


def link_whatsapp(op):
    texto = (f"*Lox | Ordem de Serviço {op['ID']}*\n"
             f"{op.get('Tipo', 'Traslado')} em {op['Data_Traslado']} às {op['Hora_Embarque']}\n"
             f"Passageiro/Escopo: {op['Passageiro']}\n"
             f"Solicitante: {op['Solicitante']} ({op['Centro_Custo']})\n"
             f"{op['Detalhe']}\n"
             f"Valor: {doc.moeda(op['Valor_Total'])}")
    return f"https://wa.me/{cfg.NUMERO_WHATSAPP_CEO}?text={urllib.parse.quote(texto)}"


def checar_antecedencia(data_corrida, hora):
    """SLA de acionamento: 1 turno (4h). Devolve as horas de antecedência."""
    alvo = datetime.combine(data_corrida, hora)
    return (alvo - cfg.agora()).total_seconds() / 3600


def mapa_rota(resultado):
    try:
        import pydeck as pdk
        pontos = resultado["pontos"]
        df_pts = pd.DataFrame([{"lat": la, "lon": lo, "ordem": i + 1} for i, (la, lo) in enumerate(pontos)])
        camadas = [
            pdk.Layer("PathLayer", data=[{"path": resultado["trajeto"]}], get_path="path",
                      get_color=[15, 76, 129], width_min_pixels=4),
            pdk.Layer("ScatterplotLayer", data=df_pts, get_position="[lon, lat]", get_radius=180,
                      get_fill_color=[230, 80, 60], radius_min_pixels=6, pickable=True),
        ]
        lat_c = sum(p[0] for p in pontos) / len(pontos)
        lon_c = sum(p[1] for p in pontos) / len(pontos)
        st.pydeck_chart(pdk.Deck(layers=camadas, map_provider="carto", map_style="light",
                                 initial_view_state=pdk.ViewState(latitude=lat_c, longitude=lon_c, zoom=10),
                                 tooltip={"text": "Ponto {ordem}"}), height=320)
    except Exception:
        st.map(pd.DataFrame([{"lat": la, "lon": lo} for la, lo in resultado["pontos"]]))


# ==========================================
# FATURAMENTO (núcleo do ciclo do recibo)
# ==========================================

def emitir_recibo(ids, emissao):
    s = store()
    ops = s.listar_ops()
    sel = ops[ops["ID"].isin(ids) & (ops["Status"] == "Pendente")].copy()
    if sel.empty:
        st.error("Nenhuma operação pendente selecionada.")
        return None
    sel["_d"] = para_data(sel["Data_Traslado"])
    sel = sel.sort_values("_d")
    numero = proximo_numero_recibo(s, emissao.year)
    total = round(float(sel["Valor_Total"].sum()), 2)
    s.adicionar_recibo({"Numero": numero, "Emissao": emissao.strftime("%d/%m/%Y"),
                        "Operacoes": ",".join(sel["ID"]), "Total": total, "Status": "Emitido"})
    s.atualizar_ops(list(sel["ID"]), {"Status": "Faturado", "Recibo": numero})
    return numero


def pdf_do_recibo(rec):
    ops = store().listar_ops()
    ids = rec["Operacoes"].split(",")
    sel = ops[ops["ID"].isin(ids)].copy()
    sel["_d"] = para_data(sel["Data_Traslado"])
    registros = sel.sort_values("_d").drop(columns="_d").to_dict("records")
    emissao = datetime.strptime(rec["Emissao"], "%d/%m/%Y")
    return doc.gerar_recibo_pdf(rec["Numero"], emissao, registros, cfg.prestador(), cfg.tomador())


def nome_arquivo(numero, assinado=False):
    return f"Francesco_NF_-_{numero}_sulmedAssistenciaMedicaLtda{'_assinado' if assinado else ''}.pdf"


def caminho_assinado(numero):
    return os.path.join(PASTA_ASSINADOS, nome_arquivo(numero, True))


def ler_assinado(numero):
    if numero in st.session_state.get("assinados", {}):
        return st.session_state["assinados"][numero]
    p = caminho_assinado(numero)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return None


def guardar_assinado(numero, dados):
    st.session_state.setdefault("assinados", {})[numero] = dados
    try:
        os.makedirs(PASTA_ASSINADOS, exist_ok=True)
        with open(caminho_assinado(numero), "wb") as f:
            f.write(dados)
    except OSError:
        pass  # Streamlit Cloud: o arquivo fica na sessão até o envio


def botao_emitir_agora(op):
    """Atalho pós-agendamento: recibo individual na hora, como na v6.1."""
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🧾 Emitir recibo agora", type="primary", width="stretch", key=f"emitir_{op['ID']}"):
            numero = emitir_recibo([op["ID"]], cfg.agora().date())
            if numero:
                st.session_state["recibo_aberto"] = numero
                st.session_state["_ir_para"] = "🧾 Faturamento"
                st.session_state["_fat_aba"] = "Recibos"
                st.session_state.pop("ultima_op", None)
                st.rerun()
    with c2:
        st.link_button("📲 Despachar no WhatsApp", link_whatsapp(op), width="stretch")
    with c3:
        if st.button("➕ Novo agendamento", width="stretch", key=f"novo_{op['ID']}"):
            st.session_state.pop("ultima_op", None)
            st.session_state.pop("cotacao", None)
            st.rerun()


def registrar(op):
    store().adicionar_op(op)
    notificar_operador(f"Novo {op['Tipo'].lower()}: {op['Passageiro']} em {op['Data_Traslado']} - {doc.moeda(op['Valor_Total'])}")
    st.session_state["ultima_op"] = op
    st.session_state.pop("cotacao", None)


def card_ultima_op(chave_tipo):
    op = st.session_state.get("ultima_op")
    if not op or op.get("Tipo") != chave_tipo:
        return False
    with st.container(border=True):
        st.success(f"Operação **{op['ID']}** registrada como *Pendente* de faturamento.")
        st.markdown(f'<div class="lox-preco">{doc.moeda(op["Valor_Total"])}</div>', unsafe_allow_html=True)
        st.caption(f"{op['Data_Traslado']} · {op['Hora_Embarque']} · {op['Passageiro']}")
        if st.session_state.get("cliente") == "sulmed":
            st.info("Agendamento recebido. A SylvaCore confirma o embarque e envia o recibo assinado.")
        else:
            botao_emitir_agora(op)
    return True


# ==========================================
# LOGIN
# ==========================================

def tela_login():
    _, meio, _ = st.columns([1, 1.2, 1])
    with meio:
        st.markdown("<br>", unsafe_allow_html=True)
        cabecalho("🔒 Lox", "Portal Corporativo de Logística Executiva · SylvaCore")
        with st.form("form_login"):
            usuario = st.text_input("Usuário").strip().lower()
            senha = st.text_input("Senha", type="password").strip()
            if st.form_submit_button("Acessar painel", type="primary", width="stretch"):
                cred = cfg.credenciais()
                if usuario in cred and str(cred[usuario]) == senha:
                    st.session_state["autenticado"] = True
                    st.session_state["cliente"] = usuario
                    st.rerun()
                else:
                    st.error("Credenciais inválidas. Acesso negado.")
        st.caption("Autenticação exigida para emissão e auditoria.")


# ==========================================
# MÓDULO: PAINEL
# ==========================================

def modulo_painel():
    cabecalho("📊 Painel", "Visão financeira e operacional do contrato Sulmed")
    s = store()
    ops, recs = s.listar_ops(), s.listar_recibos()
    hoje = cfg.agora().date()
    ops["_d"] = para_data(ops["Data_Traslado"])
    recs["_pago"] = para_data(recs["Pago_Em"])

    pend = ops[ops["Status"] == "Pendente"]
    abertos = recs[recs["Status"].isin(["Emitido", "Assinado", "Enviado"])]
    mes = ops[(ops["_d"].dt.month == hoje.month) & (ops["_d"].dt.year == hoje.year)]
    recebido_mes = recs[(recs["_pago"].dt.month == hoje.month) & (recs["_pago"].dt.year == hoje.year)]

    kpis([("A faturar", doc.moeda(pend["Valor_Total"].sum()), f"{len(pend)} operações pendentes"),
          ("A receber", doc.moeda(abertos["Total"].sum()), f"{len(abertos)} recibos em aberto"),
          ("Recebido no mês", doc.moeda(recebido_mes["Total"].sum()), f"{len(recebido_mes)} recibos quitados"),
          ("Operações no mês", str(len(mes)), doc.moeda(mes["Valor_Total"].sum()))])

    if ops.empty:
        st.info("Nenhuma operação registrada ainda. Comece em **🚘 Traslados**.")
        return

    g1, g2 = st.columns([3, 2])
    with g1:
        with st.container(border=True):
            st.markdown("**Faturamento por mês**")
            por_mes = ops.dropna(subset=["_d"]).groupby(ops["_d"].dt.to_period("M"))["Valor_Total"].sum().tail(12)
            por_mes.index = por_mes.index.strftime("%m/%Y")
            st.bar_chart(por_mes, color="#0F4C81", height=260)
    with g2:
        with st.container(border=True):
            st.markdown("**Por centro de custo**")
            por_cc = ops.groupby("Centro_Custo")["Valor_Total"].sum().sort_values(ascending=False)
            st.bar_chart(por_cc, color="#3B82C4", horizontal=True, height=260)

    with st.container(border=True):
        st.markdown("**Recibos em aberto** — acompanhe para não deixar nota sem pagamento")
        if abertos.empty:
            st.caption("Tudo quitado. 🎉")
        else:
            t = abertos[["Numero", "Emissao", "Total", "Status", "Enviado_Em"]].copy()
            t["Dias desde a emissão"] = (pd.Timestamp(hoje) - para_data(t["Emissao"])).dt.days
            t["Total"] = t["Total"].map(doc.moeda)
            st.dataframe(t, hide_index=True, width="stretch")


# ==========================================
# MÓDULO: TRASLADOS (PASSAGEIROS)
# ==========================================

def modulo_passageiros():
    cabecalho("🚘 Cotação e Agendamento", "Tarifa corporativa plana · zero tarifa dinâmica")
    if card_ultima_op("Traslado"):
        return

    st.warning(f"⏱️ **REGRA OPERACIONAL:** agendamentos devem ser solicitados com antecedência mínima "
               f"de 1 turno ({cfg.ANTECEDENCIA_MIN_HORAS} horas).")

    with st.container(border=True):
        col_data, col_hora_ida, col_hora_volta = st.columns(3)
        with col_data:
            data_corrida = st.date_input("Data do Traslado", date.today(), format="DD/MM/YYYY")
        with col_hora_ida:
            hora_corrida = st.time_input("Horário de Ida", step=60)
        with col_hora_volta:
            tem_volta = st.checkbox("Incluir hora da volta?")
            hora_retorno = st.time_input("Horário da Volta", step=60) if tem_volta else None
        hora_db_str = (f"{hora_corrida:%H:%M} (Ida) | {hora_retorno:%H:%M} (Volta)"
                       if hora_retorno else hora_corrida.strftime("%H:%M"))

        col_pass, col_sol, col_cc = st.columns(3)
        with col_pass:
            passageiro = st.text_input("Passageiro / Médico(a)", placeholder="Ex: Dr. XPTO")
        with col_sol:
            solicitante = st.text_input("Seu nome e contato", placeholder="Ex: Fulano - (51) 9999-9999")
        with col_cc:
            centro_custo = st.selectbox("Centro de Custo", cfg.CENTROS_DE_CUSTO)

    antecedencia = checar_antecedencia(data_corrida, hora_corrida)
    if antecedencia < 0:
        st.caption("🕘 Horário já passou — será um registro retroativo.")
    elif antecedencia < cfg.ANTECEDENCIA_MIN_HORAS:
        st.warning(f"Faltam só {antecedencia:.1f} h para o embarque — abaixo do SLA de {cfg.ANTECEDENCIA_MIN_HORAS} h.")

    base = {
        "Data_Agendamento": cfg.agora().strftime("%d/%m/%Y %H:%M"),
        "Data_Traslado": data_corrida.strftime("%d/%m/%Y"), "Hora_Embarque": hora_db_str,
        "Passageiro": passageiro, "Solicitante": solicitante, "Centro_Custo": centro_custo,
        "Status": "Pendente", "Tipo": "Traslado", "Recibo": "",
    }

    tipo_rota = st.radio("Modalidade do traslado", ["Rota Homologada (Frequente)", "Nova Rota (Sob Demanda)"],
                         horizontal=True)

    if tipo_rota == "Nova Rota (Sob Demanda)":
        with st.container(border=True):
            col_rua_origem, col_cid_origem = st.columns([3, 1])
            with col_rua_origem:
                rua_origem = st.text_input("Endereço de Embarque (Rua e Nº)")
            with col_cid_origem:
                cid_origem = st.selectbox("Cidade (Origem)", cfg.CIDADES_RMPA, key="cid_origem")
            origem_completa = f"{rua_origem} - {cid_origem}" if rua_origem else ""

            qtd_paradas = st.selectbox("Paradas intermediárias", [0, 1, 2, 3])
            paradas, espera_total = [], 0
            for i in range(qtd_paradas):
                col_r, col_c, col_e = st.columns([5, 3, 2])
                with col_r:
                    p_rua = st.text_input("Rua e Nº", key=f"p_rua_{i}")
                with col_c:
                    p_cid = st.selectbox("Cidade", cfg.CIDADES_RMPA, key=f"p_cid_{i}")
                with col_e:
                    e_min = st.number_input("Espera (min)", min_value=0, step=5, key=f"e_{i}")
                if p_rua:
                    paradas.append(f"{p_rua} - {p_cid}")
                    espera_total += e_min

            col_rua_dest, col_cid_dest = st.columns([3, 1])
            with col_rua_dest:
                rua_dest = st.text_input("Endereço de Desembarque Final")
            with col_cid_dest:
                cid_dest = st.selectbox("Cidade (Destino)", cfg.CIDADES_RMPA, key="cid_dest")
            destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
            ida_e_volta = st.checkbox("🔄 Retornar à base")

        enderecos = [e for e in [origem_completa, *paradas, destino_completo] if e]
        if ida_e_volta and origem_completa:
            enderecos.append(origem_completa)
        enderecos = [e for i, e in enumerate(enderecos) if i == 0 or e != enderecos[i - 1]]
        assinatura = (tuple(enderecos), espera_total)

        if st.button("Calcular cotação", type="primary"):
            if len(enderecos) >= 2 and rua_origem and rua_dest:
                with st.spinner("Processando geolocalização e matriz financeira..."):
                    resultado = calcular_rota_automatica(enderecos, espera_total)
                if isinstance(resultado, dict):
                    st.session_state["cotacao"] = {"assinatura": assinatura, "resultado": resultado}
                else:
                    st.error(resultado)
            else:
                st.warning("Preencha origem e destino para o cálculo da rota.")

        cot = st.session_state.get("cotacao")
        if cot and cot["assinatura"] == assinatura:
            r = cot["resultado"]
            with st.container(border=True):
                c1, c2 = st.columns([2, 3])
                with c1:
                    st.markdown("VALOR FINAL")
                    st.markdown(f'<div class="lox-preco">{doc.moeda(r["total"])}</div>', unsafe_allow_html=True)
                    st.markdown(f'<span class="lox-chip">{r["km"]} km</span><span class="lox-chip">~{r["minutos"]:.0f} min</span>'
                                f'<span class="lox-chip">espera {espera_total} min</span>', unsafe_allow_html=True)
                    comp = r["composicao"]
                    st.markdown(f"""
| Composição | Valor |
|---|---:|
| Tarifa base | {doc.moeda(comp['base'])} |
| Distância ({r['km']} km × {doc.moeda(cfg.VALOR_POR_KM)}) | {doc.moeda(comp['km'])} |
| Tempo (~{r['minutos']:.0f} min × {doc.moeda(cfg.VALOR_MINUTO_VIAGEM)}) | {doc.moeda(comp['tempo'])} |
| Espera ({espera_total} min × {doc.moeda(cfg.VALOR_MINUTO_ESPERA)}) | {doc.moeda(comp['espera'])} |
""")
                with c2:
                    mapa_rota(r)
                if st.button("✅ Confirmar e agendar", type="primary", width="stretch"):
                    if not passageiro or not solicitante:
                        st.warning("Informe o passageiro e o solicitante para a rastreabilidade.")
                    else:
                        registrar({**base, "ID": cfg.agora().strftime("%Y%m%d%H%M%S"),
                                   "Origem": origem_completa,
                                   "Destino": f"{enderecos[-1]} (I/V)" if ida_e_volta else enderecos[-1],
                                   "KM_Total": r["km"], "Valor_Total": r["total"], "Espera_Min": espera_total,
                                   "Detalhe": doc.detalhe_rota(origem_completa, enderecos[-1], hora_db_str, enderecos)})
                        st.rerun()
        elif cot:
            st.caption("Os endereços mudaram — calcule a cotação novamente.")

    else:
        st.info("Rotas com valores fixos já negociados e aprovados.")
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                rota_fixa = st.selectbox("Rota homologada", list(cfg.ROTAS_HOMOLOGADAS))
            with c2:
                espera_extra = st.number_input("Espera extra (min)", min_value=0, step=5)
            valor_base = cfg.ROTAS_HOMOLOGADAS[rota_fixa]["valor"]
            valor_final = valor_base + espera_extra * cfg.VALOR_MINUTO_ESPERA
            st.markdown(f'<div class="lox-preco">{doc.moeda(valor_final)}</div>', unsafe_allow_html=True)
            st.caption(f"Valor fixo {doc.moeda(valor_base)}"
                       + (f" + espera {espera_extra} min × {doc.moeda(cfg.VALOR_MINUTO_ESPERA)}" if espera_extra else ""))

        if st.button("Gerar pedido de rota fixa", type="primary"):
            if not passageiro or not solicitante:
                st.warning("Informe o passageiro e o solicitante para a rastreabilidade.")
            else:
                registrar({**base, "ID": cfg.agora().strftime("%Y%m%d%H%M%S"), "Origem": rota_fixa,
                           "Destino": "Rota Fixa Homologada", "KM_Total": 0, "Valor_Total": valor_final,
                           "Espera_Min": espera_extra,
                           "Detalhe": doc.detalhe_rota(rota_fixa, "Rota Fixa Homologada", hora_db_str)})
                st.rerun()


# ==========================================
# MÓDULO: CARGAS / ENTREGAS (B2B)
# ==========================================

def modulo_entregas():
    cabecalho("📦 Cargas / Entregas", "Faturamento B2B Sulmed · mesmo motor de rotas do traslado")
    if card_ultima_op("Carga"):
        return

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            id_os = st.text_input("ID da Ordem de Serviço", f"OS-{cfg.agora():%Y%m%d%H%M}-SUL")
        with c2:
            data_servico = st.date_input("Data do serviço", date.today(), format="DD/MM/YYYY")
        with c3:
            centro_custo = st.selectbox("Centro de Custo", cfg.CENTROS_DE_CUSTO, key="carga_cc")
        solicitante = st.text_input("Solicitante", key="carga_solicitante")
        descricao = st.text_area("Escopo do serviço (o que está sendo transportado)", placeholder="Ex: 69 volumes / fraldas")

    st.markdown("**Rota da carga** — cálculo automático do SLA base")
    with st.container(border=True):
        col_rua_o, col_cid_o = st.columns([3, 1])
        with col_rua_o:
            rua_coleta = st.text_input("Endereço de Coleta (Rua e Nº)", key="carga_rua_coleta")
        with col_cid_o:
            cid_coleta = st.selectbox("Cidade (Coleta)", cfg.CIDADES_RMPA, key="carga_cid_coleta")

        qtd = st.selectbox("Pontos de entrega intermediários", [0, 1, 2, 3], key="carga_qtd_paradas")
        paradas, espera_total = [], 0
        for i in range(qtd):
            col_r, col_c, col_e = st.columns([5, 3, 2])
            with col_r:
                p_rua = st.text_input("Rua e Nº", key=f"carga_p_rua_{i}")
            with col_c:
                p_cid = st.selectbox("Cidade", cfg.CIDADES_RMPA, key=f"carga_p_cid_{i}")
            with col_e:
                e_min = st.number_input("Espera (min)", min_value=0, step=5, key=f"carga_e_{i}")
            if p_rua:
                paradas.append(f"{p_rua} - {p_cid}")
                espera_total += e_min

        col_rua_d, col_cid_d = st.columns([3, 1])
        with col_rua_d:
            rua_entrega = st.text_input("Endereço de Entrega Final", key="carga_rua_entrega")
        with col_cid_d:
            cid_entrega = st.selectbox("Cidade (Entrega)", cfg.CIDADES_RMPA, key="carga_cid_entrega")

        if st.button("Calcular rota e SLA base", key="carga_calcular"):
            origem = f"{rua_coleta} - {cid_coleta}" if rua_coleta else ""
            destino = f"{rua_entrega} - {cid_entrega}" if rua_entrega else ""
            enderecos = [e for e in [origem, *paradas, destino] if e]
            if len(enderecos) >= 2 and rua_coleta and rua_entrega:
                with st.spinner("Calculando rota da carga..."):
                    resultado = calcular_rota_automatica(enderecos, espera_total)
                if isinstance(resultado, dict):
                    st.session_state["carga_valor_calculado"] = resultado["total"]
                    st.session_state["carga_km"] = resultado["km"]
                    st.session_state["carga_rota"] = resultado
                    partes = [f"Coleta ({origem})"] + [f"Entrega ({p})" for p in paradas] + [f"Entrega Final ({destino})"]
                    st.session_state["carga_roteiro_calculado"] = " -> ".join(partes)
                    st.session_state["carga_v_base"] = float(resultado["total"])
                else:
                    st.error(resultado)
            else:
                st.warning("Preencha ao menos a coleta e a entrega final para calcular a rota.")

        if st.session_state.get("carga_rota"):
            r = st.session_state["carga_rota"]
            st.success(f"SLA base calculado: {doc.moeda(r['total'])} ({r['km']} km)")
            mapa_rota(r)

    col1, col2 = st.columns(2)
    with col1:
        v_base = st.number_input("Valor base / SLA (R$)", min_value=0.0, step=5.0, key="carga_v_base",
                                 help="Preenchido ao calcular a rota — pode ajustar na mão.")
    with col2:
        v_taxa = st.number_input("Taxas de anomalia / re-roteamento (R$)", min_value=0.0, value=0.0, step=5.0)
    total = v_base + v_taxa
    st.markdown(f'<div class="lox-preco">{doc.moeda(total)}</div>', unsafe_allow_html=True)

    if st.button("Registrar carga", type="primary", key="carga_registrar"):
        if v_base <= 0:
            st.warning("Calcule a rota ou insira o valor base do serviço.")
        elif not descricao.strip():
            st.warning("Descreva o escopo da carga.")
        else:
            roteiro = st.session_state.get("carga_roteiro_calculado") or "Roteiro informado manualmente"
            detalhe = f"Roteiro Auditado: {roteiro}\nSLA Base: {doc.moeda(v_base)}"
            if v_taxa:
                detalhe += f"\nTaxa de Anomalia/Retorno: {doc.moeda(v_taxa)}"
            registrar({"ID": id_os, "Data_Agendamento": cfg.agora().strftime("%d/%m/%Y %H:%M"),
                       "Data_Traslado": data_servico.strftime("%d/%m/%Y"), "Hora_Embarque": "",
                       "Passageiro": descricao.strip(), "Solicitante": solicitante, "Centro_Custo": centro_custo,
                       "Origem": f"{rua_coleta} - {cid_coleta}", "Destino": f"{rua_entrega} - {cid_entrega}",
                       "KM_Total": st.session_state.get("carga_km", 0), "Valor_Total": round(total, 2),
                       "Espera_Min": espera_total, "Status": "Pendente", "Tipo": "Carga", "Detalhe": detalhe,
                       "Recibo": ""})
            for k in ("carga_rota", "carga_roteiro_calculado", "carga_valor_calculado", "carga_km"):
                st.session_state.pop(k, None)
            st.rerun()


# ==========================================
# MÓDULO: FATURAMENTO (recibo -> gov.br -> e-mail -> pagamento)
# ==========================================

def trilha(status):
    atual = ETAPAS_RECIBO.index(status) if status in ETAPAS_RECIBO else 0
    html = "".join(
        f'<div class="lox-etapa {"ok" if i < atual or status == "Pago" else "atual" if i == atual else ""}">'
        f'{"✓ " if i < atual or status == "Pago" else ""}{e}</div>'
        for i, e in enumerate(ETAPAS_RECIBO))
    st.markdown(f'<div class="lox-etapas">{html}</div>', unsafe_allow_html=True)


def painel_recibo(rec):
    s = store()
    numero, status = rec["Numero"], rec["Status"]
    c1, c2 = st.columns([3, 1])
    with c1:
        st.subheader(f"Recibo Nº {numero}")
        st.caption(f"Emitido em {rec['Emissao']} · {len(rec['Operacoes'].split(','))} operação(ões)"
                   + (f" · enviado {rec['Enviado_Em']} para {rec['Enviado_Para']}" if rec["Enviado_Em"] else "")
                   + (f" · pago em {rec['Pago_Em']}" if rec["Pago_Em"] else ""))
    with c2:
        st.markdown(f'<div class="lox-preco" style="text-align:right">{doc.moeda(rec["Total"])}</div>',
                    unsafe_allow_html=True)
    trilha(status)

    pdf = pdf_do_recibo(rec)
    assinado = ler_assinado(numero)

    e1, e2 = st.columns(2)
    with e1:
        with st.container(border=True):
            st.markdown("**1 · Baixar o recibo**")
            st.download_button("⬇️ Baixar PDF para assinar", pdf, nome_arquivo(numero), "application/pdf",
                               width="stretch", key=f"dl_{numero}")
            st.caption("PDF em Helvetica nativa, aceito pelo assinador gov.br.")
    with e2:
        with st.container(border=True):
            st.markdown("**2 · Assinar no gov.br**")
            st.link_button("🔏 Abrir assinador gov.br", ASSINADOR_GOVBR, width="stretch")
            arq = st.file_uploader("Anexe o PDF assinado", type="pdf", key=f"up_{numero}", label_visibility="collapsed")
            if arq is not None and st.session_state.get(f"_up_ok_{numero}") != arq.file_id:
                dados = arq.getvalue()
                if b"/ByteRange" not in dados:
                    st.warning("Este PDF não parece ter assinatura digital. Confira se baixou o arquivo assinado.")
                guardar_assinado(numero, dados)
                st.session_state[f"_up_ok_{numero}"] = arq.file_id
                if status == "Emitido":
                    s.atualizar_recibo(numero, {"Status": "Assinado", "Assinado_Em": cfg.agora().strftime("%d/%m/%Y %H:%M")})
                st.rerun()
            if assinado:
                st.caption(f"✍️ PDF assinado anexado ({len(assinado) // 1024} KB). "
                           f"[Validar assinatura]({VALIDADOR_GOVBR})")

    with st.container(border=True):
        st.markdown("**3 · Enviar por e-mail**")
        em, prest = cfg.email(), cfg.prestador()
        if not assinado:
            st.caption("Disponível depois de anexar o PDF assinado (passo 2)."
                       + (" Se o recibo já foi assinado em outra sessão, anexe-o de novo." if status != "Emitido" else ""))
        else:
            with st.form(f"email_{numero}"):
                c1, c2 = st.columns(2)
                para = c1.text_input("Para", em["destino"])
                cc = c2.text_input("Cópia (CC)", em["cc"])
                assunto = st.text_input("Assunto", f"Recibo Nº {numero} - {prest['nome']} - {doc.moeda(rec['Total'])}")
                corpo = st.text_area("Mensagem", height=150, value=(
                    f"Prezados,\n\nSegue em anexo o recibo Nº {numero}, devidamente assinado via gov.br, "
                    f"referente aos serviços de logística prestados, no valor de {doc.moeda(rec['Total'])}.\n\n"
                    f"Dados para pagamento: PIX {prest['pix']}.\n\nAtenciosamente,\n{prest['nome']}\n{prest['assinatura']}"))
                if st.form_submit_button("📨 " + ("Reenviar" if status in ("Enviado", "Pago") else "Enviar recibo assinado"),
                                         type="primary"):
                    try:
                        with st.spinner("Enviando..."):
                            destinos = mailer.enviar(em, para, cc, assunto, corpo, assinado, nome_arquivo(numero, True))
                        campos = {"Enviado_Em": cfg.agora().strftime("%d/%m/%Y %H:%M"), "Enviado_Para": ", ".join(destinos)}
                        if status != "Pago":
                            campos["Status"] = "Enviado"
                        s.atualizar_recibo(numero, campos)
                        st.toast(f"Recibo enviado para {', '.join(destinos)}", icon="📨")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao enviar: {e}")

    with st.container(border=True):
        st.markdown("**4 · Confirmar pagamento**")
        if status == "Pago":
            st.success(f"Pago em {rec['Pago_Em']}.")
        else:
            c1, c2 = st.columns([2, 1])
            data_pg = c1.date_input("Data do crédito", cfg.agora().date(), format="DD/MM/YYYY", key=f"pg_{numero}")
            c2.markdown("<br>", unsafe_allow_html=True)
            if c2.button("🟢 Marcar como pago", key=f"pago_{numero}", width="stretch"):
                s.atualizar_recibo(numero, {"Status": "Pago", "Pago_Em": data_pg.strftime("%d/%m/%Y")})
                s.atualizar_ops(rec["Operacoes"].split(","), {"Status": "Pago"})
                st.rerun()

    ops = s.listar_ops()
    with st.expander("Operações incluídas"):
        incl = ops[ops["ID"].isin(rec["Operacoes"].split(","))]
        st.dataframe(incl[["ID", "Tipo", "Data_Traslado", "Passageiro", "Centro_Custo", "Valor_Total"]],
                     hide_index=True, width="stretch")
    if status != "Pago":
        with st.expander("Cancelar recibo"):
            st.caption("As operações voltam para 'Pendente'. Use se o recibo foi emitido errado.")
            if st.button("Cancelar este recibo", key=f"cancel_{numero}"):
                s.atualizar_ops(rec["Operacoes"].split(","), {"Status": "Pendente", "Recibo": ""})
                s.excluir_recibo(numero)
                st.session_state.pop("recibo_aberto", None)
                st.rerun()


def modulo_faturamento():
    cabecalho("🧾 Faturamento", "Recibo → assinatura gov.br → e-mail → pagamento")
    s = store()
    if "_fat_aba" in st.session_state:
        st.session_state["fat_aba"] = st.session_state.pop("_fat_aba")
    aba = st.radio("Visão", ["A faturar", "Recibos"], horizontal=True, key="fat_aba", label_visibility="collapsed")

    if aba == "A faturar":
        ops = s.listar_ops()
        pend = ops[ops["Status"] == "Pendente"].copy()
        if pend.empty:
            st.info("Nenhuma operação pendente de faturamento.")
        else:
            pend["_d"] = para_data(pend["Data_Traslado"])
            pend = pend.sort_values("_d")
            pend.insert(0, "Incluir", True)
            editado = st.data_editor(
                pend[["Incluir", "ID", "Tipo", "Data_Traslado", "Passageiro", "Solicitante", "Centro_Custo", "Valor_Total"]],
                hide_index=True, width="stretch", disabled=["ID", "Tipo", "Data_Traslado", "Passageiro",
                                                                     "Solicitante", "Centro_Custo", "Valor_Total"],
                column_config={"Valor_Total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                               "Data_Traslado": "Data", "Centro_Custo": "Centro de custo"},
                key="editor_pendentes")
            sel = editado[editado["Incluir"]]
            c1, c2, c3 = st.columns([2, 1.3, 1.3])
            c1.metric("Selecionado", doc.moeda(sel["Valor_Total"].sum()), f"{len(sel)} operações", delta_color="off")
            emissao = c2.date_input("Data de emissão", cfg.agora().date(), format="DD/MM/YYYY")
            c3.markdown("<br>", unsafe_allow_html=True)
            if c3.button("🧾 Emitir recibo", type="primary", width="stretch", disabled=sel.empty):
                numero = emitir_recibo(list(sel["ID"]), emissao)
                if numero:
                    st.session_state["recibo_aberto"] = numero
                    st.session_state["_fat_aba"] = "Recibos"
                    st.toast(f"Recibo {numero} emitido", icon="🧾")
                    st.rerun()
            st.caption(f"Próximo número: **{proximo_numero_recibo(s, emissao.year)}** · "
                       "um recibo por operação ou vários traslados num recibo consolidado.")
            with st.expander("Operações antigas já cobradas fora do Lox?"):
                st.caption("Marque-as acima e tire-as da fila sem gerar recibo novo.")
                if st.button("Marcar selecionadas como já faturadas", disabled=sel.empty):
                    s.atualizar_ops(list(sel["ID"]), {"Status": "Faturado (externo)"})
                    st.rerun()

    else:
        recs = s.listar_recibos()
        if recs.empty:
            st.info("Nenhum recibo emitido ainda.")
            return
        recs["_n"] = recs["Numero"].map(lambda n: (n.split("-")[-1], n))
        recs = recs.sort_values("_n", ascending=False)
        filtro = st.radio("Mostrar", ["Em aberto", "Todos"], horizontal=True, label_visibility="collapsed")
        lista = recs[recs["Status"] != "Pago"] if filtro == "Em aberto" else recs
        if lista.empty:
            st.success("Nenhum recibo em aberto. 🎉")
            lista = recs
        rotulos = {r["Numero"]: f"{ICONE_STATUS.get(r['Status'], '')} {r['Numero']} · {doc.moeda(r['Total'])} · {r['Status']}"
                   for _, r in lista.iterrows()}
        opcoes = list(rotulos)
        aberto = st.session_state.get("recibo_aberto")
        idx = opcoes.index(aberto) if aberto in opcoes else 0
        escolhido = st.selectbox("Recibo", opcoes, index=idx, format_func=rotulos.get)
        st.session_state["recibo_aberto"] = escolhido
        with st.container(border=True):
            painel_recibo(recs[recs["Numero"] == escolhido].iloc[0])


# ==========================================
# MÓDULO: HISTÓRICO
# ==========================================

def modulo_historico():
    cabecalho("📚 Histórico", "Rastreabilidade completa para auditoria")
    ops = store().listar_ops()
    if ops.empty:
        st.info("Nada registrado ainda.")
        return
    ops["_d"] = para_data(ops["Data_Traslado"])
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
        hoje = cfg.agora().date()
        periodo = c1.date_input("Período", (hoje.replace(day=1) - timedelta(days=90), hoje), format="DD/MM/YYYY")
        tipo = c2.multiselect("Tipo", sorted(ops["Tipo"].unique()))
        status = c3.multiselect("Situação", sorted(ops["Status"].unique()))
        busca = c4.text_input("Buscar", placeholder="passageiro, solicitante, endereço, recibo...")

    f = ops
    if isinstance(periodo, tuple) and len(periodo) == 2:
        f = f[(f["_d"] >= pd.Timestamp(periodo[0])) & (f["_d"] <= pd.Timestamp(periodo[1]))]
    if tipo:
        f = f[f["Tipo"].isin(tipo)]
    if status:
        f = f[f["Status"].isin(status)]
    if busca:
        alvo = f.drop(columns="_d").astype(str).agg(" ".join, axis=1).str.lower()
        f = f[alvo.str.contains(busca.lower(), regex=False)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Operações", len(f))
    m2.metric("Total", doc.moeda(f["Valor_Total"].sum()))
    m3.metric("Km rodados", f"{f['KM_Total'].sum():,.0f}".replace(",", "."))

    vis = f.sort_values("_d", ascending=False).drop(columns="_d")
    vis.insert(0, "", vis["Status"].map(ICONE_STATUS).fillna(""))
    st.dataframe(vis, hide_index=True, width="stretch",
                 column_config={"Valor_Total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                                "KM_Total": st.column_config.NumberColumn("Km", format="%.1f")})
    st.download_button("⬇️ Exportar CSV", vis.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       f"lox_historico_{hoje:%Y%m%d}.csv", "text/csv")


# ==========================================
# MÓDULO: CONFIGURAÇÕES
# ==========================================

def modulo_configuracoes():
    cabecalho("⚙️ Configurações", "Tudo que é sensível fica nos Secrets do Streamlit, fora do código")
    s = store()
    prest, tom, em = cfg.prestador(), cfg.tomador(), cfg.email()
    itens = [
        ("Banco de dados", s.modo == "Google Sheets", s.modo),
        ("Chave PIX e CPF", "NAO_CONFIGURADO" not in prest["pix"] + prest["cpf"], "[lox] pix_key / cpf_prestador"),
        ("Remetente de e-mail (SMTP)", bool(em["usuario"] and em["senha"]), em["usuario"] or "[email] smtp_user / smtp_pass"),
        ("E-mail de destino", bool(em["destino"]), em["destino"] or "[email] destino"),
        ("Logins fora do código", bool(cfg._secao("auth")), "[auth] usuario = \"senha\""),
    ]
    with st.container(border=True):
        st.markdown("**Checklist**")
        for nome, ok, info in itens:
            st.markdown(f"{'✅' if ok else '⚠️'} **{nome}** — {info}")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**Matriz financeira**")
            st.markdown(f"""
| Parâmetro | Valor |
|---|---:|
| Tarifa base | {doc.moeda(cfg.TARIFA_BASE)} |
| Por km | {doc.moeda(cfg.VALOR_POR_KM)} |
| Minuto de viagem | {doc.moeda(cfg.VALOR_MINUTO_VIAGEM)} |
| Minuto de espera | {doc.moeda(cfg.VALOR_MINUTO_ESPERA)} |
""" + "".join(f"| {k} | {doc.moeda(v['valor'])} |\n" for k, v in cfg.ROTAS_HOMOLOGADAS.items()))
    with c2:
        with st.container(border=True):
            st.markdown("**Emitente e tomador**")
            st.markdown(f"{prest['nome']} · {prest['assinatura']}  \nBanco {prest['banco']} · {prest['cidade']}  \n"
                        f"Tomador: {tom['razao']} · CNPJ {tom['cnpj']}")
            if st.button("📧 Enviar e-mail de teste para mim", disabled=not em["usuario"]):
                try:
                    pdf = doc.gerar_recibo_pdf("000-TESTE", cfg.agora(), [_op_exemplo()], prest, tom)
                    mailer.enviar(em, em["usuario"], "", "Lox | teste de envio",
                                  "Teste de configuração do Lox. O anexo é um recibo de exemplo.",
                                  pdf, "recibo_teste.pdf")
                    st.success(f"Teste enviado para {em['usuario']}.")
                except Exception as e:
                    st.error(f"Falha: {e}")

    with st.expander("Modelo de Secrets (cole no painel do Streamlit Cloud › Settings › Secrets)"):
        st.code("""[lox]
pix_key = "sua-chave-pix"
cpf_prestador = "000.000.000-00"
nome = "Francesco de Andrade Apratto"
cidade = "Porto Alegre/RS"
recibo_inicial = 14          # próximo número da sequência NNN-AAAA

[tomador]
razao = "SULMED ASSISTÊNCIA MÉDICA LTDA."
cnpj = "90.747.908/0001-56"

[email]
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "seu-email@gmail.com"
smtp_pass = "senha-de-app-do-google"   # myaccount.google.com/apppasswords
destino = "financeiro@sulmed.com.br"
cc = "seu-email@gmail.com"

[auth]
tiesco = "sua-senha"
sulmed = "senha-da-sulmed"

[connections.gsheets]
# ... (credenciais da service account, já existentes)""", language="toml")


def _op_exemplo():
    return {"ID": "TESTE", "Tipo": "Traslado", "Data_Traslado": cfg.agora().strftime("%d/%m/%Y"),
            "Hora_Embarque": "08:00", "Passageiro": "Passageiro de teste", "Solicitante": "Teste",
            "Centro_Custo": "Outros", "Origem": "Porto Alegre", "Destino": "Canoas", "KM_Total": 15,
            "Valor_Total": 0, "Espera_Min": 0, "Detalhe": "Embarque: Porto Alegre\nDestino: Canoas"}


# ==========================================
# ROTEADOR DE ARQUITETURA
# ==========================================

PAGINAS_ADMIN = {
    "📊 Painel": modulo_painel,
    "🚘 Traslados": modulo_passageiros,
    "📦 Cargas / Entregas": modulo_entregas,
    "🧾 Faturamento": modulo_faturamento,
    "📚 Histórico": modulo_historico,
    "⚙️ Configurações": modulo_configuracoes,
}


def roteador_principal():
    st.sidebar.markdown('<div class="lox-marca">SylvaCore | Lox</div>', unsafe_allow_html=True)
    usuario_atual = st.session_state.get("cliente", "tiesco")
    nomes = {"tiesco": "Francesco", "sulmed": "Sulmed Administrativo"}
    st.sidebar.caption(f"Operador: {nomes.get(usuario_atual, usuario_atual.capitalize())} · v{VERSAO}")
    st.sidebar.markdown("---")

    # --- ESQUELETO: portal self-service B2B (desativado por padrão) ---
    # Quando FEATURE_FLAGS["sulmed_selfservice_ativo"] virar True, o login
    # "sulmed" passa a agendar sozinho (sem acesso ao financeiro interno).
    if usuario_atual == "sulmed":
        if cfg.FEATURE_FLAGS["sulmed_selfservice_ativo"]:
            modulo_passageiros()
        else:
            cabecalho("🚧 Portal Sulmed")
            st.info("Acesso reservado para quando o modo self-service for ativado. "
                    "Por enquanto, agendamentos seguem direto com a SylvaCore.")
    else:
        if "_ir_para" in st.session_state:
            st.session_state["pagina"] = st.session_state.pop("_ir_para")
        if "pagina" not in st.session_state:
            st.session_state["pagina"] = "📊 Painel"
        pagina = st.sidebar.radio("Módulo", list(PAGINAS_ADMIN), key="pagina", label_visibility="collapsed")
        s = store()
        try:
            pend = s.listar_ops()
            n_pend = int((pend["Status"] == "Pendente").sum())
            n_abertos = int(s.listar_recibos()["Status"].isin(["Emitido", "Assinado", "Enviado"]).sum())
            st.sidebar.markdown("---")
            st.sidebar.caption(f"🟡 {n_pend} a faturar · 📨 {n_abertos} recibos em aberto")
        except Exception:
            pass
        st.sidebar.caption(f"Banco: {s.modo}")
        PAGINAS_ADMIN[pagina]()

    st.sidebar.markdown("---")
    if st.sidebar.button("Encerrar sessão"):
        st.session_state.clear()
        st.rerun()


# ==========================================
# EXECUÇÃO DA APLICAÇÃO (ISOLAMENTO DE ERRO)
# ==========================================
if __name__ == "__main__":
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        if not st.session_state.get("autenticado"):
            tela_login()
        else:
            roteador_principal()
    except Exception:
        st.error("⚠️ Falha Crítica de Execução na Aplicação")
        st.code(traceback.format_exc())
