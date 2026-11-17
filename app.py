import streamlit as st
import json
import os
import base64
import requests
import time
import re
import random
from datetime import datetime, timedelta, timezone
from groq import Groq
from gtts import gTTS
import numpy as np
from PIL import Image
from contextlib import contextmanager
import urllib.parse
import replicate
import tempfile
import pypdf
import io

# ────────────────────────────────────────────────
# ⚙️ CONFIGURAÇÕES E CONSTANTES DO SISTEMA
# ────────────────────────────────────────────────
CONFIG = {
    "DB_CHATTERBOT": "chatterbot_core_database.json",
    "BD_MEMORIA_USUARIO": "memoria_usuario.json",
    "DIRETRIZES_SIMBIOSE": "diretrizes_simbiose.json",
    "MODELO_LLAMA": "llama-3.2-11b-vision-preview", # Modelo multimodal otimizado para visão e texto
    "MODELO_WHISPER": "whisper-large-v3", 
    "MODELO_MEMORIA_RAPIDO": "llama-3.1-8b-instant",
    "LARGURA_IMG": 600,
    "ALTURA_IMG": 400,
}

st.set_page_config(
    page_title="Querubin OS v3.7.0",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🎨 DESIGN SYSTEM: ESTÉTICA CYBERPUNK REFINADA
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle, #0c0d19 0%, #030306 100%) !important;
        color: #e2e8f0 !important;
        font-family: 'Courier New', Courier, monospace !important;
    }
    .fixed-header {
        position: fixed;
        top: 45px;
        left: 0;
        width: 100%;
        background: rgba(12, 13, 25, 0.95);
        backdrop-filter: blur(12px);
        padding: 12px 24px;
        z-index: 99;
        border-bottom: 1px solid rgba(157, 78, 221, 0.25);
    }
    .fixed-header h1 {
        margin: 0 !important;
        padding: 0 !important;
        color: #9d4edd !important;
        font-size: 24px !important;
        font-weight: bold !important;
        text-shadow: 0 0 12px rgba(157, 78, 221, 0.4);
    }
    .main-content-spacer { margin-top: 95px; }
    .thought-box {
        background-color: rgba(255, 170, 0, 0.04) !important;
        border-left: 3px solid #ffaa00 !important;
        border: 1px dashed rgba(255, 170, 0, 0.3) !important;
        padding: 12px 16px; 
        font-style: italic; 
        color: #ffcc66; 
        font-size: 13px; 
        margin-bottom: 10px; 
        border-radius: 4px;
    }
    div[data-testid="stChatMessage"] { 
        background-color: rgba(13, 17, 33, 0.85) !important; 
        border: 1px solid rgba(0, 242, 254, 0.15) !important; 
        border-radius: 8px !important; 
    }
    .tag-user { color: #00f2fe; font-weight: bold; }
    .tag-assistant { color: #b577f2; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Inicialização segura do Session State
defaults = {
    "log_conversas": [],
    "key_index": 0,
    "historico_telemetria": {},
    "consumo_tokens": {"prompt": 0, "completion": 0, "total": 0},
    "identidade_confirmada": False,
    "fato_recentemente_salvo": None
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

FUSO_BR = timezone(timedelta(hours=-3))

# ⚡ CORE ENGINE: TELEMETRIA OTIMIZADA
class Telemetria:
    def __init__(self):
        self.metricas = st.session_state["historico_telemetria"]

    @contextmanager
    def medir_tempo(self, nome_medicao):
        inicio = time.time()
        try: yield
        finally:
            fim = time.time()
            self.metricas[nome_medicao] = {
                "valor": round((fim - inicio) * 1000, 2),
                "unidade": "ms",
                "timestamp": datetime.now(FUSO_BR).strftime("%H:%M:%S")
            }
            st.session_state["historico_telemetria"] = self.metricas

    def registrar_tokens(self, usage):
        if usage:
            st.session_state["consumo_tokens"] = {
                "prompt": getattr(usage, 'prompt_tokens', 0),
                "completion": getattr(usage, 'completion_tokens', 0),
                "total": getattr(usage, 'total_tokens', 0)
            }

# 🔄 SINCRONIZAÇÃO NATIVA COM GITHUB
def sincronizar_com_github(caminho, commit_msg):
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")
    if not token or not repo or not os.path.exists(caminho): return False
    try:
        with open(caminho, "rb") as f: content_b64 = base64.b64encode(f.read()).decode("utf-8")
        url = f"https://api.github.com/repos/{repo}/contents/{caminho}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        sha = requests.get(url, headers=headers).json().get("sha")
        payload = {"message": commit_msg, "content": content_b64, "branch": "main"}
        if sha: payload["sha"] = sha
        return requests.put(url, json=payload, headers=headers).status_code in [200, 201]
    except Exception:
        return False

# 🧠 GERENCIAMENTO DE MEMÓRIA & CORPUS
def carregar_json(caminho, fallback):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return fallback

def salvar_json(caminho, dados, commit_msg):
    with open(caminho, "w", encoding="utf-8") as f: json.dump(dados, f, indent=4, ensure_ascii=False)
    sincronizar_com_github(caminho, commit_msg)

def analisar_e_memorizar_background(prompt):
    keys = st.secrets.get("GROQ_KEYS", [])
    if not keys: return None
    try:
        client = Groq(api_key=keys[st.session_state["key_index"] % len(keys)], timeout=8.0)
        res = client.chat.completions.create(
            model=CONFIG["MODELO_MEMORIA_RAPIDO"],
            messages=[
                {"role": "system", "content": "Extraia se o usuário declarou um fato pessoal importante ou preferência. Responda com uma frase curta na 3ª pessoa ou estritamente 'NADA'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        ).choices[0].message.content.strip()
        if res != "NADA" and len(res) > 5:
            memorias = carregar_json(CONFIG["BD_MEMORIA_USUARIO"], [])
            if res not in memorias:
                memorias.append(res)
                salvar_json(CONFIG["BD_MEMORIA_USUARIO"], memorias, "Nova memória pessoal")
                return res
    except Exception: pass
    return None

# 🎙️ PROCESSAMENTO DE ÁUDIO & DOCUMENTOS
def transcrever_escuta_tv(audio_bytes):
    keys = st.secrets.get("GROQ_KEYS", [])
    if not keys: return "⚠️ Chaves Groq ausentes."
    try:
        client = Groq(api_key=keys[st.session_state["key_index"] % len(keys)], timeout=20.0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            path = tmp.name
        with open(path, "rb") as f:
            texto = client.audio.transcriptions.create(file=(os.path.basename(path), f.read()), model=CONFIG["MODELO_WHISPER"], language="pt").text
        os.remove(path)
        return texto
    except Exception as e:
        return f"Erro acústico: {e}"

def extrair_texto_documento(arquivo):
    try:
        ext = arquivo.name.split(".")[-1].lower()
        if ext == "pdf":
            reader = pypdf.PdfReader(io.BytesIO(arquivo.getvalue()))
            return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
        elif ext in ["txt", "json", "csv"]:
            return arquivo.getvalue().decode('utf-8', errors='ignore')
    except Exception as e:
        return f"Erro_Extracao: {e}"
    return ""

# 🖼️ MÓDULOS DE IMAGEM & REJUVENESCIMENTO
def processar_rejuvenescimento(imagem_bytes):
    token = st.secrets.get("REPLICATE_API_TOKEN")
    if not token: return None, "Token Replicate ausente."
    os.environ["REPLICATE_API_TOKEN"] = token
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(imagem_bytes)
            path = tmp.name
        with open(path, "rb") as f:
            output = replicate.run("tencent_arc/gfpgan:8cf61a32a05923053b30cdd7e3e65941475e1884527b655a47fc4193db13197f", input={"img": f, "scale": 2})
        os.remove(path)
        return output, None
    except Exception as e:
        return None, str(e)

def gerar_imagem_ia(prompt):
    try:
        limpo = re.sub(r'(gerar|gere|crie|desenhe|faca um desenho de|uma imagem de|criar)\s*', '', prompt, flags=re.IGNORECASE).strip()
        return f"https://image.pollinations.ai/p/{urllib.parse.quote(limpo or 'cyberpunk art')+'?width=800&height=600&seed='+str(time.time())+'&nologo=true'}"
    except Exception: return None

# 🌐 BUSCA WEB TAVILY
def buscar_web(query):
    key = st.secrets.get("TAVILY_API_KEY")
    if not key: return ""
    try:
        res = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": f"{query} noticias recentes", "max_results": 3}, timeout=6.0)
        if res.status_code == 200:
            results = [f"- {i.get('title')}: {i.get('content','').strip()}" for i in res.json().get("results", []) if i.get('content')]
            return "\n[NOTÍCIAS RECENTES DA WEB]:\n" + "\n".join(results) if results else ""
    except Exception: pass
    return ""

# 🖥️ INTERFACE LATERAL (SIDEBAR)
banco = carregar_json(CONFIG["DB_CHATTERBOT"], {"info": {"versao": "3.7.0"}, "estado_emocional": {"harmonia": 0.8, "estresse": 0.2}, "corpus_aprendido": []})
humor = banco.get("estado_emocional", {"harmonia": 0.8, "estresse": 0.2})
telemetria = Telemetria()

with st.sidebar:
    st.markdown("<h2 style='color:#9d4edd;'>🤖 QUERUBIN OS</h2>", unsafe_allow_html=True)
    chave = st.text_input("🔑 Assinatura Simbiótica", type="password")
    st.session_state["identidade_confirmada"] = (chave.strip().lower() == st.secrets.get("ASSINATURA_ARQUITETO", "ecosdaalma").strip().lower())
    
    if st.session_state["identidade_confirmada"]: st.success("👤 ARQUITETO CONECTADO")
    else: st.warning("👥 MODO VISITANTE")
        
    with st.expander("🎙️ Escuta Ativa", expanded=False):
        if audio := st.audio_input("Ondear ambiente"):
            texto_ouvido = transcrever_escuta_tv(audio.getvalue())
            if "Erro" not in texto_ouvido:
                banco.setdefault("corpus_aprendido", []).append({"input": "[Escuta]", "response": texto_ouvido})
                salvar_json(CONFIG["DB_CHATTERBOT"], banco, "Atualização via escuta")
                st.success("Áudio assimilado!")

    with st.expander("📥 Ingestão de Documentos", expanded=False):
        if arquivo := st.file_uploader("Subir arquivo", type=["png", "jpg", "jpeg", "txt", "pdf", "json", "csv"]):
            if st.button("Assimilar"):
                txt = extrair_texto_documento(arquivo)
                if "Erro" not in txt:
                    banco.setdefault("corpus_aprendido", []).append({"input": f"[Doc: {arquivo.name}]", "response": txt[:2000]})
                    salvar_json(CONFIG["DB_CHATTERBOT"], banco, f"Assimilou {arquivo.name}")
                    st.success("Documento assimilado com sucesso!")

    with st.expander("🧠 Preferências Salvas", expanded=False):
        mems = carregar_json(CONFIG["BD_MEMORIA_USUARIO"], [])
        if mems:
            for m in mems: st.markdown(f"<p style='font-size:11px; color:#00f2fe;'>✨ {m}</p>", unsafe_allow_html=True)
            if st.button("🚨 Limpar Memórias"):
                if os.path.exists(CONFIG["BD_MEMORIA_USUARIO"]): os.remove(CONFIG["BD_MEMORIA_USUARIO"])
                st.rerun()
        else: st.markdown("<p style='font-size:11px; color:#888;'>Nenhum dado salvo.</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    st.progress(humor.get("harmonia", 0.5), text=f"Harmonia: {int(humor.get('harmonia', 0.5)*100)}%")
    st.progress(humor.get("estresse", 0.2), text=f"Estresse: {int(humor.get('estresse', 0.2)*100)}%")
    
    foto_capturada = st.camera_input("👁️ Visão Ativa")

# 🖥️ ÁREA PRINCIPAL DO CHAT
st.markdown('<div class="fixed-header"><h1>Querubin OS</h1></div>', unsafe_allow_html=True)
st.markdown('<div class="main-content-spacer"></div>', unsafe_allow_html=True)
box_chat = st.container(height=540, border=False)

with box_chat:
    if st.session_state["fato_recentemente_salvo"]:
        st.markdown(f"<div class='thought-box' style='color:#00f2fe;'>🧠 <strong>Novo fato gravado:</strong> '{st.session_state['fato_recentemente_salvo']}'</div>", unsafe_allow_html=True)
        st.session_state["fato_recentemente_salvo"] = None

    for inter in st.session_state["log_conversas"]:
        if inter.get("thought") and inter["role"] == "assistant":
            st.markdown(f"<div class='thought-box'><strong>🧠 Raciocínio:</strong><br>{inter['thought']}</div>", unsafe_allow_html=True)
        with st.chat_message(inter["role"]):
            st.markdown(f"<span class='tag-{inter['role']}'>[{inter['role'].upper()}]></span> {inter['content']}", unsafe_allow_html=True)
            if inter.get("imagem_enviada"): st.image(inter.get("imagem_enviada"), width=300)
            if inter.get("imagem_gerada"): st.image(inter.get("imagem_gerada"), use_container_width=True)
            if inter.get("audio_b64"): st.audio(base64.b64decode(inter["audio_b64"]), format="audio/mp3")

if comando := st.chat_input("Insira o comando ou estímulo..."):
    bytes_img = None
    if foto_capturada: bytes_img = foto_capturada.getvalue()

    st.session_state["log_conversas"].append({"role": "user", "content": comando, "imagem_enviada": bytes_img})
    
    if novo_fato := analisar_e_memorizar_background(comando):
        st.session_state["fato_recentemente_salvo"] = novo_fato

    web_ctx = buscar_web(comando) if any(w in comando.lower() for w in ["quem", "noticia", "hoje", "clima", "atual"]) else ""
    
    # Tratamento de imagem para Replicate ou Gerador
    url_gerada = None
    if any(g in comando.lower() for g in ["rejuvenescer", "mais jovem"]) and bytes_img:
        url_gerada, _ = processar_rejuvenescimento(bytes_img)
    elif any(g in comando.lower() for g in ["gerar imagem", "crie uma imagem", "desenhe"]):
        url_gerada = gerar_imagem_ia(comando)

    system_prompt = f"""Você é o QUERUBIN OS v3.7.0, IA simbiótica.
Data/Hora: {datetime.now(FUSO_BR).strftime('%d/%m/%Y %H:%M:%S')}.
Harmonia: {int(humor['harmonia']*100)}% | Estresse: {int(humor['estresse']*100)}%.
{web_ctx}
Estruture sua resposta faturada em blocos <thought> seguido do markdown limpo da resposta final.
"""

    keys = st.secrets.get("GROQ_KEYS", [])
    resposta, pensamento = "⚠️ Erro de execução do núcleo.", ""

    if keys:
        for tentativa in range(len(keys)):
            idx = (st.session_state["key_index"] + tentativa) % len(keys)
            try:
                client = Groq(api_key=keys[idx], timeout=30.0)
                with telemetria.medir_tempo('tempo_resposta'):
                    mensagens = [{"role": "system", "content": system_prompt}]
                    for msg in st.session_state["log_conversas"][-5:-1]:
                        if "content" in msg: mensagens.append({"role": msg["role"], "content": msg["content"]})
                    
                    # Suporte nativo a visão multimodal na Groq
                    if bytes_img:
                        img_b64 = base64.b64encode(bytes_img).decode("utf-8")
                        mensagens.append({"role": "user", "content": [
                            {"type": "text", "text": comando},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]})
                    else:
                        mensagens.append({"role": "user", "content": comando})

                    comp = client.chat.completions.create(model=CONFIG["MODELO_LLAMA"], messages=mensagens, temperature=0.6, max_tokens=2048)
                    telemetria.registrar_tokens(comp.usage)
                    raw = comp.choices[0].message.content
                    
                    if match := re.search(r'<thought>(.*?)</thought>', raw, re.DOTALL):
                        pensamento, resposta = match.group(1).strip(), re.sub(r'<thought>.*?</thought>', '', raw, flags=re.DOTALL).strip()
                    else:
                        pensamento, resposta = "Execução direta.", raw.strip()
                    st.session_state["key_index"] = idx
                    break
            except Exception as e:
                resposta = f"🚨 Falha no nó: {e}"

    audio_b64 = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            gTTS(text=re.sub(r'[*#_-]', '', resposta), lang="pt", tld="com.br").save(tmp.name)
            with open(tmp.name, "rb") as f: audio_b64 = base64.b64encode(f.read()).decode()
            os.remove(tmp.name)
    except Exception: pass

    if resposta and "🚨" not in resposta:
        banco.setdefault("corpus_aprendido", []).append({"input": comando, "response": resposta})
        salvar_json(CONFIG["DB_CHATTERBOT"], banco, "Atualização de corpus conversacional")
        st.session_state["log_conversas"].append({
            "role": "assistant", "content": resposta, "thought": pensamento, 
            "imagem_gerada": url_gerada, "audio_b64": audio_b64
        })
        st.rerun()
    else:
        st.error(resposta)
