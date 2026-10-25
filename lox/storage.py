"""Banco de dados do Lox.

Produção: Google Sheets (mesma planilha da v6.1). A aba "Página1" continua com
as 12 colunas originais na mesma ordem; as colunas novas entram à direita. Os
recibos e os atalhos ficam em abas próprias ("Recibos", "Atalhos"), criadas
automaticamente.

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
    "Vencimento", "Lembretes",
]
COLUNAS_ATALHOS = [
    "ID", "Nome", "Modalidade", "Rota", "Enderecos", "Ida_Volta", "Espera_Min",
    "Hora_Ida", "Hora_Volta", "Passageiro", "Solicitante", "Centro_Custo",
    "Valor", "KM", "Usos", "Ultimo_Uso", "Ativo",
]

# tabela -> (aba na planilha, colunas, chave primária)
TABELAS = {
    "ops": ("Página1", COLUNAS_OPS, "ID"),
    "recibos": ("Recibos", COLUNAS_RECIBOS, "Numero"),
    "atalhos": ("Atalhos", COLUNAS_ATALHOS, "ID"),
}
NUMERICAS = {"KM_Total", "Valor_Total", "Espera_Min", "Total", "Valor", "KM", "Usos"}


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


class _Base:
    """Atalhos legíveis usados pelo app."""

    def listar_ops(self):
        return self.listar("ops")

    def listar_recibos(self):
        return self.listar("recibos")

    def listar_atalhos(self):
        df = self.listar("atalhos")
        return df[df["Ativo"] != "0"]

    def adicionar_op(self, dados):
        self.adicionar("ops", dados)

    def adicionar_recibo(self, dados):
        self.adicionar("recibos", dados)

    def adicionar_atalho(self, dados):
        self.adicionar("atalhos", dados)

    def atualizar_ops(self, ids, campos):
        self.atualizar("ops", ids, campos)

    def atualizar_recibo(self, numero, campos):
        self.atualizar("recibos", [numero], campos)

    def atualizar_atalho(self, id_, campos):
        self.atualizar("atalhos", [id_], campos)

    def excluir_recibo(self, numero):
        self.excluir("recibos", numero)


class SheetsStore(_Base):
    modo = "Google Sheets"

    def __init__(self):
        import gspread
        creds = dict(st.secrets["connections"]["gsheets"])
        creds.setdefault("universe_domain", "googleapis.com")
        planilha = gspread.service_account_from_dict(creds).open_by_key(PLANILHA_ID)
        self.abas, self.cab, self._cache = {}, {}, {}
        for tabela, (aba, colunas, _) in TABELAS.items():
            try:
                ws = planilha.worksheet(aba)
            except gspread.WorksheetNotFound:
                ws = planilha.add_worksheet(aba, rows=500, cols=len(colunas))
            self.abas[tabela] = ws
            self.cab[tabela] = self._garantir_cabecalho(ws, colunas)

    @staticmethod
    def _garantir_cabecalho(ws, colunas):
        atual = ws.row_values(1)
        if atual[:len(colunas)] != colunas:
            # só acrescenta o que falta à direita; nunca reordena colunas existentes
            novo = atual + [c for c in colunas if c not in atual]
            if ws.col_count < len(novo):
                ws.add_cols(len(novo) - ws.col_count)
            ws.update([novo], "A1")
            return novo
        return atual

    def listar(self, tabela):
        # o Streamlit reroda o script a cada clique; o cache curto poupa a cota de leitura do Google
        if tabela in self._cache and time.time() - self._cache[tabela][0] < 30:
            return self._cache[tabela][1].copy()
        colunas = TABELAS[tabela][1]
        valores = self.abas[tabela].get_all_values()
        if len(valores) <= 1:
            df = _normalizar(pd.DataFrame(columns=colunas), colunas)
        else:
            cab = valores[0]
            linhas = [l + [""] * (len(cab) - len(l)) for l in valores[1:]]
            df = _normalizar(pd.DataFrame(linhas, columns=cab), colunas)
        self._cache[tabela] = (time.time(), df)
        return df.copy()

    def adicionar(self, tabela, dados):
        self._cache.clear()
        self.abas[tabela].append_row([dados.get(c, "") for c in self.cab[tabela]], value_input_option="RAW")

    def atualizar(self, tabela, chaves, campos):
        import gspread
        self._cache.clear()
        ws, cab, chave = self.abas[tabela], self.cab[tabela], TABELAS[tabela][2]
        chaves = set(chaves)
        celulas = []
        for i, v in enumerate(ws.col_values(cab.index(chave) + 1)[1:], start=2):
            if v in chaves:
                celulas += [gspread.Cell(i, cab.index(c) + 1, val) for c, val in campos.items()]
        if celulas:
            ws.update_cells(celulas, value_input_option="RAW")

    def excluir(self, tabela, valor_chave):
        self._cache.clear()
        ws, cab, chave = self.abas[tabela], self.cab[tabela], TABELAS[tabela][2]
        col = ws.col_values(cab.index(chave) + 1)
        if valor_chave in col:
            ws.delete_rows(col.index(valor_chave) + 1)


class LocalStore(_Base):
    modo = "Local (offline)"

    def __init__(self, caminho=None):
        self.caminho = caminho or os.path.join(os.path.dirname(os.path.dirname(__file__)), "lox_local.db")
        with self._con() as c:
            for tabela, (_, colunas, _) in TABELAS.items():
                c.execute(f"CREATE TABLE IF NOT EXISTS {tabela} ({', '.join(f'{x} TEXT' for x in colunas)})")
                existentes = {r[1] for r in c.execute(f"PRAGMA table_info({tabela})")}
                for x in colunas:
                    if x not in existentes:
                        c.execute(f"ALTER TABLE {tabela} ADD COLUMN {x} TEXT")

    def _con(self):
        return sqlite3.connect(self.caminho)

    def listar(self, tabela):
        with self._con() as c:
            return _normalizar(pd.read_sql(f"SELECT * FROM {tabela}", c), TABELAS[tabela][1])

    def adicionar(self, tabela, dados):
        colunas = TABELAS[tabela][1]
        with self._con() as c:
            c.execute(f"INSERT INTO {tabela} ({','.join(colunas)}) VALUES ({','.join('?' * len(colunas))})",
                      [str(dados.get(x, "")) for x in colunas])

    def atualizar(self, tabela, chaves, campos):
        chave = TABELAS[tabela][2]
        sets = ", ".join(f"{k}=?" for k in campos)
        with self._con() as c:
            for v in chaves:
                c.execute(f"UPDATE {tabela} SET {sets} WHERE {chave}=?", [str(x) for x in campos.values()] + [v])

    def excluir(self, tabela, valor_chave):
        with self._con() as c:
            c.execute(f"DELETE FROM {tabela} WHERE {TABELAS[tabela][2]}=?", (valor_chave,))


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
