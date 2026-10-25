"""Dias úteis bancários (Porto Alegre/RS) para o prazo de pagamento.

Conta como não útil: sábado, domingo, feriados nacionais, Carnaval (bancos
fechados), Corpus Christi, 20/09 (Revolução Farroupilha, RS) e 02/02
(Navegantes, Porto Alegre).
"""
from datetime import date, timedelta
from functools import lru_cache


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=None)
def feriados(ano):
    p = _pascoa(ano)
    fixos = [(1, 1), (2, 2), (4, 21), (5, 1), (9, 7), (9, 20), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
    moveis = [p - timedelta(days=48), p - timedelta(days=47), p - timedelta(days=2), p + timedelta(days=60)]
    return frozenset([date(ano, m, d) for m, d in fixos] + moveis)


def dia_util(d):
    return d.weekday() < 5 and d not in feriados(d.year)


def somar_dias_uteis(inicio, n):
    """inicio + n dias úteis (o dia de início não conta)."""
    d = inicio
    while n > 0:
        d += timedelta(days=1)
        if dia_util(d):
            n -= 1
    return d


def dias_uteis_entre(inicio, fim):
    """Quantos dias úteis depois de `inicio` até `fim` (inclusive). 0 se fim <= inicio."""
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if dia_util(d):
            n += 1
    return n
