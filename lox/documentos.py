"""Recibos em PDF compatíveis com o assinador gov.br.

Regras que vieram da v6.1 e continuam valendo: fonte Helvetica nativa (o gov.br
rejeitou o PDF em Courier), texto em preto, arquivo fechado em disco antes de ler.
"""
import os
import tempfile
from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from .config import VALOR_MINUTO_ESPERA

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ---------------------------------------------------------------- texto

def moeda(v):
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_pdf(s):
    """A Helvetica nativa só cobre Latin-1: troca o que estiver fora (setas, travessões)."""
    s = str(s or "")
    for a, b in {"→": "->", "←": "<-", "↔": "<->", "–": "-", "—": "-", "“": '"', "”": '"',
                 "‘": "'", "’": "'", "•": "-", "…": "...", "ẽ": "e", "ĩ": "i", "ũ": "u"}.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


UNID = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
        "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
       "setecentos", "oitocentos", "novecentos"]


def _ate999(n):
    if n == 100:
        return "cem"
    partes = [CEM[n // 100]] if n // 100 else []
    r = n % 100
    if 0 < r < 20:
        partes.append(UNID[r])
    elif r >= 20:
        partes.append(DEZ[r // 10] + (" e " + UNID[r % 10] if r % 10 else ""))
    return " e ".join(partes)


def _inteiro(n):
    if n == 0:
        return "zero"
    mi, mil, resto = n // 1_000_000, (n // 1000) % 1000, n % 1000
    grupos = []
    if mi:
        grupos.append("um milhão" if mi == 1 else _ate999(mi) + " milhões")
    if mil:
        grupos.append("mil" if mil == 1 else _ate999(mil) + " mil")
    if resto:
        grupos.append(_ate999(resto))
    if len(grupos) == 1:
        return grupos[0]
    ultimo = grupos.pop()
    sep = " e " if resto and (resto < 100 or resto % 100 == 0) else " "
    return " ".join(grupos) + sep + ultimo


def por_extenso(valor):
    reais, cent = divmod(round(float(valor or 0) * 100), 100)
    partes = []
    if reais:
        txt = _inteiro(reais) + (" real" if reais == 1 else " reais")
        if reais >= 1_000_000 and reais % 1_000_000 == 0:
            txt = txt.replace(" reais", " de reais")
        partes.append(txt)
    if cent:
        partes.append(_inteiro(cent) + (" centavo" if cent == 1 else " centavos"))
    return " e ".join(partes) or "zero real"


def detalhe_rota(origem, destino, hora_embarque, enderecos=None):
    """Descrição do trajeto que vai no recibo (lógica da v6.1, guardada na coluna Detalhe)."""
    if destino == "Rota Fixa Homologada":
        if "(Ida)" in hora_embarque:
            h_ida = hora_embarque.split("(Ida)")[0].strip()
            h_volta = hora_embarque.split("|")[1].replace("(Volta)", "").strip()
            dest = "Triunfo (Braskem)" if "Braskem" in origem else "Alvorada (Distrito Industrial)"
            return (f"IDA (Saída {h_ida}): Porto Alegre -> {dest}\n"
                    f"VOLTA (Saída {h_volta}): {dest} -> Porto Alegre\n"
                    f"Ref. Rota: {origem} (Ida e Volta)")
        return f"Rota Homologada: {origem}"

    if enderecos and len(enderecos) >= 2:
        linhas = [f"Embarque: {enderecos[0]}"]
        circular = enderecos[-1] == enderecos[0]
        miolo = enderecos[1:-1]
        if circular:
            for i, p in enumerate(miolo[:-1]):
                linhas.append(f"Parada {i + 1}: {p}")
            if miolo:
                linhas.append(f"Destino: {miolo[-1]}")
            linhas.append(f"Retorno: {enderecos[-1]}")
        else:
            for i, p in enumerate(miolo):
                linhas.append(f"Parada {i + 1}: {p}")
            linhas.append(f"Destino: {enderecos[-1]}")
        return "\n".join(linhas)
    return f"Embarque: {origem}\nDestino: {destino}"


# ---------------------------------------------------------------- PDF

class _Recibo(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, texto_pdf(f"Lox | SylvaCore - documento gerado em {datetime.now():%d/%m/%Y %H:%M}"
                                  f" - página {self.page_no()}/{{nb}}"), align="C")


def _linha(pdf, rotulo, valor, w_rot=38):
    pdf.set_font("Helvetica", "B", 9.5)
    w_rot = max(w_rot, pdf.get_string_width(texto_pdf(rotulo)) + 2)
    pdf.cell(w_rot, 5.5, texto_pdf(rotulo))
    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(0, 5.5, texto_pdf(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _titulo_secao(pdf, txt):
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(70, 70, 70)
    pdf.cell(0, 5, texto_pdf(txt.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(160, 160, 160)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1.5)
    pdf.set_text_color(0, 0, 0)


def gerar_recibo_pdf(numero, emissao, ops, prest, tom):
    """ops: lista de dicts com as colunas da aba Página1. Retorna bytes do PDF."""
    total = round(sum(float(o["Valor_Total"] or 0) for o in ops), 2)
    tipos = {o.get("Tipo") or "Traslado" for o in ops}
    if tipos == {"Carga"}:
        servico = "serviços de logística e distribuição de cargas"
    elif tipos == {"Traslado"}:
        servico = "serviços de logística e transporte executivo de pessoal, realizados em veículo particular"
    else:
        servico = "serviços de logística (transporte executivo de pessoal e distribuição de cargas)"

    pdf = _Recibo(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    # Cabeçalho
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(largura * 0.68, 7, texto_pdf("RECIBO DE PRESTAÇÃO DE SERVIÇOS"))
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, texto_pdf(f"Nº {numero}"), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(largura * 0.68, 5, texto_pdf("E REEMBOLSO DE DESPESAS"))
    pdf.cell(0, 5, texto_pdf(f"Emissão: {emissao:%d/%m/%Y}"), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    # Valor em destaque
    pdf.set_fill_color(242, 242, 242)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 11, texto_pdf(f"VALOR: {moeda(total)}"), fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5.6, texto_pdf(
        f"Recebi de {tom['razao']}, inscrita no CNPJ {tom['cnpj']}, a importância de {moeda(total)} "
        f"({por_extenso(total)}), referente a {servico}, conforme detalhamento abaixo."),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    _titulo_secao(pdf, "Tomador do serviço")
    _linha(pdf, "Razão Social:", tom["razao"])
    _linha(pdf, "CNPJ:", tom["cnpj"])

    _titulo_secao(pdf, "Descrição detalhada dos serviços")
    if len(ops) == 1:
        o = ops[0]
        _linha(pdf, "Operação:", f"{o.get('Tipo') or 'Traslado'} - ID {o['ID']}")
        _linha(pdf, "Data:", f"{o['Data_Traslado']} às {o['Hora_Embarque']}" if o["Hora_Embarque"] else o["Data_Traslado"])
        if (o.get("Tipo") or "Traslado") == "Traslado":
            _linha(pdf, "Passageiro(s):", o["Passageiro"])
        else:
            _linha(pdf, "Escopo:", o["Passageiro"])
        _linha(pdf, "Solicitante:", f"{o['Solicitante']} (Centro de Custo: {o['Centro_Custo']})")
        for l in (o.get("Detalhe") or detalhe_rota(o["Origem"], o["Destino"], o["Hora_Embarque"])).split("\n"):
            rot, _, val = l.partition(": ")
            _linha(pdf, rot + ":", val.strip()) if val else _linha(pdf, "", rot)
        if float(o["KM_Total"] or 0):
            _linha(pdf, "Distância:", f"{float(o['KM_Total']):.1f} km")
        espera = float(o.get("Espera_Min") or 0)
        _linha(pdf, "Espera Técnica:", f"{espera:g} minutos (Índice: {moeda(VALOR_MINUTO_ESPERA)}/min | "
                                       f"Subtotal: {moeda(espera * VALOR_MINUTO_ESPERA)})" if espera else "0 minutos")
    else:
        pdf.set_font("Helvetica", "", 8.5)
        with pdf.table(col_widths=(18, 34, 34, 70, 22), text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT"),
                       line_height=4.6, headings_style=FontFace(emphasis="BOLD", fill_color=(235, 235, 235)),
                       borders_layout="HORIZONTAL_LINES") as tab:
            cab = tab.row()
            for h in ("Data", "Passageiro / Escopo", "Solicitante / CC", "Trajeto", "Valor"):
                cab.cell(texto_pdf(h))
            for o in ops:
                r = tab.row()
                r.cell(texto_pdf(o["Data_Traslado"] + (f"\n{o['Hora_Embarque']}" if o["Hora_Embarque"] else "")))
                r.cell(texto_pdf(o["Passageiro"]))
                r.cell(texto_pdf(f"{o['Solicitante']}\n{o['Centro_Custo']}"))
                trajeto = (o.get("Detalhe") or f"{o['Origem']} -> {o['Destino']}").replace("\n", " | ")
                esp = float(o.get("Espera_Min") or 0)
                r.cell(texto_pdf(trajeto + (f" | Espera {esp:g} min" if esp else "")))
                r.cell(texto_pdf(moeda(o["Valor_Total"])))
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, texto_pdf(f"{len(ops)} operações no período de {ops[0]['Data_Traslado']} a {ops[-1]['Data_Traslado']}."),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, texto_pdf(f"VALOR TOTAL PELOS SERVIÇOS PRESTADOS: {moeda(total)}"), border="TB",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(0, 5.5, texto_pdf("Declaro que a quitação se dará mediante o crédito em conta."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    _titulo_secao(pdf, "Dados para pagamento")
    _linha(pdf, "Chave PIX:", prest["pix"])
    _linha(pdf, "Banco:", prest["banco"])
    _linha(pdf, "Favorecido:", prest["nome"])
    _linha(pdf, "CPF:", prest["cpf"])

    # Assinatura: deixa espaço livre para o carimbo do assinador gov.br
    if pdf.get_y() > pdf.h - 75:
        pdf.add_page()
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, texto_pdf(f"{prest['cidade']}, {emissao.day} de {MESES[emissao.month - 1]} de {emissao.year}."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(24)
    x0 = pdf.l_margin + largura * 0.2
    pdf.line(x0, pdf.get_y(), x0 + largura * 0.6, pdf.get_y())
    pdf.ln(1.5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5.5, texto_pdf(prest["nome"].upper()), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, texto_pdf(f"{prest['assinatura']} - CPF {prest['cpf']}"), align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    fd, caminho = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(caminho)
    with open(caminho, "rb") as f:
        dados = f.read()
    os.remove(caminho)
    return dados
