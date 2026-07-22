import streamlit as st
from groq import Groq

# 1. Configuração da Página
st.set_page_config(page_title="Minha IA - Estilo Gemini", page_icon="✨", layout="centered")

# 2. Estilo Customizado (Dark mode é ativado automaticamente pelo Streamlit se o sistema do usuário for escuro)
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

# 3. Inicializar o cliente Groq de forma segura pegando a chave dos Secrets do Streamlit
if "GROQ_API_KEY" not in st.secrets:
    st.error("⚠️ Por favor, configure sua GROQ_API_KEY nos Secrets do Streamlit.")
    st.stop()

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# 4. Inicializar o histórico de chat na sessão
if "messages" not in st.session_state:
    st.session_state.messages = []

# 5. Interface Inicial (Mostra a saudação apenas se não houver mensagens)
if not st.session_state.messages:
    st.markdown("<h1 class='titulo-centralizado'>Vamos lá, Menezes</h1>", unsafe_allow_html=True)

# 6. Exibir o histórico de mensagens
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 7. Campo de entrada do usuário (fica na parte inferior, como num chat real)
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
            # Usando o modelo LLaMA 3 70B da Groq (você pode trocar por 'mixtral-8x7b-32768' se preferir)
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
