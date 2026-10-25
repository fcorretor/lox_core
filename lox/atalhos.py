"""Atalhos de rotas frequentes (homologadas e novas).

O valor do atalho é congelado na primeira cotação: mesmo trajeto, mesmo preço
(coerente com "zero tarifa dinâmica"). Atualiza só quando o operador pede.
"""
import json
import math
import re
import unicodedata
import uuid
from datetime import timedelta

import pandas as pd

from . import documentos as doc

HOMOLOGADA, NOVA = "Homologada", "Nova"
DESTINO_FIXO = "Rota Fixa Homologada"


def _norm(txt):
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode().lower()
    txt = re.sub(r"\(i/v\)", " ", txt)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", txt).split())


def _separar(endereco):
    rua, _, cidade = str(endereco).rpartition(" - ")
    return (rua, cidade) if rua else (endereco, "")


def chave_rota(modalidade, origem, destino=""):
    """Identifica a mesma rota mesmo com pequenas diferenças de digitação."""
    return (HOMOLOGADA, origem) if modalidade == HOMOLOGADA else (NOVA, _norm(origem), _norm(destino))


def chave_de_op(op):
    if op["Destino"] == DESTINO_FIXO:
        return chave_rota(HOMOLOGADA, op["Origem"])
    return chave_rota(NOVA, op["Origem"], op["Destino"])


def chave_de_atalho(a):
    if a["Modalidade"] == HOMOLOGADA:
        return chave_rota(HOMOLOGADA, a["Rota"])
    pontos = json.loads(a["Enderecos"] or "[]")
    if len(pontos) < 2:
        return None
    return chave_rota(NOVA, f"{pontos[0]['rua']} - {pontos[0]['cidade']}",
                      f"{pontos[-1]['rua']} - {pontos[-1]['cidade']}")


def hora_embarque(ida, volta):
    return f"{ida} (Ida) | {volta} (Volta)" if volta else ida


def _horas(hora_embarque_txt):
    if "(Ida)" in hora_embarque_txt:
        ida = hora_embarque_txt.split("(Ida)")[0].strip()
        volta = hora_embarque_txt.split("|")[1].replace("(Volta)", "").strip()
        return ida, volta
    return hora_embarque_txt.strip(), ""


def novo_atalho(nome, modalidade, op, pontos=None, ida_volta=False, agora=None):
    """pontos: [{'rua','cidade','espera'}] da origem ao destino (só para rota nova)."""
    ida, volta = _horas(op["Hora_Embarque"])
    return {
        "ID": f"AT{agora:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}", "Nome": nome, "Modalidade": modalidade,
        "Rota": op["Origem"] if modalidade == HOMOLOGADA else "",
        "Enderecos": json.dumps(pontos or [], ensure_ascii=False), "Ida_Volta": "1" if ida_volta else "",
        "Espera_Min": op.get("Espera_Min", 0), "Hora_Ida": ida, "Hora_Volta": volta,
        "Passageiro": op["Passageiro"], "Solicitante": op["Solicitante"], "Centro_Custo": op["Centro_Custo"],
        "Valor": op["Valor_Total"], "KM": op.get("KM_Total", 0), "Usos": 0, "Ultimo_Uso": "", "Ativo": "1",
    }


def pontos_do_historico(op):
    """Reconstrói origem/paradas/destino de um traslado antigo a partir da coluna Detalhe."""
    linhas = dict()
    paradas = []
    ida_volta = False
    for l in (op.get("Detalhe") or "").split("\n"):
        rot, _, val = l.partition(": ")
        if rot.startswith("Parada"):
            paradas.append(val)
        elif rot == "Retorno":
            ida_volta = True
        elif val:
            linhas[rot] = val
    origem = linhas.get("Embarque") or op["Origem"]
    destino = linhas.get("Destino") or op["Destino"].replace(" (I/V)", "")
    pontos = [{"rua": r, "cidade": c, "espera": 0} for r, c in map(_separar, [origem, *paradas, destino])]
    if paradas and op.get("Espera_Min"):
        pontos[1]["espera"] = float(op["Espera_Min"])
    return pontos, ida_volta or op["Destino"].endswith("(I/V)")


def atalho_do_historico(op, agora):
    if op["Destino"] == DESTINO_FIXO:
        nome = f"{op['Origem'].split('<->')[-1].strip()} · {op['Passageiro']}"
        return novo_atalho(nome, HOMOLOGADA, op, agora=agora)
    pontos, iv = pontos_do_historico(op)
    nome = f"{pontos[0]['rua']} → {pontos[-1]['rua']} · {op['Passageiro']}"
    return novo_atalho(nome, NOVA, op, pontos, iv, agora=agora)


def op_do_atalho(a, data_traslado, agora):
    """Traslado pronto para registrar, com o valor congelado do atalho."""
    hora = hora_embarque(a["Hora_Ida"], a["Hora_Volta"])
    base = {
        "ID": agora.strftime("%Y%m%d%H%M%S"), "Data_Agendamento": agora.strftime("%d/%m/%Y %H:%M"),
        "Data_Traslado": data_traslado.strftime("%d/%m/%Y"), "Hora_Embarque": hora,
        "Passageiro": a["Passageiro"], "Solicitante": a["Solicitante"], "Centro_Custo": a["Centro_Custo"],
        "Valor_Total": float(a["Valor"]), "KM_Total": float(a["KM"] or 0), "Espera_Min": float(a["Espera_Min"] or 0),
        "Status": "Pendente", "Tipo": "Traslado", "Recibo": "",
    }
    if a["Modalidade"] == HOMOLOGADA:
        return {**base, "Origem": a["Rota"], "Destino": DESTINO_FIXO,
                "Detalhe": doc.detalhe_rota(a["Rota"], DESTINO_FIXO, hora)}
    pontos = json.loads(a["Enderecos"])
    enderecos = [f"{p['rua']} - {p['cidade']}" for p in pontos]
    if a["Ida_Volta"]:
        enderecos.append(enderecos[0])
    destino = pontos[-1]
    destino_txt = f"{destino['rua']} - {destino['cidade']}"
    return {**base, "Origem": enderecos[0], "Destino": f"{destino_txt} (I/V)" if a["Ida_Volta"] else destino_txt,
            "Detalhe": doc.detalhe_rota(enderecos[0], enderecos[-1], hora, enderecos)}


def resumo(a):
    hora = hora_embarque(a["Hora_Ida"], a["Hora_Volta"]).replace(" (Ida) | ", " ↔ ").replace(" (Volta)", "")
    if a["Modalidade"] == HOMOLOGADA:
        trajeto = a["Rota"]
    else:
        pontos = json.loads(a["Enderecos"] or "[]")
        trajeto = " → ".join(p["rua"] for p in pontos) + (" → retorno" if a["Ida_Volta"] else "")
    return f"{trajeto} · {hora} · {a['Passageiro']}"


def contar_repeticoes(ops, chave):
    traslados = ops[ops["Tipo"] == "Traslado"]
    return int(sum(1 for _, o in traslados.iterrows() if chave_de_op(o) == chave))


def sugestoes(ops, atalhos, minimo):
    """Rotas que se repetem no histórico e ainda não viraram atalho (mais recentes primeiro)."""
    ja = {chave_de_atalho(a) for _, a in atalhos.iterrows()}
    traslados = ops[ops["Tipo"] == "Traslado"].copy()
    if traslados.empty:
        return []
    traslados["_k"] = traslados.apply(chave_de_op, axis=1)
    traslados["_d"] = pd.to_datetime(traslados["Data_Traslado"], format="%d/%m/%Y", errors="coerce")
    saida = []
    for k, grupo in traslados.groupby("_k", sort=False):
        if k in ja or len(grupo) < minimo:
            continue
        saida.append((len(grupo), grupo.sort_values("_d").iloc[-1].drop(["_k", "_d"]).to_dict()))
    return sorted(saida, key=lambda x: -x[0])


def candidatas_homologacao(ops, hoje, minimo, dias=60):
    """Rotas novas feitas muitas vezes: argumento para propor valor fixo à Sulmed."""
    t = ops[(ops["Tipo"] == "Traslado") & (ops["Destino"] != DESTINO_FIXO)].copy()
    t["_d"] = pd.to_datetime(t["Data_Traslado"], format="%d/%m/%Y", errors="coerce")
    t = t[t["_d"] >= pd.Timestamp(hoje - timedelta(days=dias))]
    if t.empty:
        return []
    t["_k"] = t.apply(chave_de_op, axis=1)
    saida = []
    for _, g in t.groupby("_k"):
        if len(g) >= minimo:
            media = float(g["Valor_Total"].mean())
            ultimo = g.sort_values("_d").iloc[-1]
            saida.append({"rota": f"{ultimo['Origem']} → {ultimo['Destino']}", "viagens": len(g),
                          "media": media, "sugestao": math.ceil(media / 5) * 5})
    return sorted(saida, key=lambda x: -x["viagens"])
