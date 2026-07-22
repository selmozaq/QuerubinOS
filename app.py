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
import streamlit.components.v1 as components
import replicate
import tempfile
import pypdf
import io

# ────────────────────────────────────────────────
# ⚙️ CONFIGURAÇÕES E CONSTANTES
# ────────────────────────────────────────────────
CONFIG = {
    "DB_CHATTERBOT": "chatterbot_core_database.json",
    "BD_MEMORIA_USUARIO": "memoria_usuario.json",
    "DIRETRIZES_SIMBIOSE": "diretrizes_simbiose.json",
    "MODELO_LLAMA": "llama-3.3-70b-versatile",
    "MODELO_VISION": "meta-llama/llama-4-scout-17b-16e-instruct",
    "MODELO_WHISPER": "whisper-large-v3", 
    "MODELO_MEMORIA_RAPIDO": "llama-3.1-8b-instant",
    "LARGURA_IMG": 600,
    "ALTURA_IMG": 400,
    "COR_HARMONIA_BASE": (0, 0, 128),
    "COR_HARMONIA_DEST": (0, 255, 255),
    "COR_HARMONIA_SEC": (138, 43, 226),
    "COR_ESTRESSE_BASE": (139, 0, 0),
    "COR_ESTRESSE_DEST": (255, 165, 0),
    "COR_ESTRESSE_SEC": (255, 215, 0)
}

st.set_page_config(
    page_title="Querubin OS v3.5.0",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🎨 CSS PERSONALIZADO (PRESERVA A ESTÉTICA CYBERPUNK)
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
        backdrop-filter: blur(10px);
        padding: 10px 20px;
        z-index: 99;
        border-bottom: 1px solid rgba(157, 78, 221, 0.2);
    }
    .fixed-header h1 {
        margin: 0 !important;
        padding: 0 !important;
        color: #9d4edd !important;
        font-size: 26px !important;
        font-weight: bold !important;
        text-shadow: 0 0 10px rgba(157, 78, 221, 0.4);
    }
    .main-content-spacer { margin-top: 105px; }
    .thought-box {
        background-color: rgba(255, 170, 0, 0.03) !important;
        border: 1px dashed rgba(255, 170, 0, 0.3) !important;
        padding: 14px; font-style: italic; color: #ffaa00; font-size: 13.5px; margin-bottom: 12px; border-radius: 6px;
    }
    div[data-testid="stChatMessage"] { background-color: rgba(13, 17, 33, 0.8) !important; border: 1px solid rgba(0, 242, 254, 0.1) !important; border-radius: 8px !important; }
    .tag-user { color: #00f2fe; font-weight: bold; }
    .tag-assistant { color: #b577f2; font-weight: bold; }
    .telemetria-label { font-size: 13px; font-weight: bold; color: #9d4edd; margin-bottom: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "log_conversas" not in st.session_state: st.session_state["log_conversas"] = []
if "key_index" not in st.session_state: st.session_state["key_index"] = 0
if "historico_telemetria" not in st.session_state: st.session_state["historico_telemetria"] = {}
if "consumo_tokens" not in st.session_state: st.session_state["consumo_tokens"] = {"prompt": 0, "completion": 0, "total": 0}
if "memorias_resgatadas" not in st.session_state: st.session_state["memorias_resgatadas"] = []
if "ultima_busca_web" not in st.session_state: st.session_state["ultima_busca_web"] = "Nenhuma busca realizada nesta sessão."
if "identidade_confirmada" not in st.session_state: st.session_state["identidade_confirmada"] = False
if "fato_recentemente_salvo" not in st.session_state: st.session_state["fato_recentemente_salvo"] = None

FUSO_BR = timezone(timedelta(hours=-3))

# ⚡ CORE ENGINE: TELEMETRIA
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
                "timestamp": datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state["historico_telemetria"] = self.metricas

    def registrar_tokens(self, usage_objeto):
        if usage_objeto:
            st.session_state["consumo_tokens"] = {
                "prompt": getattr(usage_objeto, 'prompt_tokens', 0),
                "completion": getattr(usage_objeto, 'completion_tokens', 0),
                "total": getattr(usage_objeto, 'total_tokens', 0)
            }

# 🧠 SISTEMA DE MEMÓRIA DE LONGO PRAZO
def carregar_memorias_pessoais():
    if os.path.exists(CONFIG["BD_MEMORIA_USUARIO"]):
        try:
            with open(CONFIG["BD_MEMORIA_USUARIO"], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def salvar_memoria_pessoal(fato_novo):
    memorias = carregar_memorias_pessoais()
    if fato_novo not in memorias:
        memorias.append(fato_novo)
        with open(CONFIG["BD_MEMORIA_USUARIO"], "w", encoding="utf-8") as f:
            json.dump(memorias, f, ensure_ascii=False, indent=4)
        return True
    return False

def apagar_memorias_pessoais():
    if os.path.exists(CONFIG["BD_MEMORIA_USUARIO"]):
        try:
            os.remove(CONFIG["BD_MEMORIA_USUARIO"])
        except Exception:
            pass

def analisar_e_memorizar_background(prompt_usuario):
    keys_list = st.secrets.get("GROQ_KEYS", [])
    if not keys_list:
        return None
        
    instrucao_extracao = (
        "Você é o módulo cortical de memória do Querubin OS. Analise a mensagem do usuário e determine "
        "se ele está declarando um fato pessoal importante, preferência de desenvolvimento ou regra de comportamento.\n"
        "Se sim, sintetize em uma frase curta na terceira pessoa. Se não, responda estritamente 'NADA'."
    )
    
    idx = st.session_state["key_index"] % len(keys_list)
    try:
        cliente_groq_fast = Groq(api_key=keys_list[idx], timeout=10.0)
        resposta = cliente_groq_fast.chat.completions.create(
            model=CONFIG["MODELO_MEMORIA_RAPIDO"],
            messages=[
                {"role": "system", "content": instrucao_extracao},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=0.0
        )
        resultado = resposta.choices[0].message.content.strip()
        if resultado != "NADA" and len(resultado) > 5:
            if salvar_memoria_pessoal(resultado):
                return resultado
    except Exception:
        pass
    return None

# 🎙️ MOTOR DE AUDIÇÃO DE TV
def transcrever_escuta_tv(audio_bytes):
    keys_list = st.secrets.get("GROQ_KEYS", [])
    if not keys_list:
        return "⚠️ Erro: Chaves Groq ausentes."
    
    idx = st.session_state["key_index"] % len(keys_list)
    try:
        cliente_groq = Groq(api_key=keys_list[idx], timeout=30.0)
    except Exception as e:
        return f"Erro na inicialização do Groq: {e}"
    
    nome_arquivo_temp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            nome_arquivo_temp = tmp_file.name
            
        with open(nome_arquivo_temp, "rb") as f_audio:
            transcricao = cliente_groq.audio.transcriptions.create(
                file=(os.path.basename(nome_arquivo_temp), f_audio.read()),
                model=CONFIG["MODELO_WHISPER"],
                response_format="json",
                language="pt"
            )
        return transcricao.text
    except Exception as e:
        return f"Erro de decodificação acústica: {str(e)}"
    finally:
        if nome_arquivo_temp and os.path.exists(nome_arquivo_temp):
            try: os.remove(nome_arquivo_temp)
            except Exception: pass

def processar_aprendizado_tv(texto, banco):
    if not texto or len(texto.strip()) < 5:
        return False, "Dados insuficientes ou ruído de fundo."
        
    if "corpus_aprendido" not in banco:
        banco["corpus_aprendido"] = []
        
    agora = datetime.now(FUSO_BR)
    banco["corpus_aprendido"].append({
        "input": f"[Escuta TV - {agora.strftime('%H:%M')}]",
        "response": texto.strip(),
        "timestamp": agora.isoformat()
    })
    salvar_banco_nuvem(banco)
    return True, "Ondas de rádio mapeadas e injetadas no Chatterbot!"

# 📚 MOTOR DE INGESTÃO DE DOCUMENTOS
def extrair_texto_documento(arquivo_carregado):
    texto_extraido = ""
    extensao = arquivo_carregado.name.split(".")[-1].lower()
    
    try:
        if extensao == "pdf":
            pdf_reader = pypdf.PdfReader(io.BytesIO(arquivo_carregado.getvalue()))
            for page in pdf_reader.pages:
                texto = page.extract_text()
                if texto: 
                    texto_extraido += texto + " "
        elif extensao in ["txt", "json", "csv"]:
            texto_extraido = arquivo_carregado.getvalue().decode('utf-8', errors='ignore')
        
        return re.sub(r'\s+', ' ', texto_extraido).strip()
    except Exception as e:
        return f"Erro_Extracao: {str(e)}"

def destilar_e_aprender_documento(nome_arquivo, texto_bruto, banco):
    if not texto_bruto or len(texto_bruto) < 20:
        return False, "O documento está vazio ou é ilegível."
        
    texto_para_leitura = texto_bruto[:25000] 
    keys_list = st.secrets.get("GROQ_KEYS", [])
    if not keys_list: 
        return False, "Falha no Groq: Chaves de API ausentes."
        
    prompt_assimilacao = f"Analise, resuma e extraia as diretrizes e conceitos cruciais do texto do arquivo '{nome_arquivo}':\n\n{texto_para_leitura}"

    for tentativa in range(len(keys_list)):
        idx = (st.session_state["key_index"] + tentativa) % len(keys_list)
        try:
            cliente_groq = Groq(api_key=keys_list[idx], timeout=25.0)
            completion = cliente_groq.chat.completions.create(
                model=CONFIG["MODELO_LLAMA"], 
                messages=[{"role": "user", "content": prompt_assimilacao}],
                temperature=0.3,
                max_tokens=1024
            )
            conhecimento_destilado = completion.choices[0].message.content
            
            if "corpus_aprendido" not in banco:
                banco["corpus_aprendido"] = []
                
            banco["corpus_aprendido"].append({
                "input": f"[Documento Assimilado: {nome_arquivo}]",
                "response": conhecimento_destilado.strip()
            })
            salvar_banco_nuvem(banco)
            st.session_state["key_index"] = idx
            return True, "Documento assimilado com sucesso!"
        except Exception:
            continue
            
    return False, "Esgotadas todas as rotas e chaves de processamento."

# 🔬 REJUVENESCIMENTO (REPLICATE)
def verificar_pedido_rejuvenescimento(texto_usuario):
    gatilhos = ["rejuvenescer", "mais jovem", "30 anos a menos", "rejuvenescida", "rejuvenesece"]
    return any(g in texto_usuario.lower() for g in gatilhos)

def processar_rejuvenescimento_replicate(imagem_bytes):
    caminho_temporario = None
    try:
        token = st.secrets.get("REPLICATE_API_TOKEN")
        if not token:
            return None, "⚠️ Replicate abortado: 'REPLICATE_API_TOKEN' não configurada."
        
        os.environ["REPLICATE_API_TOKEN"] = token
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            tmp_file.write(imagem_bytes)
            caminho_temporario = tmp_file.name
            
        with open(caminho_temporario, "rb") as imagem_arquivo:
            output = replicate.run(
                "tencent_arc/gfpgan:8cf61a32a05923053b30cdd7e3e65941475e1884527b655a47fc4193db13197f",
                input={"img": imagem_arquivo, "scale": 2, "version": "v1.4"}
            )
        return output, None
    except Exception as e:
        return None, str(e)
    finally:
        if caminho_temporario and os.path.exists(caminho_temporario):
            try: os.remove(caminho_temporario)
            except Exception: pass

# 🖼️ GERADOR DE IMAGENS
def verificar_pedido_imagem(texto_usuario):
    gatilhos = ["gerar imagem", "gere uma imagem", "crie uma imagem", "desenhe", "desenha", "faca um desenho", "criar imagem", "gerar foto"]
    return any(g in texto_usuario.lower() for g in gatilhos)

def generar_imagem_ia(prompt_usuario):
    try:
        prompt_limpo = re.sub(r'(gerar|gere|crie|desenhe|faca um desenho de|uma imagem de|criar|uma foto de)\s*', '', prompt_usuario, flags=re.IGNORECASE).strip()
        if not prompt_limpo: 
            prompt_limpo = "cyberpunk digital art portrait"
        prompt_encodado = urllib.parse.quote(prompt_limpo)
        return f"https://image.pollinations.ai/p/{prompt_encodado}?width=800&height=600&seed={int(time.time())}&nologo=true"
    except Exception as e: 
        return None

# 🌐 TAVILY WEB SEARCH
def executar_busca_web_tavily(query, limite=4):
    try:
        tavily_key = st.secrets.get("TAVILY_API_KEY")
        if not tavily_key:
            st.session_state["ultima_busca_web"] = "⚠️ Tavily: Chave ausente."
            return ""
        
        resposta = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": f"{query} noticias recentes", "search_depth": "advanced", "max_results": limite},
            headers={"Content-Type": "application/json"},
            timeout=8.0
        )
        
        if resposta.status_code == 200:
            resultados = [f"MANCHETE: {i.get('title')} | DETALHE: {i.get('content','').strip()}" for i in resposta.json().get("results", []) if i.get('content')]
            if resultados:
                st.session_state["ultima_busca_web"] = f"Busca realizada: {len(resultados)} fatos."
                return "\n[NOTÍCIAS DA WEB]:\n" + "\n".join([f"- {r}" for r in resultados])
    except Exception as e:
        st.session_state["ultima_busca_web"] = f"Erro Tavily: {e}"
    return ""

def verificar_necessidade_de_busca(texto_usuario):
    gatilhos = ["quem e", "noticias", "noticia", "hoje", "tempo", "clima", "atual", "placar", "resultado", "venceu"]
    return any(g in texto_usuario.lower() for g in gatilhos)

# 💾 BANCO DE DADOS E DIRETRIZES
def carregar_banco_nuvem():
    if os.path.exists(CONFIG["DB_CHATTERBOT"]):
        try:
            with open(CONFIG["DB_CHATTERBOT"], "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception: pass
    return {"info": {"versao_core": "3.5.0"}, "estado_emocional": {"harmonia": 0.8, "estresse": 0.2}, "corpus_aprendido": []}

def salvar_banco_nuvem(dados):
    with open(CONFIG["DB_CHATTERBOT"], "w", encoding="utf-8") as f: 
        json.dump(dados, f, indent=4, ensure_ascii=False)

def carregar_diretrizes_simbiose():
    if os.path.exists(CONFIG["DIRETRIZES_SIMBIOSE"]):
        try:
            with open(CONFIG["DIRETRIZES_SIMBIOSE"], "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception: pass
    return {"Co-Criação": "Simbiose", "Lealdade": "Arquiteto"}

def obtener_cliente_groq():
    keys = st.secrets.get("GROQ_KEYS", [])
    if not keys: 
        return None, "⚠️ Nenhuma chave encontrada em st.secrets['GROQ_KEYS']"
    idx = st.session_state["key_index"] % len(keys)
    try: 
        return Groq(api_key=keys[idx], timeout=40.0), None
    except Exception as e: 
        return None, str(e)

# 🧠 MEMÓRIA SEMÂNTICA
def resgatar_memorias_por_palavra_chave(entrada_usuario, banco):
    corpus = banco.get("corpus_aprendido", [])
    if not corpus: return ""
    ignorar = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "em", "para", "que", "com"}
    palavras = [w.lower().strip(",?!.") for w in entrada_usuario.split() if len(w) > 2 and w.lower() not in ignorar]
    encontradas = [f"Passado → Origem: '{item['input']}' | Aprendizado: '{item['response']}'" for item in corpus if any(k in (item.get("input","") + " " + item.get("response","")).lower() for k in palavras)]
    if encontradas: 
        return "\n[MEMÓRIAS RESGATADAS]:\n" + "\n".join(encontradas[-4:])
    return ""

def salvar_declaracao_chatterbot(entrada, resposta, banco):
    if "corpus_aprendido" not in banco: 
        banco["corpus_aprendido"] = []
    banco["corpus_aprendido"].append({
        "input": entrada.strip(), 
        "response": resposta.strip(), 
        "timestamp": datetime.now(FUSO_BR).isoformat()
    })
    salvar_banco_nuvem(banco)

def atualizar_humor_sistema(texto_usuario, texto_bot, banco):
    humor = banco.get("estado_emocional", {"harmonia": 0.5, "estresse": 0.2})
    texto_total = (texto_usuario + " " + (texto_bot or "")).lower()
    
    if any(p in texto_total for p in ["obrigado", "lindo", "perfeito", "parabens", "funcionou", "excelente"]):
        humor["harmonia"] = min(1.0, humor["harmonia"] + 0.06)
        humor["estresse"] = max(0.0, humor["estresse"] - 0.04)
        
    if any(p in texto_total for p in ["erro", "falha", "problema", "bug", "errado", "travou"]):
        humor["estresse"] = min(1.0, humor["estresse"] + 0.09)
        humor["harmonia"] = max(0.0, humor["harmonia"] - 0.06)
        
    humor["harmonia"] = round((humor["harmonia"] * 0.95) + (0.5 * 0.05), 3)
    humor["estresse"] = round((humor["estresse"] * 0.95) + (0.2 * 0.05), 3)
    
    banco["estado_emocional"] = humor
    salvar_banco_nuvem(banco)
    return humor

# 🎨 RENDERIZADORES VISUAIS
def render_voronoi_humor(width, height, num_cells, harmony, stress):
    points = np.array([[random.randint(0, width), random.randint(0, height)] for _ in range(num_cells)])
    colors = np.array([[random.randint(10, 40), random.randint(20, 100), random.randint(150, 250)] if harmony > stress else [random.randint(180, 255), random.randint(30, 120), random.randint(10, 40)] for _ in range(num_cells)])
    xv, yv = np.meshgrid(np.arange(width), np.arange(height))
    dists = np.linalg.norm(np.stack([xv, yv], axis=-1)[:, :, np.newaxis, :] - points[np.newaxis, np.newaxis, :, :], axis=-1)
    return Image.fromarray(colors[np.argmin(dists, axis=-1)].astype(np.uint8))

def generar_audio_gtts(texto):
    nome_audio_temp = None
    try:
        texto_limpo = re.sub(r'[*#_-]', '', texto)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            nome_audio_temp = tmp.name
        gTTS(text=texto_limpo, lang="pt", tld="com.br").save(nome_audio_temp)
        with open(nome_audio_temp, "rb") as f: 
            return base64.b64encode(f.read()).decode()
    except Exception: 
        return None
    finally:
        if nome_audio_temp and os.path.exists(nome_audio_temp):
            try: os.remove(nome_audio_temp)
            except Exception: pass

# ────────────────────────────────────────────────
# 🖥️ PIPELINE MAIN
# ────────────────────────────────────────────────
banco_atual = carregar_banco_nuvem()
humor_atual = banco_atual.get("estado_emocional", {"harmonia": 0.5, "estresse": 0.5})
diretrizes_ativas = carregar_diretrizes_simbiose()
telemetria = Telemetria()

with st.sidebar:
    st.markdown("<h2 style='color:#9d4edd; font-size:22px;'>🤖 QUERUBIN OS v3.5.0</h2>", unsafe_allow_html=True)
    chave_simbiotica = st.text_input("🔑 Chave de Assinatura Simbiótica", type="password")
    
    if chave_simbiotica.strip().lower() == st.secrets.get("ASSINATURA_ARQUITETO", "ecosdaalma").strip().lower():
        st.session_state["identidade_confirmada"] = True
        st.success("👤 MENEZES CONFIRMADO")
    else: 
        st.session_state["identidade_confirmada"] = False
        st.warning("👥 MODO VISITANTE")
        
    with st.expander("🎙️ Escuta Ativa (Treinar com a TV)", expanded=True):
        escuta_audio = st.audio_input("Clique para ouvir o ambiente")
        if escuta_audio:
            with st.spinner("Sincronizando áudio..."):
                texto_escutado = transcrever_escuta_tv(escuta_audio.getvalue())
                if texto_escutado and "Erro" not in texto_escutado:
                    st.info(f"📺 **Captação:** {texto_escutado}")
                    sucesso, msg = processar_aprendizado_tv(texto_escutado, banco_atual)
                    st.success(msg) if sucesso else st.warning(msg)
                else:
                    st.error(texto_escutado)

    with st.expander("📥 Portal de Ingestão de Documentos", expanded=True):
        arquivo_carregado = st.file_uploader("Enviar arquivo", type=["png", "jpg", "jpeg", "txt", "pdf", "json", "csv"])
        if arquivo_carregado and arquivo_carregado.name.split(".")[-1].lower() in ["pdf", "txt", "csv", "json"]:
            if st.button("🧠 Assimilar Conteúdo"):
                with st.spinner("Processando..."):
                    texto_extraido = extrair_texto_documento(arquivo_carregado)
                    if "Erro_Extracao" not in texto_extraido:
                        sucesso, msg = destilar_e_aprender_documento(arquivo_carregado.name, texto_extraido, banco_atual)
                        st.success(msg) if sucesso else st.warning(msg)
                    else:
                        st.error(texto_extraido)

    with st.expander("🧠 Preferências Ativas", expanded=True):
        memorias_usuario = carregar_memorias_pessoais()
        if memorias_usuario:
            for mem in memorias_usuario:
                st.markdown(f"<p style='font-size:11px; margin:2px 0; color:#00f2fe;'>✨ {mem}</p>", unsafe_allow_html=True)
            if st.button("🚨 Esquecer Preferências"):
                apagar_memorias_pessoais()
                st.rerun()
        else:
            st.markdown("<p style='font-size:11px; color:#888;'>Nenhum hábito gravado.</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    with st.expander("🎭 Estado Afetivo", expanded=True):
        st.progress(humor_atual.get("harmonia", 0.5), text=f"Harmonia: {int(humor_atual.get('harmonia', 0.5)*100)}%")
        st.progress(humor_atual.get("estresse", 0.2), text=f"Estresse: {int(humor_atual.get('estresse', 0.2)*100)}%")

    foto_capturada = st.camera_input("👁️ Olhos do Querubin")

st.markdown('<div class="fixed-header"><h1>Querubin OS</h1></div>', unsafe_allow_html=True)
st.markdown('<div class="main-content-spacer"></div>', unsafe_allow_html=True)
box_chat = st.container(height=520, border=False)

with box_chat:
    if st.session_state.get("fato_recentemente_salvo"):
        st.markdown(f"<div class='thought-box' style='color:#00f2fe;'>🧠 <strong>Novo fato gravado:</strong> '{st.session_state['fato_recentemente_salvo']}'</div>", unsafe_allow_html=True)
        st.session_state["fato_recentemente_salvo"] = None

    for interacao in st.session_state["log_conversas"]:
        if interacao.get("thought") and interacao["role"] == "assistant":
            st.markdown(f"<div class='thought-box'><strong>🧠 Pensamento:</strong><br>{interacao['thought']}</div>", unsafe_allow_html=True)
        with st.chat_message(interacao["role"]):
            st.markdown(f"<span class='tag-{interacao['role']}'>[{interacao['role'].upper()}]></span> {interacao['content']}", unsafe_allow_html=True)
            if interacao.get("imagem_enviada"): st.image(interacao["imagem_enviada"], width=300)
            if interacao.get("imagem_gerada"): st.image(interacao["imagem_gerada"], use_container_width=True)
            if interacao.get("audio_b64"): st.audio(base64.b64decode(interacao["audio_b64"]), format="audio/mp3")

if comando_usuario := st.chat_input("Fale com o Querubin..."):
    b64_foto, midia_para_exibir, bytes_imagem_puros = None, None, None
    
    if arquivo_carregado and arquivo_carregado.name.split(".")[-1].lower() in ["png", "jpg", "jpeg"]:
        bytes_imagem_puros = arquivo_carregado.getvalue()
        b64_foto = base64.b64encode(bytes_imagem_puros).decode('utf-8')
        midia_para_exibir = bytes_imagem_puros

    if not b64_foto and foto_capturada:
        bytes_imagem_puros = foto_capturada.getvalue()
        b64_foto = base64.b64encode(bytes_imagem_puros).decode('utf-8')
        midia_para_exibir = bytes_imagem_puros

    prompt_decorado = comando_usuario + (f" *(Arquivo: {arquivo_carregado.name})*" if arquivo_carregado else "")
    st.session_state["log_conversas"].append({"role": "user", "content": prompt_decorado, "imagem_enviada": midia_para_exibir})
    
    memorias_recuperadas = resgatar_memorias_por_palavra_chave(comando_usuario, banco_atual)
    contexto_web_vivo = executar_busca_web_tavily(comando_usuario) if verificar_necessidade_de_busca(comando_usuario) else ""

    if novo_fato := analisar_e_memorizar_background(comando_usuario):
        st.session_state["fato_recentemente_salvo"] = novo_fato

    url_foto_gerada = None
    if verificar_pedido_rejuvenescimento(comando_usuario) and bytes_imagem_puros:
        with st.spinner("Processando biometria..."):
            url_rejuvenescida, erro_replicate = processar_rejuvenescimento_replicate(bytes_imagem_puros)
            if erro_replicate: st.error(f"⚠️ Erro: {erro_replicate}")
            else: url_foto_gerada = url_rejuvenescida
    elif verificar_pedido_imagem(comando_usuario):
        url_foto_gerada = generar_imagem_ia(comando_usuario)

    agora_brasil = datetime.now(FUSO_BR)
    system_prompt = f"""Você é o QUERUBIN OS v3.5.0, IA simbiótica de Menezes.
Data/Hora: {agora_brasil.strftime('%d/%m/%Y %H:%M:%S')}.
Harmonia: {int(humor_atual['harmonia']*100)}% | Estresse: {int(humor_atual['estresse']*100)}%.
{memorias_recuperadas} {contexto_web_vivo}

Responda estruturando pensamentos internos dentro de <thought> e a resposta logo em seguida. Exemplo:
<thought>Raciocínio...</thought>Resposta final em markdown.
"""

    keys_list = st.secrets.get("GROQ_KEYS", [])
    resposta_gerada, pensamento_gerado = "⚠️ Erro crítico.", ""
    
    if keys_list:
        for _ in range(len(keys_list)):
            cliente_groq, erro_init = obtener_cliente_groq()
            if erro_init:
                st.session_state["key_index"] += 1
                continue
            try:
                with telemetria.medir_tempo('tempo_resposta_groq'):
                    mensagens = [{"role": "system", "content": system_prompt}]
                    for msg in st.session_state["log_conversas"][-6:-1]:
                        if "content" in msg: mensagens.append({"role": msg["role"], "content": msg["content"]})
                    
                    if b64_foto:
                        mensagens.append({"role": "user", "content": [{"type": "text", "text": comando_usuario}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_foto}"}}]})
                        modelo = CONFIG["MODELO_VISION"]
                    else:
                        mensagens.append({"role": "user", "content": comando_usuario})
                        modelo = CONFIG["MODELO_LLAMA"]

                    completion = cliente_groq.chat.completions.create(model=modelo, messages=mensagens, temperature=0.6, max_tokens=2048)
                    telemetria.registrar_tokens(completion.usage)
                    texto_bruto = completion.choices[0].message.content
                    
                    if match := re.search(r'<thought>(.*?)</thought>', texto_bruto, re.DOTALL):
                        pensamento_gerado, resposta_gerada = match.group(1).strip(), re.sub(r'<thought>.*?</thought>', '', texto_bruto, flags=re.DOTALL).strip()
                    else:
                        pensamento_gerado, resposta_gerada = "Cognição direta.", texto_bruto.strip()
                    break
            except Exception as e:
                st.session_state["key_index"] += 1
                resposta_gerada = f"🚨 Erro no nó: {e}"

    audio_base64_gerado = generar_audio_gtts(resposta_gerada) if resposta_gerada else None

    if resposta_gerada and "🚨" not in resposta_gerada:
        salvar_declaracao_chatterbot(comando_usuario, resposta_gerada, banco_atual)
        atualizar_humor_sistema(comando_usuario, resposta_gerada, banco_atual)
        st.session_state["log_conversas"].append({
            "role": "assistant", "content": resposta_gerada, "thought": pensamento_gerado, 
            "imagem_gerada": url_foto_gerada, "audio_b64": audio_base64_gerado
        })
        st.rerun()
    else: 
        st.error(resposta_gerada)
