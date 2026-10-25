# Lox 7.1 — Portal de Logística Executiva (SylvaCore)

Ciclo completo do contrato Sulmed: **cotação → agendamento → recibo → assinatura gov.br → e-mail → pagamento → lembrete**.

| Módulo | O que faz |
|---|---|
| 📊 Painel | A faturar, a receber, **vencido**, recebido no mês; alerta de recibo fora do prazo com atalho para o lembrete; gráficos; rotas novas candidatas a valor fixo |
| 🚘 Traslados | **Atalhos** de rotas frequentes (homologadas e novas), rota homologada ou nova rota (Nominatim + OSRM), mapa, composição do preço, SLA de 4 h, despacho pelo WhatsApp |
| 📦 Cargas / Entregas | Mesmo motor de rotas; SLA base + taxa de anomalia |
| 🧾 Faturamento | Recibo individual ou consolidado (`NNN-AAAA`), PDF aceito pelo gov.br, **envio automático ao anexar o PDF assinado**, vencimento, baixa de pagamento, **lembretes em 3 níveis com extrato**, cadastro de recibos antigos |
| 📚 Histórico | Filtros, busca e exportação para CSV |
| ⚙️ Configurações | Checklist dos Secrets e e-mail de teste |

A matriz de preço é a mesma da v6.1 (`lox/config.py`).

## Fluxo do dia a dia

1. **Traslados › ⭐ Atalhos › "Registrar e emitir"** — registra o traslado e emite o recibo com o valor congelado do atalho.
   Use **✏️ Editar** para mudar data, horário ou espera antes. Rotas repetidas aparecem como sugestão de atalho.
2. **Faturamento** — baixar o PDF → assinar no gov.br → anexar. Com o envio automático ligado, o Lox confere a
   assinatura e o número do recibo e já manda o e-mail para a Sulmed, com vencimento em 5 dias úteis.
3. Quando o PIX cair: **Marcar como pago**.
4. Se vencer: o Painel avisa e o recibo ganha o passo **5 · Lembrete**. O primeiro é sempre o gentil (nível 1), e
   cada envio libera o próximo nível. O Lox nunca envia lembrete sozinho.

Todo e-mail de recibo novo leva um rodapé com os outros recibos ainda em aberto.

## Prazo de pagamento

- Combinado: 5 dias úteis após o recebimento do recibo por e-mail.
- O prazo começa a contar no envio e pula fins de semana, feriados nacionais, Carnaval, Corpus Christi, 20/09 (RS) e 02/02 (Porto Alegre). O cálculo está em `lox/prazos.py`.
- Lembretes: níveis 1, 2 e 3 a partir de 1, 5 e 10 dias úteis de atraso (`LEMBRETE_NIVEIS`).

## Secrets (Streamlit Cloud › Settings › Secrets)

Os Secrets atuais (`[lox]` e `[connections.gsheets]`) continuam valendo. Acrescente:

```toml
[lox]
recibo_inicial = 14      # continua a sequência das notas já emitidas

[email]
smtp_user = "seu-email@gmail.com"
smtp_pass = "senha-de-app"                 # myaccount.google.com/apppasswords
destino = "email-que-recebe-os-recibos@sulmed.com.br"
cc = "seu-email@gmail.com"                 # cópia para você = arquivo do recibo assinado
contato = "contato-operacional@sulmed.com.br"   # lembrete nível 1
financeiro = "financeiro@sulmed.com.br"         # lembretes níveis 2 e 3
envio_automatico = true
```

O modelo completo está na tela ⚙️ Configurações.

## Banco de dados

- **Google Sheets** (produção): a aba `Página1` mantém as 12 colunas originais e recebe as novas à direita. As abas `Recibos` e `Atalhos` são criadas sozinhas.
- **Local**: sem credenciais, ou com `LOX_OFFLINE=1`, o app usa SQLite (`lox_local.db`). Serve para testar sem mexer na planilha.

**Primeira vez:**
- Operações antigas já cobradas: em 🧾 Faturamento › A faturar, selecione-as e use **"Marcar selecionadas como já faturadas"**.
- Recibos antigos ainda não pagos (ex.: 23/09): em 🧾 Faturamento › Recibos, use **"➕ Cadastrar recibo emitido fora do Lox"**.

## Rodar localmente

```bash
pip install -r requirements.txt
LOX_OFFLINE=1 streamlit run app.py
```
