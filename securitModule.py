import streamlit as st

# ==========================================
# LOX - SISTEMA DE LOGÍSTICA EXECUTIVA B2B
# ==========================================
# Lógica: Controle de acesso usando Streamlit Session State.
# Impede curiosos e concorrência de verem tua métrica de preço.

# 1. Configuração da Página Web
st.set_page_config(page_title="Lox | Portal Corporativo", page_icon="🔒")

# 2. Banco de Credenciais Hardcoded (Solução rápida e segura para o MVP)
CREDENCIAIS = {
    "sulmed": "lox2026",  # Login exclusivo da Sulmed
    "admin": "tiesco_boss" # Teu login de mestre para testes
}

def tela_login():
    """Renderiza a interface de autenticação."""
    st.title("🔒 Lox")
    st.markdown("**Portal Corporativo de Logística Executiva**")
    st.markdown("Acesso restrito. Insira suas credenciais.")
    
    usuario = st.text_input("Usuário (Login)")
    senha = st.text_input("Senha", type="password")
    
    if st.button("Autenticar"):
        # Tratamento de exceção visual: Verifica se a chave existe e a senha confere
        if usuario in CREDENCIAIS and CREDENCIAIS[usuario] == senha:
            st.session_state["autenticado"] = True
            st.session_state["cliente"] = usuario
            st.rerun() # Atualiza a página instantaneamente, derrubando a parede
        else:
            st.error("Credenciais inválidas. Acesso negado.")

def tela_principal():
    """Renderiza o motor de cotação (Onde o dinheiro é feito)."""
    # Cabeçalho pós-login
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.success(f"Logado como: {st.session_state['cliente'].upper()}")
    with col2:
        if st.button("Sair"):
            st.session_state["autenticado"] = False
            st.rerun()

    st.title("Motor de Cotação Lox 🚘")
    st.markdown("---")
    
    # Aqui vamos plugar o Motor OSRM de GPS que fizemos na etapa anterior!
    st.info("Interface de Cotação de Rotas Carregando...")

# ==========================================
# MÁQUINA DE ESTADO DO SISTEMA
# ==========================================
# Inicia a variável se for o primeiro acesso da pessoa
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

# Roteador de Telas: Manda pra rua ou deixa entrar
if not st.session_state["autenticado"]:
    tela_login()
else:
    tela_principal()