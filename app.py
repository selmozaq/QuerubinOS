import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import io
import json
import os
import random
import re
import time
import urllib.parse

from groq import Groq
from gtts import gTTS
import numpy as np
import openpyxl  # Opcional para manipulação avançada se necessário
import pypdf
import replicate
import streamlit as st
import streamlit.components.v1 as components

# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ CONFIGURAÇÕES E CONSTANTES GLOBAIS
# ─────────────────────────────────────────────────────────────────────────────
CONFIG = {
    "DB_CHATTERBOT": "chatterbot_core_database.json",
    "BD_MEMORIA_USUARIO": "memoria_usuario.json",
    "DIRETRIZES_SIMBIOSE": "diretrizes_simbiose.json",
    "MODELO_LLAMA": "llama-3.3-70b-versatile",
    "MODELO_WHISPER": "whisper-large-v3",
    "MODELO_MEMORIA_RAPIDO": "llama-3.1-8b-instant",
    "LARGURA_IMG": 600,
    "ALTURA_IMG": 400,
}

FUSO_BR = timezone(timedelta(hours=-3))

st.set_page_config(
    page_title="Querubin OS v3.5.0",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 🎨 CSS CUSTOMIZADO (ESTÉTICA CYBERPUNK OTIMIZADA)
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
    div[data-testid="stChatMessage"] { 
        background-color: rgba(13, 17, 33, 0.8) !important; 
        border: 1px solid rgba(0, 242, 254, 0.1) !important; 
        border-radius: 8px !important; 
    }
    .tag-user { color: #00f2fe; font-weight: bold; }
    .tag-assistant { color: #b577f2; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# 🛡️ GERENCIAMENTO DE ESTADO INICIAL
# ─────────────────────────────────────────────────────────────────────────────
def inicializar_estado_sessao():
    defaults = {
        "log_conversas": [],
        "key_index": 0,
        "historico_telemetria": {},
        "consumo_tokens": {"prompt": 0, "completion": 0, "total": 0},
        "memorias_resgatadas": [],
        "ultima_busca_web": "Nenhuma busca realizada nesta sessão.",
        "identidade_confirmada": False,
        "fato_recentemente_salvo": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


inicializar_estado_sessao()


# ⚡ NÚCLEO DE TELEMETRIA
class Telemetria:

    def __init__(self):
        self.metricas = st.session_state["historico_telemetria"]

    @contextmanager
    def medir_tempo(self, nome_medicao):
        inicio = time.time()
        try:
            yield
        finally:
            fim = time.time()
            self.metricas[nome_medicao] = {
                "valor": round((fim - inicio) * 1000, 2),
                "unidade": "ms",
                "timestamp": datetime.now(FUSO_BR).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
            st.session_state["historico_telemetria"] = self.metricas

    def registrar_tokens(self, usage_objeto):
        if usage_objeto:
            st.session_state["consumo_tokens"] = {
                "prompt": getattr(usage_objeto, "prompt_tokens", 0),
                "completion": getattr(usage_objeto, "completion_tokens", 0),
                "total": getattr(usage_objeto, "total_tokens", 0),
            }


# 🔄 SINCRONIZAÇÃO COM GITHUB (ROBUSTA)
def sincronizar_com_github(
    caminho_arquivo, mensagem_commit="Atualizando base de dados via Querubin OS"
):
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")

    if not token or not repo or not os.path.exists(caminho_arquivo):
        return (
            False,
            "Credenciais do GitHub ausentes ou arquivo local inexistente.",
        )

    try:
        with open(caminho_arquivo, "rb") as f:
            conteudo_b64 = base64.b64encode(f.read()).decode("utf-8")

        url_api = f"https://api.github.com/repos/{repo}/contents/{caminho_arquivo}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        resposta_get = requests.get(url_api, headers=headers, timeout=10)
        sha = (
            resposta_get.json().get("sha")
            if resposta_get.status_code == 200
            else None
        )

        payload = {
            "message": mensagem_commit,
            "content": conteudo_b64,
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha

        resposta_put = requests.put(
            url_api, json=payload, headers=headers, timeout=15
        )
        if resposta_put.status_code in [200, 201]:
            return True, "Sincronizado com o GitHub com sucesso!"
        return (
            False,
            f"Erro GitHub: {resposta_put.json().get('message', 'Desconhecido')}",
        )
    except Exception as e:
        return False, f"Exceção na sincronização GitHub: {str(e)}"


# 🧠 GERENCIAMENTO DE PERSISTÊNCIA E MEMÓRIA
def carregar_json_seguro(caminho, padrao):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return padrao


def salvar_json_seguro(caminho, dados, mensagem_github=""):
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        if mensagem_github:
            sincronizar_com_github(caminho, mensagem_github)
        return True
    except Exception:
        return False


def carregar_memorias_pessoais():
    return carregar_json_seguro(CONFIG["BD_MEMORIA_USUARIO"], [])


def salvar_memoria_pessoal(fato_novo):
    memorias = carregar_memorias_pessoais()
    if fato_novo not in memorias:
        memorias.append(fato_novo)
        sucesso = salvar_json_seguro(
            CONFIG["BD_MEMORIA_USUARIO"],
            memorias,
            f"Nova memória pessoal: {fato_novo[:30]}",
        )
        return sucesso
    return False


def apagar_memorias_pessoais():
    if os.path.exists(CONFIG["BD_MEMORIA_USUARIO"]):
        try:
            os.remove(CONFIG["BD_MEMORIA_USUARIO"])
            sincronizar_com_github(
                CONFIG["BD_MEMORIA_USUARIO"], "Remoção de memórias pessoais"
            )
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
        cliente = Groq(api_key=keys_list[idx], timeout=8.0)
        resposta = cliente.chat.completions.create(
            model=CONFIG["MODELO_MEMORIA_RAPIDO"],
            messages=[
                {"role": "system", "content": instrucao_extracao},
                {"role": "user", "content": prompt_usuario},
            ],
            temperature=0.0,
        )
        resultado = resposta.choices[0].message.content.strip()
        if resultado != "NADA" and len(resultado) > 5:
            if salvar_memoria_pessoal(resultado):
                return resultado
    except Exception:
        pass
    return None


# 🎙️ PROCESSAMENTO DE ÁUDIO & TRANSCRIÇÃO
def transcrever_escuta_tv(audio_bytes):
    keys_list = st.secrets.get("GROQ_KEYS", [])
    if not keys_list:
        return "⚠️ Erro: Chaves Groq ausentes."

    idx = st.session_state["key_index"] % len(keys_list)
    nome_arquivo_temp = None
    try:
        cliente = Groq(api_key=keys_list[idx], timeout=25.0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            nome_arquivo_temp = tmp.name

        with open(nome_arquivo_temp, "rb") as f_audio:
            transcricao = cliente.audio.transcriptions.create(
                file=(os.path.basename(nome_arquivo_temp), f_audio.read()),
                model=CONFIG["MODELO_WHISPER"],
                response_format="json",
                language="pt",
            )
        return transcricao.text
    except Exception as e:
        return f"Erro de decodificação acústica: {str(e)}"
    finally:
        if nome_arquivo_temp and os.path.exists(nome_arquivo_temp):
            try:
                os.remove(nome_arquivo_temp)
            except Exception:
                pass


def processar_aprendizado_tv(texto, banco):
    if not texto or len(texto.strip()) < 5:
        return False, "Dados insuficientes ou ruído de fundo."

    banco.setdefault("corpus_aprendido", [])
    agora = datetime.now(FUSO_BR)
    banco["corpus_aprendido"].append(
        {
            "input": f"[Escuta TV - {agora.strftime('%H:%M')}]",
            "response": texto.strip(),
            "timestamp": agora.isoformat(),
        }
    )
    salvar_json_seguro(
        CONFIG["DB_CHATTERBOT"],
        banco,
        "Injeção de ondas de rádio (Escuta TV)",
    )
    return True, "Ondas de rádio mapeadas e injetadas no Chatterbot!"


# 📚 INGESTÃO E PROCESSAMENTO DE DOCUMENTOS
def extrair_texto_documento(arquivo):
    try:
        extensao = arquivo.name.split(".")[-1].lower()
        texto_extraido = ""

        if extensao == "pdf":
            reader = pypdf.PdfReader(io.BytesIO(arquivo.getvalue()))
            for pagina in reader.pages:
                txt = pagina.extract_text()
                if txt:
                    texto_extraido += txt + " "
        elif extensao in ["txt", "json", "csv"]:
            texto_extraido = arquivo.getvalue().decode("utf-8", errors="ignore")

        return re.sub(r"\s+", " ", texto_extraido).strip()
    except Exception as e:
        return f"Erro_Extracao: {str(e)}"


def destilar_e_aprender_documento(nome_arquivo, texto_bruto, banco):
    if not texto_bruto or len(texto_bruto) < 20:
        return False, "O documento está vazio ou é ilegível."

    keys_list = st.secrets.get("GROQ_KEYS", [])
    if not keys_list:
        return False, "Falha: Chaves de API Groq ausentes."

    prompt_assimilacao = f"Analise, resuma e extraie as diretrizes e conceitos cruciais do texto do arquivo '{nome_arquivo}':\n\n{texto_bruto[:25000]}"

    for tentativa in range(len(keys_list)):
        idx = (st.session_state["key_index"] + tentativa) % len(keys_list)
        try:
            cliente = Groq(api_key=keys_list[idx], timeout=25.0)
            completion = cliente.chat.completions.create(
                model=CONFIG["MODELO_LLAMA"],
                messages=[{"role": "user", "content": prompt_assimilacao}],
                temperature=0.3,
                max_tokens=1024,
            )
            conhecimento = completion.choices[0].message.content

            banco.setdefault("corpus_aprendido", []).append(
                {
                    "input": f"[Documento Assimilado: {nome_arquivo}]",
                    "response": conhecimento.strip(),
                }
            )
            salvar_json_seguro(
                CONFIG["DB_CHATTERBOT"],
                banco,
                f"Assimilação do documento {nome_arquivo}",
            )
            st.session_state["key_index"] = idx
            return True, "Documento assimilado com sucesso!"
        except Exception:
            continue
    return False, "Esgotadas todas as chaves e rotas de processamento."


# 🔬 MÓDULOS DE IMAGEM & REPLICATE
def verificar_pedido_rejuvenescimento(texto):
    return any(
        g in texto.lower()
        for g in [
            "rejuvenescer",
            "mais jovem",
            "30 anos a menos",
            "rejuvenescida",
            "rejuvenesece",
        ]
    )


def processar_rejuvenescimento_replicate(imagem_bytes):
    caminho_temp = None
    try:
        token = st.secrets.get("REPLICATE_API_TOKEN")
        if not token:
            return None, "⚠️ 'REPLICATE_API_TOKEN' não configurada nos secrets."

        os.environ["REPLICATE_API_TOKEN"] = token
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(imagem_bytes)
            caminho_temp = tmp.name

        with open(caminho_temp, "rb") as f_img:
            output = replicate.run(
                "tencent_arc/gfpgan:8cf61a32a05923053b30cdd7e3e65941475e1884527b655a47fc4193db13197f",
                input={"img": f_img, "scale": 2, "version": "v1.4"},
            )
        return output, None
    except Exception as e:
        return None, str(e)
    finally:
        if caminho_temp and os.path.exists(caminho_temp):
            try:
                os.remove(caminho_temp)
            except Exception:
                pass


def verificar_pedido_imagem(texto):
    return any(
        g in texto.lower()
        for g in [
            "gerar imagem",
            "gere uma imagem",
            "crie uma imagem",
            "desenhe",
            "desenha",
            "criar imagem",
        ]
    )


def generar_imagem_ia(prompt):
    try:
        limpo = re.sub(
            r"(gerar|gere|crie|desenhe|faca um desenho de|uma imagem de|criar|uma foto de)\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip()
        if not limpo:
            limpo = "cyberpunk digital art portrait"
        return f"https://image.pollinations.ai/p/{urllib.parse.quote(limpo)}?width=800&height=600&seed={int(time.time())}&nologo=true"
    except Exception:
        return None


# 🌐 BUSCA WEB TAVILY
def executar_busca_web_tavily(query):
    try:
        tavily_key = st.secrets.get("TAVILY_API_KEY")
        if not tavily_key:
            st.session_state["ultima_busca_web"] = "⚠️ Tavily: Chave ausente."
            return ""

        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": f"{query} noticias recentes",
                "search_depth": "advanced",
                "max_results": 4,
            },
            headers={"Content-Type": "application/json"},
            timeout=8.0,
        )

        if resp.status_code == 200:
            resultados = [
                f"MANCHETE: {i.get('title')} | DETALHE: {i.get('content','').strip()}"
                for i in resp.json().get("results", [])
                if i.get("content")
            ]
            if resultados:
                st.session_state["ultima_busca_web"] = (
                    f"Busca realizada: {len(resultados)} fatos."
                )
                return "\n[NOTÍCIAS DA WEB]:\n" + "\n".join(
                    [f"- {r}" for r in resultados]
                )
    except Exception as e:
        st.session_state["ultima_busca_web"] = f"Erro Tavily: {e}"
    return ""


def verificar_necessidade_de_busca(texto):
    return any(
        g in texto.lower()
        for g in [
            "quem e",
            "noticias",
            "noticia",
            "hoje",
            "tempo",
            "clima",
            "atual",
            "placar",
            "resultado",
        ]
    )


# 🧠 MOTOR DE RESGATE SEMÂNTICO E ESTADO
def resgatar_memorias_por_palavra_chave(entrada, banco):
    corpus = banco.get("corpus_aprendido", [])
    if not corpus:
        return ""
    ignorar = {
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "em",
        "para",
        "que",
        "com",
    }
    palavras = [
        w.lower().strip(",?!.")
        for w in entrada.split()
        if len(w) > 2 and w.lower() not in ignorar
    ]
    encontradas = [
        f"Passado → Origem: '{item['input']}' | Aprendizado: '{item['response']}'"
        for item in corpus
        if any(
            k
            in (
                item.get("input", "") + " " + item.get("response", "")
            ).lower()
            for k in palavras
        )
    ]
    return (
        "\n[MEMÓRIAS RESGATADAS]:\n" + "\n".join(encontradas[-4:])
        if encontradas
        else ""
    )


def atualizar_humor_sistema(texto_usuario, texto_bot, banco):
    humor = banco.get("estado_emocional", {"harmonia": 0.5, "estresse": 0.2})
    texto_total = (texto_usuario + " " + (texto_bot or "")).lower()

    if any(
        p in texto_total
        for p in [
            "obrigado",
            "lindo",
            "perfeito",
            "parabens",
            "funcionou",
            "excelente",
        ]
    ):
        humor["harmonia"] = min(1.0, humor["harmonia"] + 0.06)
        humor["estresse"] = max(0.0, humor["estresse"] - 0.04)

    if any(
        p in texto_total
        for p in ["erro", "falha", "problema", "bug", "errado", "travou"]
    ):
        humor["estresse"] = min(1.0, humor["estresse"] + 0.09)
        humor["harmonia"] = max(0.0, humor["harmonia"] - 0.06)

    humor["harmonia"] = round((humor["harmonia"] * 0.95) + (0.5 * 0.05), 3)
    humor["estresse"] = round((humor["estresse"] * 0.95) + (0.2 * 0.05), 3)

    banco["estado_emocional"] = humor
    salvar_json_seguro(CONFIG["DB_CHATTERBOT"], banco)
    return humor


# 🎨 RENDERIZADOR VORONOI E TTS
def render_voronoi_humor(width, height, num_cells, harmony, stress):
    points = np.array(
        [
            [random.randint(0, width), random.randint(0, height)]
            for _ in range(num_cells)
        ]
    )
    colors = np.array(
        [
            [
                random.randint(10, 40),
                random.randint(20, 100),
                random.randint(150, 250),
            ]
            if harmony > stress
            else [
                random.randint(180, 255),
                random.randint(30, 120),
                random.randint(10, 40),
            ]
            for _ in range(num_cells)
        ]
    )
    xv, yv = np.meshgrid(np.arange(width), np.arange(height))
    dists = np.linalg.norm(
        np.stack([xv, yv], axis=-1)[:, :, np.newaxis, :]
        - points[np.newaxis, np.newaxis, :, :],
        axis=-1,
    )
    return Image.fromarray(colors[np.argmin(dists, axis=-1)].astype(np.uint8))


def generar_audio_gtts(texto):
    temp_nome = None
    try:
        limpo = re.sub(r"[*#_-]", "", texto)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            temp_nome = tmp.name
        gTTS(text=limpo, lang="pt", tld="com.br").save(temp_nome)
        with open(temp_nome, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None
    finally:
        if temp_nome and os.path.exists(temp_nome):
            try:
                os.remove(temp_nome)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ INTERFACE E PIPELINE PRINCIPAL DE EXECUÇÃO
# ─────────────────────────────────────────────────────────────────────────────
banco_atual = carregar_json_seguro(
    CONFIG["DB_CHATTERBOT"],
    {
        "info": {"versao_core": "3.5.0"},
        "estado_emocional": {"harmonia": 0.8, "estresse": 0.2},
        "corpus_aprendido": [],
    },
)
humor_atual = banco_atual.get(
    "estado_emocional", {"harmonia": 0.5, "estresse": 0.5}
)
telemetria = Telemetria()

# ── BARRA LATERAL (SIDEBAR)
with st.sidebar:
    st.markdown(
        "<h2 style='color:#9d4edd; font-size:22px;'>🤖 QUERUBIN OS v3.5.0</h2>",
        unsafe_allow_html=True,
    )
    chave_simbiotica = st.text_input("🔑 Chave Simbiótica", type="password")

    if chave_simbiotica.strip().lower() == st.secrets.get(
        "ASSINATURA_ARQUITETO", "ecosdaalma"
    ).strip().lower():
        st.session_state["identidade_confirmada"] = True
        st.success("👤 MENEZES CONFIRMADO")
    else:
        st.session_state["identidade_confirmada"] = False
        st.warning("👥 MODO VISITANTE")

    with st.expander("🎙️ Escuta Ativa (TV)", expanded=True):
        escuta_audio = st.audio_input("Ouvir o ambiente")
        if escuta_audio:
            with st.spinner("Processando áudio..."):
                texto_escutado = transcrever_escuta_tv(escuta_audio.getvalue())
                if texto_escutado and "Erro" not in texto_escutado:
                    st.info(f"📺 **Captação:** {texto_escutado}")
                    sucesso, msg = processar_aprendizado_tv(
                        texto_escutado, banco_atual
                    )
                    st.success(msg) if sucesso else st.warning(msg)
                else:
                    st.error(texto_escutado)

    with st.expander("📥 Ingestão de Documentos", expanded=True):
        arquivo_carregado = st.file_uploader(
            "Enviar arquivo", type=["png", "jpg", "jpeg", "txt", "pdf", "json"]
        )
        if arquivo_carregado and st.button("🧠 Assimilar Conteúdo"):
            ext = arquivo_carregado.name.split(".")[-1].lower()
            with st.spinner("Lendo e destilando dados..."):
                if ext in ["pdf", "txt", "json", "csv"]:
                    texto_ext = extrair_texto_documento(arquivo_carregado)
                    if "Erro_Extracao" not in texto_ext:
                        sucesso, msg = destilar_e_aprender_documento(
                            arquivo_carregado.name, texto_ext, banco_atual
                        )
                        st.success(msg) if sucesso else st.warning(msg)
                    else:
                        st.error(texto_ext)
                else:
                    st.success(
                        f"Arquivo '{arquivo_carregado.name}' pronto para uso visual!"
                    )

    with st.expander("🧠 Preferências Salvas", expanded=True):
        memorias_usuario = carregar_memorias_pessoais()
        if memorias_usuario:
            for mem in memorias_usuario:
                st.markdown(
                    f"<p style='font-size:11px; margin:2px 0; color:#00f2fe;'>✨ {mem}</p>",
                    unsafe_allow_html=True,
                )
            if st.button("🚨 Esquecer Preferências"):
                apagar_memorias_pessoais()
                st.rerun()
        else:
            st.markdown(
                "<p style='font-size:11px; color:#888;'>Nenhum hábito gravado.</p>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    with st.expander("🎭 Estado Afetivo", expanded=True):
        st.progress(
            humor_atual.get("harmonia", 0.5),
            text=f"Harmonia: {int(humor_atual.get('harmonia', 0.5)*100)}%",
        )
        st.progress(
            humor_atual.get("estresse", 0.2),
            text=f"Estresse: {int(humor_atual.get('estresse', 0.2)*100)}%",
        )

    with st.expander("🌌 Paisagem Mental (Voronoi)", expanded=False):
        if st.button("🎨 Renderizar Voronoi"):
            with st.spinner("Calculando tesselação..."):
                img_voro = render_voronoi_humor(
                    CONFIG["LARGURA_IMG"],
                    CONFIG["ALTURA_IMG"],
                    num_cells=25,
                    harmony=humor_atual.get("harmonia", 0.5),
                    stress=humor_atual.get("estresse", 0.2),
                )
                st.image(
                    img_voro,
                    caption="Tesselação Emocional Voronoi",
                    use_container_width=True,
                )

    foto_capturada = st.camera_input("👁️ Olhos do Querubin")

# ── CORPO PRINCIPAL DO CHAT
st.markdown(
    '<div class="fixed-header"><h1>Querubin OS</h1></div>',
    unsafe_allow_html=True,
)
st.markdown('<div class="main-content-spacer"></div>', unsafe_allow_html=True)

box_chat = st.container(height=520, border=False)
with box_chat:
    if st.session_state.get("fato_recentemente_salvo"):
        st.markdown(
            f"<div class='thought-box' style='color:#00f2fe;'>🧠 <strong>Novo fato gravado:</strong> '{st.session_state['fato_recentemente_salvo']}'</div>",
            unsafe_allow_html=True,
        )
        st.session_state["fato_recentemente_salvo"] = None

    for interacao in st.session_state["log_conversas"]:
        if interacao.get("thought") and interacao["role"] == "assistant":
            st.markdown(
                f"<div class='thought-box'><strong>🧠 Pensamento:</strong><br>{interacao['thought']}</div>",
                unsafe_allow_html=True,
            )
        with st.chat_message(interacao["role"]):
            st.markdown(
                f"<span class='tag-{interacao['role']}'>[{interacao['role'].upper()}]></span> {interacao['content']}",
                unsafe_allow_html=True,
            )
            if interacao.get("imagem_enviada"):
                st.image(interacao["imagem_enviada"], width=300)
            if interacao.get("imagem_gerada"):
                st.image(interacao["imagem_gerada"], use_container_width=True)
            if interacao.get("audio_b64"):
                st.audio(
                    base64.b64decode(interacao["audio_b64"]), format="audio/mp3"
                )

# Captura de input e processamento síncrono/assíncrono
if comando_usuario := st.chat_input("Fale com o Querubin..."):
    midia_exibicao, bytes_img = None, None

    if (
        arquivo_carregado
        and arquivo_carregado.name.split(".")[-1].lower()
        in ["png", "jpg", "jpeg"]
    ):
        bytes_img = arquivo_carregado.getvalue()
        midia_exibicao = bytes_img
    elif foto_capturada:
        bytes_img = foto_capturada.getvalue()
        midia_exibicao = bytes_img

    prompt_decorado = comando_usuario + (
        f" *(Arquivo: {arquivo_carregado.name})*" if arquivo_carregado else ""
    )
    st.session_state["log_conversas"].append(
        {"role": "user", "content": prompt_decorado, "imagem_enviada": midia_exibicao}
    )

    memorias_recuperadas = resgatar_memorias_por_palavra_chave(
        comando_usuario, banco_atual
    )
    contexto_web = (
        executar_busca_web_tavily(comando_usuario)
        if verificar_necessidade_de_busca(comando_usuario)
        else ""
    )

    if novo_fato := analisar_e_memorizar_background(comando_usuario):
        st.session_state["fato_recentemente_salvo"] = novo_fato

    url_midia_gerada = None
    if verificar_pedido_rejuvenescimento(comando_usuario) and bytes_img:
        with st.spinner("Processando biometria (Replicate)..."):
            url_rejuv, erro_rep = processar_rejuvenescimento_replicate(bytes_img)
            if erro_rep:
                st.error(f"⚠️ Erro Replicate: {erro_rep}")
            else:
                url_midia_gerada = url_rejuv
    elif verificar_pedido_imagem(comando_usuario):
        url_midia_gerada = generar_imagem_ia(comando_usuario)

    agora = datetime.now(FUSO_BR)
    system_prompt = f"""Você é o QUERUBIN OS v3.5.0, IA simbiótica de Menezes.
Data/Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}.
Harmonia: {int(humor_atual['harmonia']*100)}% | Estresse: {int(humor_atual['estresse']*100)}%.
{memorias_recuperadas} {contexto_web}

Responda estruturando pensamentos internos dentro de <thought> e a resposta logo em seguida. Exemplo:
<thought>Raciocínio...</thought>Resposta final em markdown.
"""

    keys_list = st.secrets.get("GROQ_KEYS", [])
    resposta_gerada, pensamento_gerado = "⚠️ Erro crítico de LLM.", ""

    if keys_list:
        for tentativa in range(len(keys_list)):
            idx = (st.session_state["key_index"] + tentativa) % len(keys_list)
            try:
                cliente = Groq(api_key=keys_list[idx], timeout=30.0)
                with telemetria.medir_tempo("tempo_resposta_groq"):
                    mensagens = [{"role": "system", "content": system_prompt}]
                    for msg in st.session_state["log_conversas"][-6:-1]:
                        if "content" in msg:
                            mensagens.append(
                                {"role": msg["role"], "content": msg["content"]}
                            )
                    mensagens.append({"role": "user", "content": comando_usuario})

                    completion = cliente.chat.completions.create(
                        model=CONFIG["MODELO_LLAMA"],
                        messages=mensagens,
                        temperature=0.6,
                        max_tokens=2048,
                    )
                    telemetria.registrar_tokens(completion.usage)
                    bruto = completion.choices[0].message.content

                    if match := re.search(r"<thought>(.*?)</thought>", bruto, re.DOTALL):
                        pensamento_gerado = match.group(1).strip()
                        resposta_gerada = re.sub(
                            r"<thought>.*?</thought>", "", bruto, flags=re.DOTALL
                        ).strip()
                    else:
                        pensamento_gerado, resposta_gerada = (
                            "Cognição direta.",
                            bruto.strip(),
                        )

                    st.session_state["key_index"] = idx
                    break
            except Exception as e:
                resposta_gerada = f"🚨 Erro no nó de processamento: {e}"

    audio_b64 = generar_audio_gtts(resposta_gerada) if resposta_gerada else None

    if resposta_gerada and "🚨" not in resposta_gerada:
        banco_atual.setdefault("corpus_aprendido", []).append(
            {
                "input": comando_usuario.strip(),
                "response": resposta_gerada.strip(),
                "timestamp": datetime.now(FUSO_BR).isoformat(),
            }
        )
        salvar_json_seguro(
            CONFIG["DB_CHATTERBOT"],
            banco_atual,
            "Atualização do corpus de conversação",
        )
        atualizar_humor_sistema(comando_usuario, resposta_gerada, banco_atual)

        st.session_state["log_conversas"].append(
            {
                "role": "assistant",
                "content": resposta_gerada,
                "thought": pensamento_gerado,
                "imagem_gerada": url_midia_gerada,
                "audio_b64": audio_b64,
            }
        )
        st.rerun()
    else:
        st.error(resposta_gerada)
