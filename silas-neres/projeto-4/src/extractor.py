"""
Motor de extração semântica via Gemini.
Detecta o tipo de documento (boletim conjuntura vs prévia individual)
pelo conteúdo do texto e usa o schema Pydantic correto para cada caso.
"""
import logging
import time
from google import genai
from google.genai import types
from google.genai.errors import ServerError

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.schemas import DadosOperacionaisLLM, BoletimConjunturaLLM

logger = logging.getLogger(__name__)

_client = None
_MAX_RETRIES = 4
_RETRY_DELAYS = [10, 20, 40, 60]  # backoff em segundos

KEYWORDS_BOLETIM = [
    "conjuntura do setor",
    "balanço das empresas",
    "boletim",
    "setor habitacional",
]


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _call_with_retry(model: str, contents: str, config) -> object:
    """Chama o Gemini com retry exponencial em caso de 503/429."""
    client = _get_client()
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:
            is_retryable = "503" in str(e) or "429" in str(e) or "UNAVAILABLE" in str(e)
            if is_retryable and attempt < _MAX_RETRIES:
                logger.warning(f"Gemini {e.__class__.__name__} (tentativa {attempt}/{_MAX_RETRIES}). Aguardando {delay}s...")
                time.sleep(delay)
            else:
                raise
    # Última tentativa sem captura
    return client.models.generate_content(model=model, contents=contents, config=config)


def detect_document_type(text: str) -> str:
    """
    Detecta o tipo do documento pelo conteúdo sem chamar o LLM.
    Retorna 'boletim_conjuntura' ou 'previa_operacional'.
    """
    text_lower = text.lower()
    if any(kw in text_lower for kw in KEYWORDS_BOLETIM):
        return "boletim_conjuntura"
    return "previa_operacional"


# ── Extração: Boletim de Conjuntura ───────────────────────────────────────────

PROMPT_BOLETIM = """Você é um analista de dados especializado em relatórios do setor habitacional brasileiro.

TIPO DE DOCUMENTO: Boletim de Conjuntura — contém variações percentuais de MÚLTIPLAS empresas.

REGRAS CRÍTICAS:
1. Capture as variações % exatamente como aparecem no documento. Remova o símbolo % e retorne apenas o número (ex: -32 para -32%).
2. Para as colunas de comparação: a primeira coluna é vs trimestre anterior, a segunda vs mesmo trimestre do ano anterior, a terceira 9m do penúltimo ano vs ano anterior a ele, a quarta 9m do último ano vs penúltimo ano.
3. Se um valor não estiver no documento, retorne null. NUNCA invente.
4. O campo 'observacao' deve conter o comentário textual do boletim, se houver.
5. Capture TODAS as empresas listadas nas tabelas.

TEXTO DO DOCUMENTO:
{text}
"""


def extract_boletim(pdf_text: str) -> BoletimConjunturaLLM:
    prompt = PROMPT_BOLETIM.format(text=pdf_text)

    response = _call_with_retry(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BoletimConjunturaLLM,
            temperature=0.0,
        ),
    )

    dados = response.parsed
    if dados is None:
        raise ValueError("Gemini retornou resposta vazia para boletim")

    logger.info(
        f"[Boletim] {dados.titulo} {dados.periodo} | "
        f"{len(dados.empresas)} empresas | {len(dados.totais)} totais"
    )
    return dados


# ── Extração: Prévia Operacional ───────────────────────────────────────────────

PROMPT_PREVIA = """Você é um analista de dados especializado em relatórios trimestrais de incorporadoras imobiliárias brasileiras.

TIPO DE DOCUMENTO: Prévia Operacional — contém valores ABSOLUTOS de UMA empresa.

REGRAS CRÍTICAS:
1. Extraia SOMENTE valores ABSOLUTOS (unidades, R$ mil). NUNCA confunda variação percentual com valor absoluto.
2. Se um campo não estiver no documento, retorne null. NUNCA invente valores.
3. VALORES MONETÁRIOS: sempre em R$ MIL. Se o documento usar R$ milhões, multiplique por 1.000.
4. TRIMESTRE: retorne apenas o número inteiro (1, 2, 3 ou 4). "1T25" = trimestre 1, ano 2025.
5. VENDAS LÍQUIDAS = vendas brutas MENOS distratos.
6. VSO: retorne apenas o número (ex: 15.3 para 15,3%).
7. Priorize dados DO TRIMESTRE, não acumulados do ano.

Empresa monitorada: {empresa}

TEXTO DO DOCUMENTO:
{text}
"""


def extract_previa(pdf_text: str, empresa: str) -> DadosOperacionaisLLM:
    prompt = PROMPT_PREVIA.format(text=pdf_text, empresa=empresa)

    response = _call_with_retry(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DadosOperacionaisLLM,
            temperature=0.0,
        ),
    )

    dados = response.parsed
    if dados is None:
        raise ValueError(f"Gemini retornou resposta vazia para {empresa}")

    logger.info(
        f"[Prévia/texto] {dados.empresa} {dados.trimestre}T{dados.ano} | "
        f"Vendas: {dados.vendas_liquidas_unidades} un."
    )
    return dados


PROMPT_PREVIA_IMAGEM = """Você é um analista de dados especializado em relatórios trimestrais de incorporadoras imobiliárias.

Este PDF é uma APRESENTAÇÃO/SLIDESHOW. Os dados estão em tabelas e gráficos visuais nas imagens abaixo.

REGRAS CRÍTICAS:
1. Leia TODAS as imagens e localize as tabelas com dados operacionais.
2. Extraia SOMENTE valores ABSOLUTOS: unidades, R$ mil ou R$ milhões. NUNCA confunda % de variação com valor absoluto.
3. VALORES MONETÁRIOS: sempre em R$ MIL. Se estiver em R$ milhões, multiplique por 1.000.
4. TRIMESTRE: retorne apenas o número inteiro (1, 2, 3 ou 4). "1T26" = trimestre 1, ano 2026.
5. VENDAS LÍQUIDAS = vendas brutas MENOS distratos/cancelamentos.
6. VSO: retorne apenas o número (ex: 15.3 para 15,3%).
7. Se um valor não estiver visível nas imagens, retorne null. NUNCA invente.
8. Priorize dados DO TRIMESTRE, não acumulados do ano.

Empresa monitorada: {empresa}

Analise as páginas do PDF abaixo e extraia os dados operacionais:
"""


def extract_previa_from_images(page_images: list[bytes], empresa: str) -> DadosOperacionaisLLM:
    """
    Extração via Gemini Vision — para PDFs de apresentação onde os dados
    estão em tabelas gráficas não capturáveis por extração de texto.
    """
    client = _get_client()

    # Monta conteúdo multimodal: imagens + instrução
    contents = []
    for img_bytes in page_images:
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
    contents.append(PROMPT_PREVIA_IMAGEM.format(empresa=empresa))

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=DadosOperacionaisLLM,
        temperature=0.0,
    )

    # Retry manual para multimodal (não usa _call_with_retry pois contents é lista)
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config
            )
            break
        except Exception as e:
            is_retryable = "503" in str(e) or "429" in str(e) or "UNAVAILABLE" in str(e)
            if is_retryable and attempt < _MAX_RETRIES:
                logger.warning(f"Gemini Vision retry {attempt}/{_MAX_RETRIES} em {delay}s...")
                time.sleep(delay)
            else:
                raise

    dados = response.parsed
    if dados is None:
        raise ValueError(f"Gemini Vision retornou resposta vazia para {empresa}")

    logger.info(
        f"[Prévia/vision] {dados.empresa} {dados.trimestre}T{dados.ano} | "
        f"Vendas: {dados.vendas_liquidas_unidades} un."
    )
    return dados
