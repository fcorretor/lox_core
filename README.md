# Lox 7.0 — Portal de Logística Executiva (SylvaCore)

Ciclo completo do contrato Sulmed: **cotação → agendamento → recibo → assinatura gov.br → e-mail → pagamento**.

| Módulo | O que faz |
|---|---|
| 📊 Painel | A faturar, a receber, recebido no mês, gráficos por mês e centro de custo, recibos em aberto com dias desde a emissão |
| 🚘 Traslados | Rota homologada (valor fixo) ou nova rota (Nominatim + OSRM), mapa do trajeto, composição do preço, alerta do SLA de 4 h, despacho pelo WhatsApp |
| 📦 Cargas / Entregas | Mesmo motor de rotas; SLA base + taxa de anomalia |
| 🧾 Faturamento | Recibo individual ou consolidado (numeração `NNN-AAAA`), PDF aceito pelo gov.br, anexar o PDF assinado, envio por e-mail com anexo, baixa de pagamento |
| 📚 Histórico | Filtros, busca e exportação para CSV |
| ⚙️ Configurações | Checklist dos Secrets e e-mail de teste |

A matriz de preço é a mesma da v6.1 (`lox/config.py`).

## Secrets (Streamlit Cloud › Settings › Secrets)

Os Secrets atuais (`[lox]` e `[connections.gsheets]`) continuam valendo. Para o e-mail funcionar, acrescente:

```toml
[lox]
recibo_inicial = 14      # continua a sequência das notas já emitidas

[email]
smtp_user = "seu-email@gmail.com"
smtp_pass = "senha-de-app"            # myaccount.google.com/apppasswords
destino = "financeiro@sulmed.com.br"
cc = "seu-email@gmail.com"            # cópia para você = arquivo do recibo assinado
```

O modelo completo está na tela ⚙️ Configurações.

## Banco de dados

- **Google Sheets** (produção): a aba `Página1` mantém as 12 colunas originais. As colunas `Tipo`, `Espera_Min`, `Detalhe` e `Recibo` entram à direita. A aba `Recibos` é criada sozinha.
- **Local**: sem credenciais, ou com `LOX_OFFLINE=1`, o app usa SQLite (`lox_local.db`). Serve para testar sem mexer na planilha.

Operações antigas que já foram cobradas fora do Lox: em 🧾 Faturamento › A faturar, selecione-as e use **"Marcar selecionadas como já faturadas"**.

## Rodar localmente

```bash
pip install -r requirements.txt
LOX_OFFLINE=1 streamlit run app.py
```
