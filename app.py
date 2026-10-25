import json
import os
import traceback
import urllib.parse
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from lox import VERSAO
from lox import atalhos as atl
from lox import config as cfg
from lox import documentos as doc
from lox import mailer, prazos
from lox.pricing import calcular_rota_automatica
from lox.storage import obter_store, proximo_numero_recibo

# ==========================================
# LOX - MOTOR DE LOGÍSTICA EXECUTIVA B2B
# Versão: 7.1 - Atalhos de rota, envio ao anexar, vencimento e lembretes
# ==========================================

st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒", layout="wide")

PASTA_ASSINADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recibos")
ASSINADOR_GOVBR = "https://assinador.iti.br"
VALIDADOR_GOVBR = "https://validar.iti.gov.br"

ETAPAS_RECIBO = ["Emitido", "Assinado", "Enviado", "Pago"]
ICONE_STATUS = {"Pendente": "🟡", "Faturado": "🔵", "Faturado (externo)": "⚪", "Pago": "🟢",
                "Emitido": "📝", "Assinado": "✍️", "Enviado": "📨"}
PAG_TRASLADOS, PAG_FATURAMENTO = "🚘 Traslados", "🧾 Faturamento"

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
  .lox-kpi.alerta b { color: #B3261E; }
  .lox-kpi small { opacity: .6; }
  .lox-hero { padding: 4px 0 10px; }
  .lox-hero h1 { margin: 0; font-size: 1.9rem; }
  .lox-hero p { margin: 2px 0 0; opacity: .7; }
  .lox-preco { white-space: nowrap; font-size: 2.4rem; font-weight: 800; color: #0F4C81; line-height: 1.1; }
  .lox-preco.p { font-size: 1.5rem; }
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
    html = "".join(f'<div class="lox-kpi{" alerta" if len(i) > 3 and i[3] else ""}"><span>{i[0]}</span>'
                   f'<b>{i[1]}</b><small>{i[2]}</small></div>' for i in itens)
    st.markdown(f'<div class="lox-kpis">{html}</div>', unsafe_allow_html=True)


def para_data(serie):
    return pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce")


def data_txt(txt):
    try:
        return datetime.strptime(str(txt)[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def hora_txt(txt, padrao=time(8, 0)):
    try:
        return datetime.strptime(str(txt).strip(), "%H:%M").time()
    except ValueError:
        return padrao


def padrao(chave, valor):
    """Valor inicial de um widget com key, sem conflitar com o pré-preenchimento dos atalhos."""
    if chave not in st.session_state:
        st.session_state[chave] = valor


def avisar(msg, tipo="success"):
    """Mensagem que sobrevive ao st.rerun()."""
    st.session_state.setdefault("_avisos", []).append((tipo, msg))


def mostrar_avisos():
    for tipo, msg in st.session_state.pop("_avisos", []):
        getattr(st, tipo)(msg)


def ir_para(pagina, recibo=None):
    st.session_state["_ir_para"] = pagina
    if recibo:
        st.session_state["recibo_aberto"] = recibo
        st.session_state["_fat_aba"] = "Recibos"


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
    return (datetime.combine(data_corrida, hora) - cfg.agora()).total_seconds() / 3600


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
# RECIBOS: emissão, prazo e situação
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
    sel = ops[ops["ID"].isin(rec["Operacoes"].split(","))].copy()
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


def referencia(rec, ops):
    sel = ops[ops["ID"].isin(rec["Operacoes"].split(","))]
    if sel.empty:
        return rec["Obs"] or "—"
    if len(sel) == 1:
        o = sel.iloc[0]
        trajeto = o["Origem"].split("<->")[-1].strip() if o["Destino"] == atl.DESTINO_FIXO else o["Destino"]
        return f"{o['Tipo']} de {o['Data_Traslado']} · {trajeto}"
    datas = para_data(sel["Data_Traslado"]).dropna().sort_values()
    return f"{len(sel)} operações de {datas.iloc[0]:%d/%m} a {datas.iloc[-1]:%d/%m}" if len(datas) else f"{len(sel)} operações"


def situacao(rec, hoje):
    """(texto, dias úteis de atraso). O prazo só corre depois do envio por e-mail."""
    if rec["Status"] == "Pago":
        return "🟢 Pago", 0
    venc = data_txt(rec["Vencimento"])
    if not venc:
        return f"{ICONE_STATUS.get(rec['Status'], '')} {rec['Status']} · aguardando envio", 0
    if hoje < venc:
        return f"⏳ No prazo · vence {venc:%d/%m}", 0
    if hoje == venc:
        return "🟠 Vence hoje", 0
    atraso = prazos.dias_uteis_entre(venc, hoje)
    return (f"🔴 Vencido há {atraso} dia(s) útil(eis)" if atraso else f"🟠 Venceu em {venc:%d/%m}"), atraso


def recibos_em_aberto(hoje):
    s = store()
    recs, ops = s.listar_recibos(), s.listar_ops()
    saida = []
    for _, r in recs[recs["Status"] != "Pago"].iterrows():
        texto, atraso = situacao(r, hoje)
        saida.append({**r.to_dict(), "Referencia": referencia(r, ops), "Situacao": texto, "Atraso": atraso})
    return saida


def rodape_pendencias(numero_atual, hoje):
    """Rodapé informativo no e-mail de cada recibo novo: o jeito menos chato de lembrar o que está em aberto."""
    outros = [r for r in recibos_em_aberto(hoje) if r["Numero"] != numero_atual and r["Status"] == "Enviado"]
    if not outros:
        return ""
    linhas = []
    for r in outros:
        venc = data_txt(r["Vencimento"])
        quando = (f"vencido em {venc:%d/%m}" if venc and venc < hoje else f"vence em {venc:%d/%m}") if venc else "enviado"
        linhas.append(f"- Recibo Nº {r['Numero']} ({r['Referencia']}, {doc.moeda(r['Total'])}, {quando})")
    return "\n\nPara conferência, consta em aberto também:\n" + "\n".join(linhas)


def assunto_padrao(rec):
    return f"Recibo Nº {rec['Numero']} - {cfg.prestador()['nome']} - {doc.moeda(rec['Total'])}"


def corpo_padrao(rec, venc, hoje):
    prest = cfg.prestador()
    return (f"Prezados,\n\nSegue em anexo o recibo Nº {rec['Numero']}, devidamente assinado via gov.br, "
            f"referente aos serviços de logística prestados, no valor de {doc.moeda(rec['Total'])}.\n\n"
            f"Vencimento: {venc:%d/%m/%Y} ({cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias úteis após o recebimento deste e-mail).\n"
            f"Dados para pagamento: PIX {prest['pix']}."
            f"{rodape_pendencias(rec['Numero'], hoje)}"
            f"\n\nAtenciosamente,\n{prest['nome']}\n{prest['assinatura']}")


def vencimento_previsto(rec, hoje):
    return data_txt(rec["Vencimento"]) or prazos.somar_dias_uteis(hoje, cfg.PRAZO_PAGAMENTO_DIAS_UTEIS)


def enviar_recibo(rec, assinado, para=None, cc=None, assunto=None, corpo=None):
    """Envia o recibo assinado e registra envio + vencimento. Usado pelo envio automático e pelo manual."""
    em, hoje = cfg.email(), cfg.agora().date()
    venc = vencimento_previsto(rec, hoje)
    destinos = mailer.enviar(em, em["destino"] if para is None else para, em["cc"] if cc is None else cc,
                             assunto or assunto_padrao(rec), corpo or corpo_padrao(rec, venc, hoje),
                             [(assinado, nome_arquivo(rec["Numero"], True))])
    campos = {"Enviado_Em": cfg.agora().strftime("%d/%m/%Y %H:%M"), "Enviado_Para": ", ".join(destinos)}
    if not rec["Vencimento"]:
        campos["Vencimento"] = venc.strftime("%d/%m/%Y")
    if rec["Status"] != "Pago":
        campos["Status"] = "Enviado"
    store().atualizar_recibo(rec["Numero"], campos)
    return destinos, venc


# ==========================================
# LEMBRETES (o Lox prepara, você revisa e envia)
# ==========================================

def nivel_recomendado(atraso):
    n1, n2, n3 = cfg.LEMBRETE_NIVEIS
    return 3 if atraso >= n3 else 2 if atraso >= n2 else 1 if atraso >= n1 else 0


def montar_lembrete(nivel, rec, hoje):
    em, prest = cfg.email(), cfg.prestador()
    abertos = recibos_em_aberto(hoje)
    este = next(r for r in abertos if r["Numero"] == rec["Numero"])
    venc = data_txt(rec["Vencimento"])
    envio = rec["Enviado_Em"][:10]
    total_aberto = doc.moeda(sum(r["Total"] for r in abertos))
    assinatura = f"\n\nAtenciosamente,\n{prest['nome']}\n{prest['assinatura']}"
    if nivel == 1:
        return (em["contato"], em["cc"], f"Conferência - recibo Nº {rec['Numero']}",
                f"Olá, tudo bem?\n\nFazendo meu fechamento, notei que o recibo Nº {rec['Numero']} "
                f"({este['Referencia']}, {doc.moeda(rec['Total'])}), enviado em {envio}, ainda consta em aberto "
                f"por aqui. Consegues verificar se ele ficou fora do último lote de pagamento?\n\n"
                f"Reenvio o recibo assinado em anexo para facilitar.\n\nObrigado!\n{prest['nome']}")
    cc = ", ".join(x for x in [em["contato"], em["cc"]] if x and x != em["financeiro"])
    if nivel == 2:
        return (em["financeiro"], cc, f"Recibos em aberto - posição em {hoje:%d/%m/%Y} - {prest['nome']}",
                f"Prezados,\n\nPara facilitar a conferência, segue em anexo o extrato dos recibos que constam em "
                f"aberto até hoje ({len(abertos)} recibo(s), total {total_aberto}). O recibo Nº {rec['Numero']} "
                f"venceu em {venc:%d/%m/%Y}, conforme a condição de {cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias úteis "
                f"após o recebimento.\n\nSe algum já tiver sido pago, me avisem que dou baixa por aqui — às vezes "
                f"um item fica fora do lote.\n\nDados para pagamento: PIX {prest['pix']}.{assinatura}")
    return (em["financeiro"], cc, f"Recibo Nº {rec['Numero']} - pagamento pendente desde {venc:%d/%m/%Y}",
            f"Prezados,\n\nRetomo o recibo Nº {rec['Numero']} ({este['Referencia']}, {doc.moeda(rec['Total'])}), "
            f"enviado em {envio}. Pela condição acordada — pagamento em até {cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias "
            f"úteis após o recebimento —, o vencimento foi em {venc:%d/%m/%Y}; hoje são {este['Atraso']} dias úteis "
            f"em aberto.\n\nPeço, por gentileza, a confirmação de uma data prevista para o crédito. Segue o extrato "
            f"atualizado em anexo.\n\nFico à disposição.{assinatura}")


def extrato_pdf(hoje):
    abertos = [r for r in recibos_em_aberto(hoje) if r["Status"] == "Enviado"]
    return doc.gerar_extrato_pdf(abertos, cfg.prestador(), cfg.tomador(), hoje)


# ==========================================
# ATALHOS DE ROTA
# ==========================================

def registrar(op, base_atalho=None):
    existentes = set(store().listar_ops()["ID"])
    if op["ID"] in existentes:  # dois registros no mesmo segundo
        op["ID"] = next(f"{op['ID']}-{i}" for i in range(2, 100) if f"{op['ID']}-{i}" not in existentes)
    store().adicionar_op(op)
    notificar_operador(f"Novo {op['Tipo'].lower()}: {op['Passageiro']} em {op['Data_Traslado']} - {doc.moeda(op['Valor_Total'])}")
    st.session_state["ultima_op"] = op
    st.session_state["ultima_base_atalho"] = base_atalho
    st.session_state.pop("cotacao", None)


def usar_atalho(a, data_traslado, emitir=True):
    s = store()
    op = atl.op_do_atalho(a, data_traslado, cfg.agora())
    registrar(op)
    s.atualizar_atalho(a["ID"], {"Usos": int(a["Usos"]) + 1, "Ultimo_Uso": cfg.agora().strftime("%d/%m/%Y")})
    if emitir:
        numero = emitir_recibo([op["ID"]], cfg.agora().date())
        if numero:
            st.session_state.pop("ultima_op", None)
            avisar(f"Traslado registrado e recibo Nº {numero} emitido pelo atalho “{a['Nome']}”. "
                   "Agora é só baixar, assinar no gov.br e anexar.")
            ir_para(PAG_FATURAMENTO, numero)


def preencher_formulario(a, data_traslado):
    """'Editar antes': joga o atalho no formulário para ajustar algo antes de registrar."""
    p = {"tr_data": data_traslado, "tr_hora_ida": hora_txt(a["Hora_Ida"]), "tr_tem_volta": bool(a["Hora_Volta"]),
         "tr_hora_volta": hora_txt(a["Hora_Volta"], time(17, 0)), "tr_passageiro": a["Passageiro"],
         "tr_solicitante": a["Solicitante"],
         "tr_cc": a["Centro_Custo"] if a["Centro_Custo"] in cfg.CENTROS_DE_CUSTO else cfg.CENTROS_DE_CUSTO[0]}
    if a["Modalidade"] == atl.HOMOLOGADA:
        p.update({"tr_modalidade": "Rota Homologada (Frequente)", "tr_rota_fixa": a["Rota"],
                  "tr_espera_extra": int(float(a["Espera_Min"] or 0))})
    else:
        pontos = json.loads(a["Enderecos"])
        cidade = lambda c: c if c in cfg.CIDADES_RMPA else cfg.CIDADES_RMPA[0]
        p.update({"tr_modalidade": "Nova Rota (Sob Demanda)", "rua_origem": pontos[0]["rua"],
                  "cid_origem": cidade(pontos[0]["cidade"]), "qtd_paradas": len(pontos) - 2,
                  "rua_dest": pontos[-1]["rua"], "cid_dest": cidade(pontos[-1]["cidade"]),
                  "ida_volta": bool(a["Ida_Volta"])})
        for i, pt in enumerate(pontos[1:-1]):
            p.update({f"p_rua_{i}": pt["rua"], f"p_cid_{i}": cidade(pt["cidade"]), f"e_{i}": int(pt.get("espera") or 0)})
    st.session_state["_prefill"] = p


def recalcular_atalho(a):
    pontos = json.loads(a["Enderecos"])
    enderecos = [f"{p['rua']} - {p['cidade']}" for p in pontos] + ([f"{pontos[0]['rua']} - {pontos[0]['cidade']}"]
                                                                    if a["Ida_Volta"] else [])
    r = calcular_rota_automatica(enderecos, sum(float(p.get("espera") or 0) for p in pontos))
    if isinstance(r, dict):
        store().atualizar_atalho(a["ID"], {"Valor": r["total"], "KM": r["km"]})
        avisar(f"Atalho “{a['Nome']}” atualizado: {doc.moeda(a['Valor'])} → {doc.moeda(r['total'])}.")
    else:
        avisar(r, "error")


def painel_atalhos():
    s = store()
    lista = s.listar_atalhos().sort_values("Usos", ascending=False)
    sugestoes = atl.sugestoes(s.listar_ops(), lista, cfg.REPETICOES_SUGERIR_ATALHO)[:3]
    if lista.empty and not sugestoes:
        return
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        c1.markdown("**⭐ Atalhos** — um toque registra o traslado e já emite o recibo com o valor combinado")
        data_at = c2.date_input("Data do traslado", cfg.agora().date(), format="DD/MM/YYYY", key="at_data",
                                label_visibility="collapsed")
        for inicio in range(0, len(lista), 3):
            cols = st.columns(3)
            for col, (_, a) in zip(cols, list(lista.iloc[inicio:inicio + 3].iterrows())):
                with col, st.container(border=True):
                    st.markdown(f"**{a['Nome']}**")
                    st.caption(atl.resumo(a))
                    st.markdown(f'<div class="lox-preco p">{doc.moeda(a["Valor"])}</div>', unsafe_allow_html=True)
                    if st.button("Registrar e emitir", type="primary", width="stretch", key=f"at_usar_{a['ID']}"):
                        usar_atalho(a, data_at)
                        st.rerun()
                    b1, b2 = st.columns([3, 1])
                    if b1.button("✏️ Editar", width="stretch", key=f"at_edit_{a['ID']}",
                                 help="Abre o formulário preenchido para ajustar data, horário ou espera antes de registrar"):
                        preencher_formulario(a, data_at)
                        st.rerun()
                    with b2.popover("⋯", width="stretch"):
                        st.caption(f"Usado {int(a['Usos'])}x" + (f" · último em {a['Ultimo_Uso']}" if a["Ultimo_Uso"] else ""))
                        if a["Modalidade"] == atl.NOVA and st.button("Recalcular valor pelo mapa", key=f"at_rec_{a['ID']}"):
                            recalcular_atalho(a)
                            st.rerun()
                        if st.button("Remover atalho", key=f"at_del_{a['ID']}"):
                            s.atualizar_atalho(a["ID"], {"Ativo": "0"})
                            st.rerun()
        for vezes, op in sugestoes:
            novo = atl.atalho_do_historico(op, cfg.agora())
            c1, c2 = st.columns([4, 1])
            c1.info(f"💡 Você já fez **{novo['Nome']}** {vezes} vezes ({doc.moeda(op['Valor_Total'])}). Vira atalho?")
            if c2.button("⭐ Salvar", key=f"sug_{op['ID']}", width="stretch"):
                s.adicionar_atalho(novo)
                avisar(f"Atalho “{novo['Nome']}” criado.")
                st.rerun()


def oferta_salvar_atalho(op):
    base = st.session_state.get("ultima_base_atalho")
    if not base or op.get("Tipo") != "Traslado":
        return
    s = store()
    chave = atl.chave_de_op(op)
    existente = [a for _, a in s.listar_atalhos().iterrows() if atl.chave_de_atalho(a) == chave]
    if existente:
        st.caption(f"⭐ Esta rota já tem atalho: “{existente[0]['Nome']}”.")
        return
    vezes = atl.contar_repeticoes(s.listar_ops(), chave)
    if vezes >= cfg.REPETICOES_SUGERIR_ATALHO:
        st.info(f"💡 Você já fez esta rota {vezes} vezes. Salve como atalho e da próxima vez é um toque só.")
    with st.expander("⭐ Salvar como atalho", expanded=vezes >= cfg.REPETICOES_SUGERIR_ATALHO):
        sugestao = atl.atalho_do_historico(op, cfg.agora())["Nome"]
        nome = st.text_input("Nome do atalho", sugestao, key=f"nome_at_{op['ID']}")
        st.caption(f"O valor fica congelado em {doc.moeda(op['Valor_Total'])} — mesmo trajeto, mesmo preço.")
        if st.button("Salvar atalho", key=f"salvar_at_{op['ID']}"):
            s.adicionar_atalho(atl.novo_atalho(nome, base["modalidade"], op, base.get("pontos"),
                                               base.get("ida_volta", False), agora=cfg.agora()))
            st.session_state["ultima_base_atalho"] = None
            avisar(f"Atalho “{nome}” salvo. Ele aparece no topo da tela de Traslados.")
            st.rerun()


def botao_emitir_agora(op):
    """Atalho pós-agendamento: recibo individual na hora, como na v6.1."""
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🧾 Emitir recibo agora", type="primary", width="stretch", key=f"emitir_{op['ID']}"):
            numero = emitir_recibo([op["ID"]], cfg.agora().date())
            if numero:
                st.session_state.pop("ultima_op", None)
                ir_para(PAG_FATURAMENTO, numero)
                st.rerun()
    with c2:
        st.link_button("📲 Despachar no WhatsApp", link_whatsapp(op), width="stretch")
    with c3:
        if st.button("➕ Novo agendamento", width="stretch", key=f"novo_{op['ID']}"):
            st.session_state.pop("ultima_op", None)
            st.session_state.pop("cotacao", None)
            st.rerun()


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
            oferta_salvar_atalho(op)
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
    abertos = recibos_em_aberto(hoje)
    vencidos = sorted([r for r in abertos if r["Atraso"] > 0], key=lambda r: -r["Atraso"])

    pend = ops[ops["Status"] == "Pendente"]
    mes = ops[(ops["_d"].dt.month == hoje.month) & (ops["_d"].dt.year == hoje.year)]
    recebido_mes = recs[(recs["_pago"].dt.month == hoje.month) & (recs["_pago"].dt.year == hoje.year)]

    kpis([("A faturar", doc.moeda(pend["Valor_Total"].sum()), f"{len(pend)} operações pendentes"),
          ("A receber", doc.moeda(sum(r["Total"] for r in abertos)), f"{len(abertos)} recibos em aberto"),
          ("Vencido", doc.moeda(sum(r["Total"] for r in vencidos)), f"{len(vencidos)} recibos fora do prazo", bool(vencidos)),
          ("Recebido no mês", doc.moeda(recebido_mes["Total"].sum()), f"{len(recebido_mes)} recibos quitados"),
          ("Operações no mês", str(len(mes)), doc.moeda(mes["Valor_Total"].sum()))])

    if vencidos:
        pior = vencidos[0]
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.error(f"**{len(vencidos)} recibo(s) fora do prazo de {cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias úteis.** "
                     f"O mais antigo: Nº {pior['Numero']} ({pior['Referencia']}) — {pior['Situacao'][2:]}.")
            c2.markdown("<br>", unsafe_allow_html=True)
            if c2.button("Preparar lembrete", type="primary", width="stretch"):
                ir_para(PAG_FATURAMENTO, pior["Numero"])
                st.rerun()

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
        st.markdown(f"**Recibos em aberto** — prazo combinado: {cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias úteis após o envio")
        if not abertos:
            st.caption("Tudo quitado. 🎉")
        else:
            t = pd.DataFrame(abertos)[["Numero", "Referencia", "Enviado_Em", "Vencimento", "Situacao", "Total"]]
            t["Total"] = t["Total"].map(doc.moeda)
            st.dataframe(t.rename(columns={"Numero": "Nº", "Referencia": "Referência", "Enviado_Em": "Enviado em",
                                           "Situacao": "Situação"}), hide_index=True, width="stretch")

    candidatas = atl.candidatas_homologacao(ops.drop(columns="_d"), hoje, cfg.HOMOLOGACAO_MIN_VIAGENS)
    if candidatas:
        with st.container(border=True):
            st.markdown("**🤝 Rotas candidatas a valor fixo** — argumento para propor homologação à Sulmed")
            for c in candidatas:
                st.markdown(f"- **{c['rota']}** · {c['viagens']} viagens em 60 dias · média {doc.moeda(c['media'])} "
                            f"→ sugestão de valor fixo: **{doc.moeda(c['sugestao'])}**")


# ==========================================
# MÓDULO: TRASLADOS (PASSAGEIROS)
# ==========================================

def modulo_passageiros():
    cabecalho("🚘 Cotação e Agendamento", "Tarifa corporativa plana · zero tarifa dinâmica")
    if card_ultima_op("Traslado"):
        return
    admin = st.session_state.get("cliente") != "sulmed"
    if admin:
        painel_atalhos()
    for k, v in st.session_state.pop("_prefill", {}).items():
        st.session_state[k] = v

    st.warning(f"⏱️ **REGRA OPERACIONAL:** agendamentos devem ser solicitados com antecedência mínima "
               f"de 1 turno ({cfg.ANTECEDENCIA_MIN_HORAS} horas).")

    padrao("tr_data", date.today())
    padrao("tr_hora_ida", cfg.agora().time().replace(second=0, microsecond=0))
    padrao("tr_hora_volta", time(17, 0))
    with st.container(border=True):
        col_data, col_hora_ida, col_hora_volta = st.columns(3)
        with col_data:
            data_corrida = st.date_input("Data do Traslado", format="DD/MM/YYYY", key="tr_data")
        with col_hora_ida:
            hora_corrida = st.time_input("Horário de Ida", step=60, key="tr_hora_ida")
        with col_hora_volta:
            tem_volta = st.checkbox("Incluir hora da volta?", key="tr_tem_volta")
            hora_retorno = st.time_input("Horário da Volta", step=60, key="tr_hora_volta") if tem_volta else None
        hora_db_str = atl.hora_embarque(hora_corrida.strftime("%H:%M"), hora_retorno.strftime("%H:%M") if hora_retorno else "")

        col_pass, col_sol, col_cc = st.columns(3)
        with col_pass:
            passageiro = st.text_input("Passageiro / Médico(a)", placeholder="Ex: Dr. XPTO", key="tr_passageiro")
        with col_sol:
            solicitante = st.text_input("Seu nome e contato", placeholder="Ex: Fulano - (51) 9999-9999", key="tr_solicitante")
        with col_cc:
            centro_custo = st.selectbox("Centro de Custo", cfg.CENTROS_DE_CUSTO, key="tr_cc")

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
                         horizontal=True, key="tr_modalidade")

    if tipo_rota == "Nova Rota (Sob Demanda)":
        with st.container(border=True):
            col_rua_origem, col_cid_origem = st.columns([3, 1])
            with col_rua_origem:
                rua_origem = st.text_input("Endereço de Embarque (Rua e Nº)", key="rua_origem")
            with col_cid_origem:
                cid_origem = st.selectbox("Cidade (Origem)", cfg.CIDADES_RMPA, key="cid_origem")
            origem_completa = f"{rua_origem} - {cid_origem}" if rua_origem else ""

            qtd_paradas = st.selectbox("Paradas intermediárias", [0, 1, 2, 3], key="qtd_paradas")
            paradas, pontos_paradas, espera_total = [], [], 0
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
                    pontos_paradas.append({"rua": p_rua, "cidade": p_cid, "espera": e_min})
                    espera_total += e_min

            col_rua_dest, col_cid_dest = st.columns([3, 1])
            with col_rua_dest:
                rua_dest = st.text_input("Endereço de Desembarque Final", key="rua_dest")
            with col_cid_dest:
                cid_dest = st.selectbox("Cidade (Destino)", cfg.CIDADES_RMPA, key="cid_dest")
            destino_completo = f"{rua_dest} - {cid_dest}" if rua_dest else ""
            ida_e_volta = st.checkbox("🔄 Retornar à base", key="ida_volta")

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
                        pontos = ([{"rua": rua_origem, "cidade": cid_origem, "espera": 0}] + pontos_paradas
                                  + [{"rua": rua_dest, "cidade": cid_dest, "espera": 0}])
                        registrar({**base, "ID": cfg.agora().strftime("%Y%m%d%H%M%S"),
                                   "Origem": origem_completa,
                                   "Destino": f"{destino_completo} (I/V)" if ida_e_volta else destino_completo,
                                   "KM_Total": r["km"], "Valor_Total": r["total"], "Espera_Min": espera_total,
                                   "Detalhe": doc.detalhe_rota(origem_completa, enderecos[-1], hora_db_str, enderecos)},
                                  {"modalidade": atl.NOVA, "pontos": pontos, "ida_volta": ida_e_volta})
                        st.rerun()
        elif cot:
            st.caption("Os endereços mudaram — calcule a cotação novamente.")

    else:
        st.info("Rotas com valores fixos já negociados e aprovados.")
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                rota_fixa = st.selectbox("Rota homologada", list(cfg.ROTAS_HOMOLOGADAS), key="tr_rota_fixa")
            with c2:
                espera_extra = st.number_input("Espera extra (min)", min_value=0, step=5, key="tr_espera_extra")
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
                           "Destino": atl.DESTINO_FIXO, "KM_Total": 0, "Valor_Total": valor_final,
                           "Espera_Min": espera_extra,
                           "Detalhe": doc.detalhe_rota(rota_fixa, atl.DESTINO_FIXO, hora_db_str)},
                          {"modalidade": atl.HOMOLOGADA})
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
            for k in ("carga_rota", "carga_roteiro_calculado", "carga_km"):
                st.session_state.pop(k, None)
            st.rerun()


# ==========================================
# MÓDULO: FATURAMENTO (recibo -> gov.br -> e-mail -> pagamento -> lembrete)
# ==========================================

def trilha(status):
    atual = ETAPAS_RECIBO.index(status) if status in ETAPAS_RECIBO else 0
    html = "".join(
        f'<div class="lox-etapa {"ok" if i < atual or status == "Pago" else "atual" if i == atual else ""}">'
        f'{"✓ " if i < atual or status == "Pago" else ""}{e}</div>'
        for i, e in enumerate(ETAPAS_RECIBO))
    st.markdown(f'<div class="lox-etapas">{html}</div>', unsafe_allow_html=True)


def ao_anexar(rec, dados, automatico):
    """Confere o PDF assinado e, se o envio automático estiver ligado, já manda para a Sulmed."""
    numero, s = rec["Numero"], store()
    ok, motivo = doc.conferir_pdf_assinado(dados, numero)
    if not ok:
        avisar(f"Não anexei: {motivo}.", "error")
        return
    guardar_assinado(numero, dados)
    if rec["Status"] == "Emitido":
        s.atualizar_recibo(numero, {"Status": "Assinado", "Assinado_Em": cfg.agora().strftime("%d/%m/%Y %H:%M")})
        rec = {**rec, "Status": "Assinado"}
    em = cfg.email()
    if automatico and rec["Status"] in ("Emitido", "Assinado") and em["usuario"] and em["destino"]:
        try:
            destinos, venc = enviar_recibo(rec, dados)
            avisar(f"✍️ {motivo.capitalize()}. 📨 Enviado às {cfg.agora():%H:%M} para {', '.join(destinos)} · "
                   f"vencimento {venc:%d/%m/%Y}.")
        except Exception as e:
            avisar(f"PDF anexado, mas o envio falhou: {e}", "error")
    elif automatico and rec["Status"] in ("Emitido", "Assinado"):
        avisar("PDF anexado. Para enviar sozinho, configure o e-mail em ⚙️ Configurações.", "warning")
    else:
        avisar(f"✍️ PDF anexado — {motivo}.")


def painel_recibo(rec):
    s, hoje = store(), cfg.agora().date()
    numero, status = rec["Numero"], rec["Status"]
    importado = rec["Obs"].startswith("Importado")
    texto_sit, atraso = situacao(rec, hoje)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.subheader(f"Recibo Nº {numero}")
        st.caption(f"Emitido em {rec['Emissao']} · {referencia(rec, s.listar_ops())}"
                   + (f" · enviado {rec['Enviado_Em']} para {rec['Enviado_Para']}" if rec["Enviado_Em"] else "")
                   + (f" · pago em {rec['Pago_Em']}" if rec["Pago_Em"] else ""))
        st.markdown(f"**{texto_sit}**" + (f" · vencimento {rec['Vencimento']}" if rec["Vencimento"] and status != "Pago" else ""))
    with c2:
        st.markdown(f'<div class="lox-preco" style="text-align:right">{doc.moeda(rec["Total"])}</div>',
                    unsafe_allow_html=True)
    trilha(status)

    assinado = ler_assinado(numero)
    em = cfg.email()

    e1, e2 = st.columns(2)
    with e1:
        with st.container(border=True):
            st.markdown("**1 · Baixar o recibo**")
            if importado:
                st.caption("Recibo emitido fora do Lox (cadastrado para acompanhamento).")
                if assinado:
                    st.download_button("⬇️ Baixar PDF assinado", assinado, nome_arquivo(numero, True), "application/pdf",
                                       width="stretch", key=f"dl_{numero}")
            else:
                st.download_button("⬇️ Baixar PDF para assinar", pdf_do_recibo(rec), nome_arquivo(numero), "application/pdf",
                                   width="stretch", key=f"dl_{numero}")
                st.caption("PDF em Helvetica nativa, aceito pelo assinador gov.br.")
    with e2:
        with st.container(border=True):
            st.markdown("**2 · Assinar no gov.br e anexar**")
            st.link_button("🔏 Abrir assinador gov.br", ASSINADOR_GOVBR, width="stretch")
            automatico = st.toggle("Enviar automaticamente ao anexar", value=em["envio_automatico"], key="envio_auto",
                                   disabled=status in ("Enviado", "Pago"))
            arq = st.file_uploader("Anexe o PDF assinado", type="pdf", key=f"up_{numero}", label_visibility="collapsed")
            if arq is not None and st.session_state.get(f"_up_ok_{numero}") != arq.file_id:
                st.session_state[f"_up_ok_{numero}"] = arq.file_id
                ao_anexar(rec, arq.getvalue(), automatico)
                st.rerun()
            if assinado:
                st.caption(f"✍️ PDF assinado anexado ({len(assinado) // 1024} KB). [Validar assinatura]({VALIDADOR_GOVBR})")

    with st.container(border=True):
        st.markdown("**3 · Enviar por e-mail**")
        if not assinado:
            st.caption("Disponível depois de anexar o PDF assinado (passo 2)."
                       + (" Se o recibo já foi assinado em outra sessão, anexe-o de novo." if status != "Emitido" else ""))
        else:
            ja_enviado = status in ("Enviado", "Pago")
            if ja_enviado:
                st.caption(f"📨 Enviado em {rec['Enviado_Em']} para {rec['Enviado_Para']}.")
            with st.expander("Reenviar / editar mensagem" if ja_enviado else "Revisar e enviar", expanded=not ja_enviado):
                venc = vencimento_previsto(rec, hoje)
                with st.form(f"email_{numero}"):
                    c1, c2 = st.columns(2)
                    para = c1.text_input("Para", em["destino"])
                    cc = c2.text_input("Cópia (CC)", em["cc"])
                    assunto = st.text_input("Assunto", assunto_padrao(rec))
                    corpo = st.text_area("Mensagem", corpo_padrao(rec, venc, hoje), height=200)
                    if st.form_submit_button("📨 " + ("Reenviar" if ja_enviado else "Enviar recibo assinado"), type="primary"):
                        try:
                            with st.spinner("Enviando..."):
                                destinos, venc = enviar_recibo(rec, assinado, para, cc, assunto, corpo)
                            avisar(f"📨 Recibo enviado para {', '.join(destinos)} · vencimento {venc:%d/%m/%Y}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Falha ao enviar: {e}")

    with st.container(border=True):
        st.markdown("**4 · Confirmar pagamento**")
        if status == "Pago":
            st.success(f"Pago em {rec['Pago_Em']}.")
        else:
            c1, c2 = st.columns([2, 1])
            data_pg = c1.date_input("Data do crédito", hoje, format="DD/MM/YYYY", key=f"pg_{numero}")
            c2.markdown("<br>", unsafe_allow_html=True)
            if c2.button("🟢 Marcar como pago", key=f"pago_{numero}", width="stretch"):
                s.atualizar_recibo(numero, {"Status": "Pago", "Pago_Em": data_pg.strftime("%d/%m/%Y")})
                s.atualizar_ops(rec["Operacoes"].split(","), {"Status": "Pago"})
                avisar(f"Recibo Nº {numero} quitado.")
                st.rerun()

    if status == "Enviado" and atraso >= 1:
        painel_lembrete(rec, atraso, hoje, assinado)

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


def painel_lembrete(rec, atraso, hoje, assinado):
    numero = rec["Numero"]
    historico = [l.split(":") for l in rec["Lembretes"].split(";") if ":" in l]
    # sobe um degrau por vez: o primeiro contato é sempre o gentil, mesmo com atraso grande
    ultimo = max((int(n) for n, _ in historico), default=0)
    recomendado = max(1, min(nivel_recomendado(atraso), ultimo + 1))
    with st.container(border=True):
        st.markdown(f"**5 · Lembrete de pagamento** — {atraso} dia(s) útil(eis) após o vencimento")
        if historico:
            st.caption("Já enviados: " + " · ".join(f"nível {n} em {d}" for n, d in historico))
        rotulos = {1: "1 · Conferência gentil (contato)", 2: "2 · Extrato ao financeiro", 3: "3 · Formal, pede data"}
        nivel = st.radio("Tom", [1, 2, 3], index=recomendado - 1, format_func=rotulos.get, horizontal=True,
                         key=f"niv_{numero}")
        st.caption(f"Recomendado agora: nível {recomendado}. O Lox nunca envia lembrete sozinho — revise e envie.")
        para0, cc0, assunto0, corpo0 = montar_lembrete(nivel, rec, hoje)
        anexos = [(assinado, nome_arquivo(numero, True))] if assinado else []
        if nivel >= 2:
            anexos.insert(0, (extrato_pdf(hoje), f"Extrato_recibos_em_aberto_{hoje:%Y%m%d}.pdf"))
        with st.form(f"lembrete_{numero}_{nivel}"):
            c1, c2 = st.columns(2)
            para = c1.text_input("Para", para0)
            cc = c2.text_input("Cópia (CC)", cc0)
            assunto = st.text_input("Assunto", assunto0)
            corpo = st.text_area("Mensagem", corpo0, height=230)
            st.caption("Anexos: " + (", ".join(n for _, n in anexos) or "nenhum (anexe o PDF assinado no passo 2 para incluí-lo)"))
            if st.form_submit_button("📨 Enviar lembrete", type="primary"):
                try:
                    destinos = mailer.enviar(cfg.email(), para, cc, assunto, corpo, anexos)
                    registro = ";".join([rec["Lembretes"], f"{nivel}:{hoje:%d/%m/%Y}"]).strip(";")
                    store().atualizar_recibo(numero, {"Lembretes": registro})
                    avisar(f"Lembrete nível {nivel} enviado para {', '.join(destinos)}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao enviar: {e}")
        if nivel >= 2:
            st.download_button("⬇️ Ver extrato (PDF)", anexos[0][0], anexos[0][1], "application/pdf", key=f"ext_{numero}")


def cadastrar_recibo_antigo():
    """Recibo emitido antes do Lox 7 (ou fora dele): entra no acompanhamento de prazo e lembretes."""
    s, hoje = store(), cfg.agora().date()
    with st.expander("➕ Cadastrar recibo emitido fora do Lox"):
        st.caption("Para acompanhar prazo e lembretes de recibos antigos — ex.: o de 23/09. "
                   "Use como número o que está impresso no PDF (Nº da Transação ou Nº do recibo).")
        rotas = list(cfg.ROTAS_HOMOLOGADAS) + ["Outra (descrever)"]
        with st.form("form_importar"):
            c1, c2, c3 = st.columns(3)
            numero = c1.text_input("Número do recibo", placeholder="ex.: 20260923232128")
            data_tr = c2.date_input("Data do traslado", hoje, format="DD/MM/YYYY")
            valor = c3.number_input("Valor (R$)", min_value=0.0, step=5.0)
            c1, c2 = st.columns(2)
            rota = c1.selectbox("Rota", rotas)
            descricao = c2.text_input("Descrição (se 'Outra')")
            c1, c2, c3 = st.columns(3)
            passageiro = c1.text_input("Passageiro")
            hora = c2.text_input("Horário", placeholder="12:10 (Ida) | 17:00 (Volta)")
            centro = c3.selectbox("Centro de Custo", cfg.CENTROS_DE_CUSTO)
            c1, c2, c3 = st.columns(3)
            envio = c1.date_input("Enviado por e-mail em", hoje, format="DD/MM/YYYY")
            ja_pago = c2.checkbox("Já foi pago")
            pago_em = c3.date_input("Pago em", hoje, format="DD/MM/YYYY")
            pdf = st.file_uploader("PDF assinado (opcional — entra como anexo nos lembretes)", type="pdf")
            if st.form_submit_button("Cadastrar", type="primary"):
                numero = numero.strip()
                if not numero or valor <= 0:
                    st.error("Informe o número e o valor.")
                elif numero in set(s.listar_recibos()["Numero"]):
                    st.error(f"Já existe um recibo Nº {numero}.")
                else:
                    homologada = rota != "Outra (descrever)"
                    op_id = f"ANT-{numero}"
                    s.adicionar_op({
                        "ID": op_id, "Data_Agendamento": cfg.agora().strftime("%d/%m/%Y %H:%M"),
                        "Data_Traslado": data_tr.strftime("%d/%m/%Y"), "Hora_Embarque": hora.strip(),
                        "Passageiro": passageiro, "Solicitante": "", "Centro_Custo": centro,
                        "Origem": rota if homologada else descricao, "Destino": atl.DESTINO_FIXO if homologada else "",
                        "KM_Total": 0, "Valor_Total": valor, "Status": "Pago" if ja_pago else "Faturado",
                        "Tipo": "Traslado", "Espera_Min": 0, "Recibo": numero,
                        "Detalhe": doc.detalhe_rota(rota, atl.DESTINO_FIXO, hora.strip()) if homologada else descricao})
                    s.adicionar_recibo({
                        "Numero": numero, "Emissao": envio.strftime("%d/%m/%Y"), "Operacoes": op_id, "Total": valor,
                        "Status": "Pago" if ja_pago else "Enviado", "Enviado_Em": envio.strftime("%d/%m/%Y"),
                        "Vencimento": prazos.somar_dias_uteis(envio, cfg.PRAZO_PAGAMENTO_DIAS_UTEIS).strftime("%d/%m/%Y"),
                        "Pago_Em": pago_em.strftime("%d/%m/%Y") if ja_pago else "", "Obs": "Importado"})
                    if pdf is not None:
                        guardar_assinado(numero, pdf.getvalue())
                    avisar(f"Recibo Nº {numero} cadastrado.")
                    ir_para(PAG_FATURAMENTO, numero)
                    st.rerun()


def modulo_faturamento():
    cabecalho("🧾 Faturamento", "Recibo → assinatura gov.br → e-mail → pagamento")
    s, hoje = store(), cfg.agora().date()
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
            emissao = c2.date_input("Data de emissão", hoje, format="DD/MM/YYYY")
            c3.markdown("<br>", unsafe_allow_html=True)
            if c3.button("🧾 Emitir recibo", type="primary", width="stretch", disabled=sel.empty):
                numero = emitir_recibo(list(sel["ID"]), emissao)
                if numero:
                    ir_para(PAG_FATURAMENTO, numero)
                    avisar(f"Recibo Nº {numero} emitido.")
                    st.rerun()
            st.caption(f"Próximo número: **{proximo_numero_recibo(s, emissao.year)}** · "
                       "um recibo por operação ou vários traslados num recibo consolidado.")
            with st.expander("Operações antigas já cobradas fora do Lox?"):
                st.caption("Marque-as acima e tire-as da fila sem gerar recibo novo.")
                if st.button("Marcar selecionadas como já faturadas", disabled=sel.empty):
                    s.atualizar_ops(list(sel["ID"]), {"Status": "Faturado (externo)"})
                    st.rerun()
    else:
        cadastrar_recibo_antigo()
        recs = s.listar_recibos()
        if recs.empty:
            st.info("Nenhum recibo emitido ainda.")
            return
        recs["_ord"] = para_data(recs["Emissao"])
        recs = recs.sort_values(["_ord", "Numero"], ascending=False)
        filtro = st.radio("Mostrar", ["Em aberto", "Todos"], horizontal=True, label_visibility="collapsed")
        lista = recs[recs["Status"] != "Pago"] if filtro == "Em aberto" else recs
        if lista.empty:
            st.success("Nenhum recibo em aberto. 🎉")
            lista = recs
        rotulos = {}
        for _, r in lista.iterrows():
            texto, _ = situacao(r, hoje)
            rotulos[r["Numero"]] = f"{r['Numero']} · {doc.moeda(r['Total'])} · {texto}"
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
        ("E-mail de destino dos recibos", bool(em["destino"]), em["destino"] or "[email] destino"),
        ("Contato operacional (lembrete 1)", bool(cfg._secao("email").get("contato")), em["contato"] or "[email] contato"),
        ("Financeiro (lembretes 2 e 3)", bool(cfg._secao("email").get("financeiro")), em["financeiro"] or "[email] financeiro"),
        ("Envio automático ao anexar", em["envio_automatico"], "ligado" if em["envio_automatico"] else "desligado"),
        ("Logins fora do código", bool(cfg._secao("auth")), "[auth] usuario = \"senha\""),
    ]
    with st.container(border=True):
        st.markdown("**Checklist**")
        for nome, ok, info in itens:
            st.markdown(f"{'✅' if ok else '⚠️'} **{nome}** — {info}")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**Matriz financeira e prazos**")
            st.markdown(f"""
| Parâmetro | Valor |
|---|---:|
| Tarifa base | {doc.moeda(cfg.TARIFA_BASE)} |
| Por km | {doc.moeda(cfg.VALOR_POR_KM)} |
| Minuto de viagem | {doc.moeda(cfg.VALOR_MINUTO_VIAGEM)} |
| Minuto de espera | {doc.moeda(cfg.VALOR_MINUTO_ESPERA)} |
| Prazo de pagamento | {cfg.PRAZO_PAGAMENTO_DIAS_UTEIS} dias úteis após o envio |
| Lembretes (dias úteis de atraso) | {' / '.join(map(str, cfg.LEMBRETE_NIVEIS))} |
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
                                  [(pdf, "recibo_teste.pdf")])
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
destino = "email-que-recebe-os-recibos@sulmed.com.br"
cc = "seu-email@gmail.com"
contato = "contato-operacional@sulmed.com.br"   # lembrete nível 1
financeiro = "financeiro@sulmed.com.br"          # lembretes níveis 2 e 3
envio_automatico = true

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
    PAG_TRASLADOS: modulo_passageiros,
    "📦 Cargas / Entregas": modulo_entregas,
    PAG_FATURAMENTO: modulo_faturamento,
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
            n_pend = int((s.listar_ops()["Status"] == "Pendente").sum())
            abertos = recibos_em_aberto(cfg.agora().date())
            n_venc = sum(1 for r in abertos if r["Atraso"] > 0)
            st.sidebar.markdown("---")
            st.sidebar.caption(f"🟡 {n_pend} a faturar · 📨 {len(abertos)} em aberto"
                               + (f" · 🔴 {n_venc} vencido(s)" if n_venc else ""))
        except Exception:
            pass
        st.sidebar.caption(f"Banco: {s.modo}")
        mostrar_avisos()
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
