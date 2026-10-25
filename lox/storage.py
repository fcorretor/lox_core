"""Banco de dados do Lox.

Produção: Google Sheets (mesma planilha da v6.1). A aba "Página1" continua com
as 12 colunas originais na mesma ordem; as colunas novas entram à direita. Os
recibos ficam numa aba nova, "Recibos", criada automaticamente.

Sem credenciais (ou com LOX_OFFLINE=1): SQLite local, mesma interface.
"""
import os
import sqlite3
import time

import pandas as pd
import streamlit as st

from . import config

PLANILHA_ID = "1rwrlPpSCc89nc12fP26oCNhWUhKtiKVbIOiCbFWqV44"

COLUNAS_OPS = [
    # v6.1 — não mudar a ordem
    "ID", "Data_Agendamento", "Data_Traslado", "Hora_Embarque", "Passageiro",
    "Solicitante", "Centro_Custo", "Origem", "Destino", "KM_Total",
    "Valor_Total", "Status",
    # v7
    "Tipo", "Espera_Min", "Detalhe", "Recibo",
]
COLUNAS_RECIBOS = [
    "Numero", "Emissao", "Operacoes", "Total", "Status",
    "Assinado_Em", "Enviado_Em", "Enviado_Para", "Pago_Em", "Obs",
]
NUMERICAS = {"KM_Total", "Valor_Total", "Espera_Min", "Total"}


def _normalizar(df, colunas):
    for c in colunas:
        if c not in df.columns:
            df[c] = ""
    for c in NUMERICAS & set(colunas):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    df = df[colunas].copy()
    for c in set(colunas) - NUMERICAS:
        df[c] = df[c].fillna("").astype(str)
    if "Tipo" in df.columns:
        df.loc[df["Tipo"] == "", "Tipo"] = "Traslado"
    return df


class SheetsStore:
    modo = "Google Sheets"

    def __init__(self):
        import gspread
        creds = dict(st.secrets["connections"]["gsheets"])
        creds.setdefault("universe_domain", "googleapis.com")
        planilha = gspread.service_account_from_dict(creds).open_by_key(PLANILHA_ID)
        self.ops = planilha.worksheet("Página1")
        try:
            self.recibos = planilha.worksheet("Recibos")
        except gspread.WorksheetNotFound:
            self.recibos = planilha.add_worksheet("Recibos", rows=500, cols=len(COLUNAS_RECIBOS))
        self._garantir_cabecalho(self.ops, COLUNAS_OPS)
        self._garantir_cabecalho(self.recibos, COLUNAS_RECIBOS)

    @staticmethod
    def _garantir_cabecalho(ws, colunas):
        atual = ws.row_values(1)
        if atual[:len(colunas)] != colunas:
            # só acrescenta o que falta à direita; nunca reordena colunas existentes
            novo = atual + [c for c in colunas if c not in atual]
            if ws.col_count < len(novo):
                ws.add_cols(len(novo) - ws.col_count)
            ws.update([novo], "A1")
        ws._lox_cab = ws.row_values(1)

    def _ler(self, ws, colunas):
        # o Streamlit reroda o script a cada clique; o cache curto poupa a cota de leitura do Google
        cache = self.__dict__.setdefault("_cache", {})
        if ws.title in cache and time.time() - cache[ws.title][0] < 30:
            return cache[ws.title][1].copy()
        df = self._ler_planilha(ws, colunas)
        cache[ws.title] = (time.time(), df)
        return df.copy()

    def _invalidar(self):
        self.__dict__.get("_cache", {}).clear()

    @staticmethod
    def _ler_planilha(ws, colunas):
        valores = ws.get_all_values()
        if len(valores) <= 1:
            return _normalizar(pd.DataFrame(columns=colunas), colunas)
        cab = valores[0]
        linhas = [l + [""] * (len(cab) - len(l)) for l in valores[1:]]
        return _normalizar(pd.DataFrame(linhas, columns=cab), colunas)

    @staticmethod
    def _anexar(ws, dados):
        ws.append_row([dados.get(c, "") for c in ws._lox_cab], value_input_option="RAW")

    @staticmethod
    def _atualizar(ws, chave, valores_chave, campos):
        import gspread
        cab = ws._lox_cab
        col_chave = ws.col_values(cab.index(chave) + 1)
        celulas = []
        for i, v in enumerate(col_chave[1:], start=2):
            if v in valores_chave:
                for campo, valor in campos.items():
                    celulas.append(gspread.Cell(i, cab.index(campo) + 1, valor))
        if celulas:
            ws.update_cells(celulas, value_input_option="RAW")

    def listar_ops(self):
        return self._ler(self.ops, COLUNAS_OPS)

    def listar_recibos(self):
        return self._ler(self.recibos, COLUNAS_RECIBOS)

    def adicionar_op(self, dados):
        self._invalidar()
        self._anexar(self.ops, dados)

    def adicionar_recibo(self, dados):
        self._invalidar()
        self._anexar(self.recibos, dados)

    def atualizar_ops(self, ids, campos):
        self._invalidar()
        self._atualizar(self.ops, "ID", set(ids), campos)

    def atualizar_recibo(self, numero, campos):
        self._invalidar()
        self._atualizar(self.recibos, "Numero", {numero}, campos)

    def excluir_recibo(self, numero):
        self._invalidar()
        col = self.recibos.col_values(self.recibos._lox_cab.index("Numero") + 1)
        if numero in col:
            self.recibos.delete_rows(col.index(numero) + 1)


class LocalStore:
    modo = "Local (offline)"

    def __init__(self, caminho=None):
        self.caminho = caminho or os.path.join(os.path.dirname(os.path.dirname(__file__)), "lox_local.db")
        with self._con() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS ops ({', '.join(f'{x} TEXT' for x in COLUNAS_OPS)})")
            c.execute(f"CREATE TABLE IF NOT EXISTS recibos ({', '.join(f'{x} TEXT' for x in COLUNAS_RECIBOS)})")

    def _con(self):
        return sqlite3.connect(self.caminho)

    def _ler(self, tabela, colunas):
        with self._con() as c:
            return _normalizar(pd.read_sql(f"SELECT * FROM {tabela}", c), colunas)

    def _inserir(self, tabela, colunas, dados):
        with self._con() as c:
            c.execute(f"INSERT INTO {tabela} VALUES ({','.join('?' * len(colunas))})",
                      [str(dados.get(x, "")) for x in colunas])

    def _atualizar(self, tabela, chave, valores, campos):
        sets = ", ".join(f"{k}=?" for k in campos)
        with self._con() as c:
            for v in valores:
                c.execute(f"UPDATE {tabela} SET {sets} WHERE {chave}=?", [str(x) for x in campos.values()] + [v])

    def listar_ops(self):
        return self._ler("ops", COLUNAS_OPS)

    def listar_recibos(self):
        return self._ler("recibos", COLUNAS_RECIBOS)

    def adicionar_op(self, dados):
        self._inserir("ops", COLUNAS_OPS, dados)

    def adicionar_recibo(self, dados):
        self._inserir("recibos", COLUNAS_RECIBOS, dados)

    def atualizar_ops(self, ids, campos):
        self._atualizar("ops", "ID", ids, campos)

    def atualizar_recibo(self, numero, campos):
        self._atualizar("recibos", "Numero", [numero], campos)

    def excluir_recibo(self, numero):
        with self._con() as c:
            c.execute("DELETE FROM recibos WHERE Numero=?", (numero,))


@st.cache_resource(show_spinner=False)
def _store_cacheado(modo):
    return SheetsStore() if modo == "sheets" else LocalStore()


def obter_store():
    """Devolve o banco ativo; se o Sheets falhar, cai para o local sem derrubar o app."""
    if os.environ.get("LOX_OFFLINE") != "1" and config.gsheets_configurado():
        try:
            return _store_cacheado("sheets")
        except Exception as e:
            st.sidebar.error(f"Google Sheets indisponível ({e}). Usando banco local.")
    return _store_cacheado("local")


def proximo_numero_recibo(store, ano):
    """Numeração NNN-AAAA, igual às notas já emitidas (ex.: 014-2026)."""
    rec = store.listar_recibos()
    do_ano = [int(n.split("-")[0]) for n in rec["Numero"] if n.endswith(f"-{ano}") and n.split("-")[0].isdigit()]
    inicial = config.prestador()["recibo_inicial"]
    return f"{max(do_ano + [inicial - 1]) + 1:03d}-{ano}"
