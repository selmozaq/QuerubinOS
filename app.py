import streamlit as st
from groq import Groq

# 1. Configuração da Página
st.set_page_config(page_title="Minha IA - Estilo Gemini", page_icon="✨", layout="centered")

# 2. Estilo Customizado
st.markdown("""
<style>
    .titulo-centralizado {
        text-align: center;
        margin-top: 15vh;
        margin-bottom: 5vh;
        font-weight: 400;
        font-size: 2.5rem;
        font-family: sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# 3. Inicialização e Chave da API
if "GROQ_API_KEY" not in st.secrets:
    st.error("⚠️ Por favor, configure sua GROQ_API_KEY nos Secrets do Streamlit.")
    st.stop()

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# 4. Inicializar o histórico de chat na sessão
if "messages" not in st.session_state:
    st.session_state.messages = []

# 5. Interface Inicial
if not st.session_state.messages:
    st.markdown("<h1 class='titulo-centralizado'>Pode falar, Menezes</h1>", unsafe_allow_html=True)

# 6. Exibir o histórico de mensagens
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==========================================
# MENU ESTILO GEMINI (POPOVER)
# ==========================================
# Cria um container para o menu ficar logo acima da barra de digitação
menu_container = st.container()

with menu_container:
    # Cria o botão "➕" que abre um menu flutuante
    with st.popover("➕ Opções"):
        st.markdown("**Peça ao seu assistente**")
        
        # Opção 1: Enviar Arquivo
        arquivo_enviado = st.file_uploader("📎 Enviar arquivos", type=["txt", "pdf", "csv"])
        if arquivo_enviado:
            st.success(f"Arquivo {arquivo_enviado.name} carregado! (A lógica de leitura precisa ser implementada)")
            
        st.divider()
        
        # Opção 2: Criar Imagem (Botão visual)
        if st.button("🖼️ Criar Imagem (Novo)"):
            st.info("Para gerar imagens, você precisará integrar uma API como DALL-E ou Midjourney.")
            
        # Opção 3: Criar Música (Botão visual)
        if st.button("🎵 Criar música (Novo)"):
            st.info("Para gerar músicas, você precisará integrar uma API de áudio.")

# 7. Campo de entrada do usuário
if prompt := st.chat_input("Peça à sua IA..."):
    # Salva e mostra a mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 8. Chamada para a API da Groq
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # Usando o modelo atualizado escolhido
            stream = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                stream=True,
            )
            
            # Efeito de digitação (streaming)
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
        
        except Exception as e:
            st.error(f"Erro ao conectar com a API da Groq: {e}")
            
    # Salva a resposta do assistente no histórico
    st.session_state.messages.append({"role": "assistant", "content": full_response})
