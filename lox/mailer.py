"""Envio do recibo assinado por e-mail (SMTP com TLS)."""
import smtplib
import ssl
from email.message import EmailMessage


def _lista(txt):
    return [e.strip() for e in (txt or "").replace(";", ",").split(",") if e.strip()]


def enviar(cfg, para, cc, assunto, corpo, anexo_bytes, anexo_nome):
    """Envia e devolve a lista de destinatários. Lança exceção com a mensagem do servidor se falhar."""
    if not (cfg["usuario"] and cfg["senha"]):
        raise RuntimeError("Remetente SMTP não configurado nos Secrets ([email] smtp_user / smtp_pass).")
    destinos, copias = _lista(para), _lista(cc)
    if not destinos:
        raise RuntimeError("Informe ao menos um e-mail de destino.")

    msg = EmailMessage()
    msg["From"] = cfg["usuario"]
    msg["To"] = ", ".join(destinos)
    if copias:
        msg["Cc"] = ", ".join(copias)
    msg["Subject"] = assunto
    msg.set_content(corpo)
    msg.add_attachment(anexo_bytes, maintype="application", subtype="pdf", filename=anexo_nome)

    ctx = ssl.create_default_context()
    if cfg["porta"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], 465, context=ctx, timeout=30) as s:
            s.login(cfg["usuario"], cfg["senha"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["porta"], timeout=30) as s:
            s.starttls(context=ctx)
            s.login(cfg["usuario"], cfg["senha"])
            s.send_message(msg)
    return destinos + copias
