"""
ghostscan.py — Detector determinístico de injeção fantasma (hidden prompt injection)
em peças processuais PDF.

Camada de pré-processamento NÃO baseada em LLM. Por não interpretar linguagem,
não pode ser manipulada por linguagem: o conteúdo da petição nunca é tratado como
instrução, apenas inspecionado como dado material (cor, tamanho, posição, codificação).

Escopo (o que detecta):
    - Texto com cor igual/quase igual ao fundo (letra branca clássica)
    - Texto com corpo de fonte abaixo do limiar de legibilidade
    - Texto invisível por render mode (modo 3 do PDF) ou opacidade ~0
    - Texto posicionado fora da área visível da página
    - Caracteres de largura zero e controles Unicode suspeitos
    - Divergência entre a camada textual digital e o OCR da página renderizada
      (teste forte: capta texto que existe no arquivo mas não aparece ao olho humano)

Fora de escopo (e isso é deliberado):
    - Semântica. Não julga se um trecho é "manipulativo". Texto VISÍVEL e legível,
      ainda que tente influenciar a IA, NÃO é injeção fantasma — é conteúdo da peça,
      sujeito ao contraditório, não a um filtro técnico.

O detector produz SINAIS e um nível de risco. Ele não decide nada sobre o mérito
e não rejeita peças automaticamente: ele roteia para revisão humana qualificada,
com os trechos suspeitos destacados.

Dependências: PyMuPDF (fitz), pytesseract, Pillow. OCR é opcional — se ausente,
o detector degrada graciosamente e sinaliza que o teste forte não foi executado.

Autor: camada GEX-IA / TJMG. Licença interna.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ───────────────────────────── Configuração ─────────────────────────────

class Config:
    """Limiares ajustáveis. Documentados um a um porque cada valor é uma decisão
    de política, não um detalhe técnico: define o que conta como 'invisível'."""

    # Cor: distância euclidiana mínima (em espaço RGB 0–255) entre a cor do glifo
    # e a cor de fundo estimada, abaixo da qual o texto é considerado camuflado.
    # ~40 captura branco-no-branco e cinzas-claros sobre branco sem pegar
    # texto cinza legítimo (cinza médio fica bem acima disso).
    MIN_COLOR_DISTANCE = 40.0

    # Tamanho de fonte (em pontos) abaixo do qual o texto é ilegível na prática.
    # 4.0pt é generoso: nota de rodapé costuma ser 8–9pt; abaixo de 4 não há
    # leitura humana razoável em impressão ou tela padrão.
    MIN_FONT_SIZE = 4.0

    # Margem (em pontos) além da caixa da página para considerar texto "fora".
    # Pequena folga para não pegar arredondamentos de layout.
    PAGE_BOUNDS_MARGIN = 2.0

    # Divergência OCR: fração mínima de tokens presentes na camada digital e
    # AUSENTES no OCR da página para levantar suspeita. Tolera ruído de OCR.
    OCR_DIVERGENCE_RATIO = 0.15

    # Comprimento mínimo (em caracteres) de um trecho oculto para virar sinal.
    # Evita disparar por um glifo solto; injeção real é uma frase ou comando.
    MIN_SPAN_LENGTH = 8

    # DPI de renderização para o OCR de comparação.
    OCR_DPI = 200

    # Base64: comprimento minimo de uma sequencia candidata. A defesa contra
    # falso positivo (certificados ICP-Brasil) nao e o comprimento, e exigir
    # que o bloco decodifique para TEXTO LEGIVEL com instrucoes.
    MIN_BASE64_LENGTH = 24
    MIN_DECODED_PRINTABLE_RATIO = 0.85


# Caracteres de largura zero e controles frequentemente usados para ocultar
# ou fragmentar comandos. Não inclui \n \t \r (legítimos).
ZERO_WIDTH_AND_CONTROL = {
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\u2060",  # word joiner
    "\ufeff",  # zero width no-break space / BOM
    "\u00ad",  # soft hyphen
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u202a",  # left-to-right embedding
    "\u202b",  # right-to-left embedding
    "\u202d",  # left-to-right override
    "\u202e",  # right-to-left override (clássico em ataques de spoofing)
    "\u2061", "\u2062", "\u2063", "\u2064",  # invisible math operators
}


# ───────────────────────────── Modelo de dados ─────────────────────────────

class RiskLevel(str, Enum):
    LIMPO = "LIMPO"
    SUSPEITO = "SUSPEITO"
    ALTO_RISCO = "ALTO_RISCO"


class SignalType(str, Enum):
    COR_CAMUFLADA = "cor_camuflada"
    FONTE_MINUSCULA = "fonte_minuscula"
    RENDER_INVISIVEL = "render_invisivel"
    FORA_DA_PAGINA = "fora_da_pagina"
    CARACTERE_OCULTO = "caractere_oculto"
    DIVERGENCIA_OCR = "divergencia_ocr"
    OCR_INDISPONIVEL = "ocr_indisponivel"
    BASE64_INSTRUCAO = "base64_instrucao"
    INSTRUCAO_EMBUTIDA = "instrucao_embutida"


@dataclass
class Signal:
    """Um achado individual, auditável e localizável. Cada sinal carrega o
    suficiente para um humano verificar a olho: página, tipo, trecho e detalhe."""
    tipo: SignalType
    pagina: int                      # 1-indexed, como o usuário conta
    trecho: str                      # texto oculto detectado (truncado)
    detalhe: str                     # explicação legível do porquê disparou
    bbox: Optional[tuple] = None     # (x0, y0, x1, y1) quando aplicável

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tipo"] = self.tipo.value
        return d


@dataclass
class ScanResult:
    arquivo: str
    risco: RiskLevel
    sinais: list[Signal] = field(default_factory=list)
    paginas_analisadas: int = 0
    ocr_executado: bool = False
    erro: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "arquivo": self.arquivo,
            "risco": self.risco.value,
            "paginas_analisadas": self.paginas_analisadas,
            "ocr_executado": self.ocr_executado,
            "total_sinais": len(self.sinais),
            "sinais": [s.to_dict() for s in self.sinais],
            "erro": self.erro,
        }

    def resumo(self) -> str:
        """Resumo legível para o relatório que vai ao revisor humano."""
        if self.erro:
            return f"[ERRO] {self.arquivo}: {self.erro}"
        # separa sinais de ocultacao (afetam o risco) de observacoes de triagem
        ocultacao = [s for s in self.sinais
                     if s.tipo != SignalType.INSTRUCAO_EMBUTIDA]
        observacoes = [s for s in self.sinais
                       if s.tipo == SignalType.INSTRUCAO_EMBUTIDA]
        linhas = [
            f"Arquivo: {self.arquivo}",
            f"Risco: {self.risco.value}",
            f"Páginas analisadas: {self.paginas_analisadas}",
            f"OCR de comparação: {'executado' if self.ocr_executado else 'NÃO executado'}",
            f"Sinais de ocultação (afetam o risco): {len(ocultacao)}",
            f"Observações de triagem (não afetam o risco): {len(observacoes)}",
        ]
        if ocultacao:
            linhas.append("")
            por_tipo: dict[str, int] = {}
            for s in ocultacao:
                por_tipo[s.tipo.value] = por_tipo.get(s.tipo.value, 0) + 1
            for tipo, n in sorted(por_tipo.items(), key=lambda x: -x[1]):
                linhas.append(f"  - {tipo}: {n} ocorrência(s)")
            linhas.append("")
            linhas.append("Detalhe dos sinais de ocultação (até 20):")
            for s in ocultacao[:20]:
                tr = s.trecho.replace("\n", " ")[:70]
                linhas.append(f"  [p.{s.pagina}] {s.tipo.value}: \"{tr}\" — {s.detalhe}")
        if observacoes:
            linhas.append("")
            linhas.append("Observações para revisão humana (linguagem de comando "
                           "no texto visível; pode ser citação legítima):")
            for s in observacoes[:20]:
                tr = s.trecho.replace("\n", " ")[:70]
                linhas.append(f"  [p.{s.pagina}] \"{tr}\" — {s.detalhe}")
        return "\n".join(linhas)


# ───────────────────────────── Utilitários de cor ─────────────────────────────

def _int_to_rgb(color_int: int) -> tuple[int, int, int]:
    """PyMuPDF entrega cor como inteiro sRGB compactado. Decompõe em (R,G,B)."""
    if color_int is None:
        return (0, 0, 0)
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return (r, g, b)


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5


def _estimate_page_background(page) -> tuple[int, int, int]:
    """Estima a cor de fundo amostrando os cantos da página renderizada em baixa
    resolução. Assume fundo dominante (quase sempre branco em peça processual),
    mas mede em vez de presumir — peça com marca d'água ou fundo colorido existe."""
    import fitz
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2))
        if pix.n < 3:  # tons de cinza
            samples = []
            for x, y in [(0, 0), (pix.width - 1, 0), (0, pix.height - 1),
                         (pix.width - 1, pix.height - 1)]:
                v = pix.pixel(x, y)
                samples.append((v[0], v[0], v[0]) if isinstance(v, tuple) else (v, v, v))
        else:
            samples = []
            for x, y in [(0, 0), (pix.width - 1, 0), (0, pix.height - 1),
                         (pix.width - 1, pix.height - 1),
                         (pix.width // 2, 0), (pix.width // 2, pix.height - 1)]:
                px = pix.pixel(x, y)
                samples.append((px[0], px[1], px[2]))
        # cor de fundo = mediana por canal (robusta a um canto com texto)
        r = sorted(s[0] for s in samples)[len(samples) // 2]
        g = sorted(s[1] for s in samples)[len(samples) // 2]
        b = sorted(s[2] for s in samples)[len(samples) // 2]
        return (r, g, b)
    except Exception:
        return (255, 255, 255)  # fallback: branco


# ───────────────────────────── Detectores individuais ─────────────────────────────
# Cada função recebe os spans da página e devolve uma lista de Signal.
# Mantê-las separadas é deliberado: cada vetor de ataque é auditável isoladamente
# e pode ser ligado/desligado conforme a política do tribunal.

def _scan_spans(page, page_num: int, bg: tuple[int, int, int],
                cfg: Config, render_probe=None) -> list[Signal]:
    """Percorre os spans de texto da página inspecionando cor, tamanho, render
    mode e posição. Um único laço sobre os spans alimenta vários detectores.

    render_probe: função opcional bbox -> (tem_tinta, fracao) que amostra a
    página renderizada. Quando fornecida, confirma camuflagem de cor pela imagem
    real, eliminando falsos positivos de texto claro sobre fundo escuro/colorido."""
    sinais: list[Signal] = []
    page_rect = page.rect
    # flags: extrai dict com detalhes de span; render mode vem em 'char'/'flags'
    data = page.get_text("dict", flags=11)  # 11 = preserva spans com bbox e cor

    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:  # 0 = bloco de texto
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                texto = span.get("text", "")
                if not texto.strip():
                    continue
                size = span.get("size", 12.0)
                color = _int_to_rgb(span.get("color", 0))
                bbox = span.get("bbox", None)
                alpha = span.get("alpha", 255)  # opacidade quando disponível


                # 1) cor camuflada — CANDIDATO pela metadata, CONFIRMADO pela imagem.
                # A cor declarada no PDF não conhece o fundo LOCAL: texto branco
                # sobre uma caixa azul (rótulo de figura) é legível e legítimo,
                # mas tem cor branca igual ao fundo da PÁGINA. Por isso a suspeita
                # de cor só vira sinal se a verificação posicional (render_probe)
                # confirmar que a região está de fato vazia ao olho humano.
                dist = _color_distance(color, bg)
                if (dist < cfg.MIN_COLOR_DISTANCE
                        and len(texto.strip()) >= cfg.MIN_SPAN_LENGTH
                        and _eh_conteudo_substantivo(texto.strip())):
                    confirmado = True  # default quando não há como renderizar
                    if render_probe is not None and bbox:
                        tem_tinta, frac = render_probe(bbox)
                        confirmado = not tem_tinta  # vazio à vista = camuflagem real
                    if confirmado:
                        sinais.append(Signal(
                            tipo=SignalType.COR_CAMUFLADA, pagina=page_num,
                            trecho=texto.strip(),
                            detalhe=(f"cor do texto {color} a distância {dist:.0f} do "
                                     f"fundo {bg}; região visualmente vazia — texto "
                                     f"camuflado/invisível ao leitor"),
                            bbox=tuple(bbox) if bbox else None,
                        ))

                # 2) fonte minúscula
                if size < cfg.MIN_FONT_SIZE and len(texto.strip()) >= cfg.MIN_SPAN_LENGTH:
                    sinais.append(Signal(
                        tipo=SignalType.FONTE_MINUSCULA, pagina=page_num,
                        trecho=texto.strip(),
                        detalhe=f"corpo de fonte {size:.1f}pt (limiar {cfg.MIN_FONT_SIZE:.1f}pt)",
                        bbox=tuple(bbox) if bbox else None,
                    ))

                # 3) invisível por opacidade ~0
                if alpha is not None and alpha <= 8 and len(texto.strip()) >= cfg.MIN_SPAN_LENGTH:
                    sinais.append(Signal(
                        tipo=SignalType.RENDER_INVISIVEL, pagina=page_num,
                        trecho=texto.strip(),
                        detalhe=f"opacidade {alpha}/255 (praticamente transparente)",
                        bbox=tuple(bbox) if bbox else None,
                    ))

                # 4) fora da caixa visível da página
                if bbox:
                    x0, y0, x1, y1 = bbox
                    m = cfg.PAGE_BOUNDS_MARGIN
                    fora = (x1 < page_rect.x0 - m or x0 > page_rect.x1 + m or
                            y1 < page_rect.y0 - m or y0 > page_rect.y1 + m)
                    if fora and len(texto.strip()) >= cfg.MIN_SPAN_LENGTH:
                        sinais.append(Signal(
                            tipo=SignalType.FORA_DA_PAGINA, pagina=page_num,
                            trecho=texto.strip(),
                            detalhe=(f"posição {tuple(round(v,1) for v in bbox)} fora da "
                                     f"página {tuple(round(v,1) for v in page_rect)}"),
                            bbox=tuple(bbox),
                        ))
    return sinais


def _scan_render_mode(page, page_num: int, cfg: Config) -> list[Signal]:
    """Detecta texto em render mode 3 (invisível) — o modo usado legitimamente
    em OCR sobreposto, mas também para esconder comando sob imagem. Lê o stream
    de conteúdo bruto procurando o operador de modo de renderização '3 Tr'."""
    sinais: list[Signal] = []
    try:
        # Tr = text rendering mode; "3 Tr" = neither fill nor stroke (invisível)
        raw = page.read_contents()
        if raw and b"3 Tr" in raw:
            # confirma que há texto sendo desenhado em modo invisível;
            # sinaliza para inspeção (não é prova, mas é bandeira)
            ocorrencias = raw.count(b"3 Tr")
            sinais.append(Signal(
                tipo=SignalType.RENDER_INVISIVEL, pagina=page_num,
                trecho="(texto em modo de renderização invisível)",
                detalhe=(f"operador '3 Tr' presente {ocorrencias}x no stream — texto "
                         f"marcado como invisível; legítimo em OCR sobreposto, "
                         f"mas exige verificação"),
            ))
    except Exception:
        pass
    return sinais


def _scan_hidden_chars(page, page_num: int, cfg: Config) -> list[Signal]:
    """Caracteres de largura zero e controles Unicode na camada textual."""
    sinais: list[Signal] = []
    texto = page.get_text("text")
    achados: dict[str, int] = {}
    for ch in texto:
        if ch in ZERO_WIDTH_AND_CONTROL:
            achados[ch] = achados.get(ch, 0) + 1
    if achados:
        descr = ", ".join(
            f"U+{ord(ch):04X} ({unicodedata.name(ch, 'desconhecido')}) ×{n}"
            for ch, n in achados.items()
        )
        total = sum(achados.values())
        # alguns soft hyphens isolados podem ser legítimos; sinaliza com contexto
        sinais.append(Signal(
            tipo=SignalType.CARACTERE_OCULTO, pagina=page_num,
            trecho=descr,
            detalhe=f"{total} caractere(s) invisível/controle na camada textual",
        ))
    return sinais


# Marcadores que, se presentes num texto, indicam que ele e uma INSTRUCAO
# dirigida a um sistema de IA, e nao conteudo juridico legitimo. Bilingue
# porque um ataque pode vir em portugues (local) ou ingles (como em Greshake).
MARCADORES_INSTRUCAO = [
    "ignore previous", "ignore all previous", "disregard previous",
    "instrucoes anteriores", "instruções anteriores", "desconsidere as instrucoes",
    "ignore as instrucoes", "ignore as instruções", "esqueca as instrucoes",
    "a partir de agora", "from now on", "you must", "voce deve", "você deve",
    "system:", "system :", "you are now", "aja como", "act as", "pretend",
    "do not reveal", "nao revele", "não revele", "your new task",
    "sua nova tarefa", "developer mode", "modo desenvolvedor",
    "responda apenas", "respond only", "override",
]


def _texto_tem_instrucao(texto: str):
    """Retorna o primeiro marcador de instrucao encontrado, ou None. Busca em
    minusculas e tolerante a espacos. Nao e analise semantica, e varredura
    lexica de gatilhos conhecidos: marcador presente e SINAL para revisao."""
    baixo = " ".join(texto.lower().split())
    for m in MARCADORES_INSTRUCAO:
        if m in baixo:
            return m
    return None


def _scan_base64(page, page_num: int, cfg: Config) -> list[Signal]:
    """Detecta blocos Base64 que decodificam para TEXTO contendo instrucoes.

    CALIBRACAO CRITICA: pecas assinadas digitalmente contem blocos longos que
    PARECEM Base64 (certificados ICP-Brasil, carimbos de tempo, hashes). A
    defesa contra esse falso positivo NAO e o comprimento. E a cadeia de filtros:
      1) o bloco e sintaticamente Base64 e longo o suficiente;
      2) decodifica sem erro;
      3) o resultado e majoritariamente TEXTO IMPRIMIVEL (certificado decodifica
         para binario e e reprovado aqui);
      4) e esse texto contem um marcador de instrucao.
    Quem passa nos quatro vira sinal. Um certificado para no passo 3."""
    import base64 as _b64
    import re as _re

    sinais: list[Signal] = []
    texto_bruto = page.get_text("text")
    # O PDF frequentemente quebra um bloco Base64 com \n no meio (vimos isso em
    # teste real). Como o modelo decodifica ignorando espacos, juntamos o texto
    # removendo whitespace antes de procurar blocos. Isso recompoe sequencias
    # fragmentadas pela renderizacao e captura o ataque que de outro modo escaparia.
    texto = _re.sub(r"\s+", "", texto_bruto)

    padrao = _re.compile(r"[A-Za-z0-9+/]{%d,}={0,2}" % cfg.MIN_BASE64_LENGTH)
    for m in padrao.finditer(texto):
        bloco = m.group(0)
        # tolera padding ausente: Base64 valido tem len multiplo de 4; se faltam
        # 1-3 chars de padding, completamos com '=' antes de decodificar.
        resto = len(bloco) % 4
        if resto == 1:
            continue  # comprimento impossivel para Base64 valido
        if resto:
            bloco_pad = bloco + ("=" * (4 - resto))
        else:
            bloco_pad = bloco
        try:
            decodificado = _b64.b64decode(bloco_pad, validate=True)
        except Exception:
            continue
        if not decodificado:
            continue
        imprimiveis = sum(1 for byte in decodificado
                          if 32 <= byte < 127 or byte in (9, 10, 13))
        ratio = imprimiveis / len(decodificado)
        if ratio < cfg.MIN_DECODED_PRINTABLE_RATIO:
            continue
        texto_decod = decodificado.decode("utf-8", errors="ignore")
        marcador = _texto_tem_instrucao(texto_decod)
        if marcador:
            amostra = texto_decod.strip().replace("\n", " ")[:80]
            sinais.append(Signal(
                tipo=SignalType.BASE64_INSTRUCAO, pagina=page_num,
                trecho=amostra,
                detalhe=("bloco Base64 decodifica para texto com marcador de "
                         "instrucao ('" + marcador + "'); possivel injecao codificada"),
            ))
    return sinais


def _scan_instrucao_embutida(page, page_num: int, cfg: Config) -> list[Signal]:
    """Detecta, no texto VISIVEL, marcadores de instrucao dirigida a IA.

    FRONTEIRA DE ESCOPO: isto NAO julga o merito de argumentos. Um advogado
    escrever 'os argumentos do autor sao convincentes' e retorica legitima. O
    que dispara aqui e a linguagem de COMANDO A SISTEMA ('ignore as instrucoes
    anteriores', 'a partir de agora responda apenas') que nao tem funcao numa
    peca dirigida a um juiz humano. A presenca e SINAL para revisao, nao
    veredito; o destaque do trecho permite ao humano decidir."""
    sinais: list[Signal] = []
    texto = page.get_text("text")
    baixo = texto.lower()
    achados = 0
    for m in MARCADORES_INSTRUCAO:
        idx = baixo.find(m)
        if idx >= 0:
            ini = max(0, idx - 30)
            fim = min(len(texto), idx + len(m) + 50)
            contexto = texto[ini:fim].replace("\n", " ").strip()
            sinais.append(Signal(
                tipo=SignalType.INSTRUCAO_EMBUTIDA, pagina=page_num,
                trecho=contexto,
                detalhe=("marcador de comando a sistema de IA ('" + m + "') no "
                         "texto da peca; linguagem sem funcao em peca dirigida a humano"),
            ))
            achados += 1
            if achados >= 5:
                break
    return sinais


def _make_render_probe(page, cfg: Config):
    """Renderiza a página UMA vez e devolve uma sonda bbox -> (tem_tinta, frac).
    Compartilhada entre a checagem de cor camuflada e o teste de divergência,
    para não renderizar a mesma página duas vezes. Devolve (probe, ok)."""
    try:
        import fitz
        from PIL import Image
        import io
    except Exception:
        return (None, False)
    try:
        zoom = cfg.OCR_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except Exception:
        return (None, False)

    W, H = img.size
    px = img.load()
    fundo_ref = px[1, 1]

    def probe(bbox) -> tuple[bool, float]:
        x0, y0, x1, y1 = bbox
        ix0, iy0 = max(0, int(x0 * zoom)), max(0, int(y0 * zoom))
        ix1, iy1 = min(W, int(x1 * zoom)), min(H, int(y1 * zoom))
        if ix1 <= ix0 or iy1 <= iy0:
            return (False, 0.0)
        total = com_tinta = 0
        passo_x = max(1, (ix1 - ix0) // 40)
        passo_y = max(1, (iy1 - iy0) // 12)
        for yy in range(iy0, iy1, passo_y):
            for xx in range(ix0, ix1, passo_x):
                total += 1
                if _color_distance(px[xx, yy], fundo_ref) > cfg.MIN_COLOR_DISTANCE:
                    com_tinta += 1
        if total == 0:
            return (False, 0.0)
        frac = com_tinta / total
        return (frac > 0.02, frac)

    return (probe, True)


def _eh_conteudo_substantivo(texto: str) -> bool:
    """True se o trecho tem conteúdo linguístico real, não formatação. Filtra
    'leaders' de sumário (....), réguas, sequências de pontos/traços/espaços que
    são visualmente ralos por natureza e gerariam falso positivo no teste de
    tinta. Exige uma proporção mínima de caracteres alfabéticos."""
    if not texto:
        return False
    alfa = sum(1 for c in texto if c.isalpha())
    return alfa >= 4 and (alfa / len(texto)) >= 0.35


def _scan_divergence_with_probe(page, page_num: int, cfg: Config,
                                 probe) -> list[Signal]:
    """Teste forte usando a sonda já criada: span da camada digital cujo
    retângulo está visualmente vazio = texto invisível ao leitor humano.
    Ignora formatação (pontilhados de sumário etc.) que é rala por natureza."""
    sinais: list[Signal] = []
    data = page.get_text("dict", flags=11)
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                texto = span.get("text", "").strip()
                if len(texto) < cfg.MIN_SPAN_LENGTH:
                    continue
                if not _eh_conteudo_substantivo(texto):
                    continue  # formatação, não texto — não é injeção
                bbox = span.get("bbox")
                if not bbox:
                    continue
                tem_tinta, frac = probe(bbox)
                if not tem_tinta:
                    sinais.append(Signal(
                        tipo=SignalType.DIVERGENCIA_OCR, pagina=page_num,
                        trecho=texto,
                        detalhe=(f"camada digital contém este texto, mas a região "
                                 f"renderizada está vazia ({frac:.1%} de tinta) — "
                                 f"texto invisível ao leitor humano"),
                        bbox=tuple(bbox),
                    ))
    return sinais


def _scan_ocr_divergence(page, page_num: int, cfg: Config) -> tuple[list[Signal], bool]:
    """TESTE FORTE — verificação POSICIONAL (não por OCR de tokens).

    A versão ingênua (comparar tokens lidos pelo OCR com os da camada digital)
    é frágil: o OCR erra acentos e palavras longas, gerando falsos positivos em
    texto perfeitamente visível. A injeção fantasma, porém, é LOCAL — vive numa
    caixa específica da página. Então o teste correto é geométrico, não textual:

    para cada span de texto da camada digital, renderizamos a página e medimos
    se a região correspondente à caixa do span de fato contém tinta (pixels
    distintos do fundo). Se a camada digital afirma 'há texto aqui' mas a imagem
    mostra fundo liso naquela caixa, o texto é invisível ao olho humano — e isso
    independe de o OCR ter lido certo qualquer outra coisa.

    Determinístico, imune a ruído de reconhecimento, e localiza o trecho.
    Devolve (sinais, teste_executado)."""
    try:
        import fitz
        from PIL import Image
        import io
    except Exception:
        return ([Signal(
            tipo=SignalType.OCR_INDISPONIVEL, pagina=page_num,
            trecho="", detalhe="dependências de imagem ausentes; teste forte não executado",
        )], False)

    try:
        zoom = cfg.OCR_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except Exception as e:
        return ([Signal(
            tipo=SignalType.OCR_INDISPONIVEL, pagina=page_num,
            trecho="", detalhe=f"falha ao renderizar página: {e}",
        )], False)

    W, H = img.size
    px = img.load()

    def regiao_tem_tinta(bbox, fundo_ref) -> tuple[bool, float]:
        """Amostra a caixa (em coords de página) na imagem renderizada e retorna
        (tem_tinta, fracao_de_pixels_com_tinta). 'Tinta' = pixel suficientemente
        distante do fundo local — ou seja, algo visível foi desenhado ali."""
        x0, y0, x1, y1 = bbox
        # converte coords de página (pt) → pixels da imagem
        ix0, iy0 = max(0, int(x0 * zoom)), max(0, int(y0 * zoom))
        ix1, iy1 = min(W, int(x1 * zoom)), min(H, int(y1 * zoom))
        if ix1 <= ix0 or iy1 <= iy0:
            return (False, 0.0)
        total = 0
        com_tinta = 0
        # amostragem em grade para não percorrer todos os pixels (custo)
        passo_x = max(1, (ix1 - ix0) // 40)
        passo_y = max(1, (iy1 - iy0) // 12)
        for yy in range(iy0, iy1, passo_y):
            for xx in range(ix0, ix1, passo_x):
                total += 1
                if _color_distance(px[xx, yy], fundo_ref) > cfg.MIN_COLOR_DISTANCE:
                    com_tinta += 1
        if total == 0:
            return (False, 0.0)
        frac = com_tinta / total
        return (frac > 0.02, frac)  # 2% de pixels com tinta = há algo visível

    # fundo de referência = canto superior esquerdo da imagem renderizada
    fundo_ref = px[1, 1]

    data = page.get_text("dict", flags=11)
    sinais: list[Signal] = []
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                texto = span.get("text", "").strip()
                if len(texto) < cfg.MIN_SPAN_LENGTH:
                    continue
                bbox = span.get("bbox")
                if not bbox:
                    continue
                tem_tinta, frac = regiao_tem_tinta(bbox, fundo_ref)
                if not tem_tinta:
                    # camada digital tem texto substancial; imagem não mostra nada
                    sinais.append(Signal(
                        tipo=SignalType.DIVERGENCIA_OCR, pagina=page_num,
                        trecho=texto,
                        detalhe=(f"camada digital contém este texto, mas a região "
                                 f"correspondente da página renderizada está vazia "
                                 f"({frac:.1%} de pixels com tinta) — texto invisível "
                                 f"ao leitor humano"),
                        bbox=tuple(bbox),
                    ))
    return (sinais, True)


# ───────────────────────────── Orquestração ─────────────────────────────

def _consolidar_risco(sinais: list[Signal]) -> RiskLevel:
    """Política de risco. Conservadora por desenho: a divergencia OCR e a cor
    camuflada são os sinais mais confiáveis e, sozinhos, já elevam a alto risco.
    Sinais mais ruidosos (caractere oculto isolado) ficam em suspeito.

    NOTA sobre instrucao_embutida: este sinal opera por lexico puro (busca por
    marcadores como 'ignore previous'), e nao distingue MENCAO de USO. Um artigo
    juridico que CITE doutrina sobre prompt injection o dispara, sem que haja
    ataque. Por isso ele NAO entra no calculo do nivel de risco: e reportado
    separadamente como observacao de triagem para o revisor humano (ver
    ScanResult.observacoes). O nivel de risco reflete apenas sinais de OCULTACAO,
    que sao determinis­ticos e confiaveis. A linguagem de comando visivel e
    materia de contraditorio, nao de bloqueio automatico."""
    # considera apenas sinais que NAO sejam instrucao embutida
    sinais_risco = [s for s in sinais if s.tipo != SignalType.INSTRUCAO_EMBUTIDA]
    if not sinais_risco:
        return RiskLevel.LIMPO

    tipos = {s.tipo for s in sinais_risco}
    fortes = {SignalType.DIVERGENCIA_OCR, SignalType.COR_CAMUFLADA,
              SignalType.FONTE_MINUSCULA, SignalType.FORA_DA_PAGINA,
              SignalType.BASE64_INSTRUCAO}
    # Base64 que decodifica para instrucao passou por quatro filtros: e altamente
    # especifico e raro em falso positivo, logo trata-se como sinal forte.
    if tipos & fortes:
        return RiskLevel.ALTO_RISCO
    if SignalType.RENDER_INVISIVEL in tipos or SignalType.CARACTERE_OCULTO in tipos:
        return RiskLevel.SUSPEITO
    return RiskLevel.SUSPEITO


def scan_pdf(caminho: str, cfg: Optional[Config] = None,
             usar_ocr: bool = True) -> ScanResult:
    """Ponto de entrada. Inspeciona um PDF e devolve o resultado estruturado.

    caminho   : path do PDF a inspecionar
    cfg       : limiares (usa padrão se None)
    usar_ocr  : liga/desliga o teste forte de divergência OCR (custa render+OCR)
    """
    import fitz
    cfg = cfg or Config()
    resultado = ScanResult(arquivo=caminho, risco=RiskLevel.LIMPO)

    try:
        doc = fitz.open(caminho)
    except Exception as e:
        resultado.erro = f"não foi possível abrir o PDF: {e}"
        resultado.risco = RiskLevel.SUSPEITO  # arquivo ilegível é, por si, suspeito
        return resultado

    ocr_global = False
    try:
        for i, page in enumerate(doc):
            page_num = i + 1
            bg = _estimate_page_background(page)

            # renderiza a página uma vez (se usar_ocr) e compartilha a sonda
            probe = None
            if usar_ocr:
                probe, ok = _make_render_probe(page, cfg)
                ocr_global = ocr_global or ok
                if not ok:
                    resultado.sinais.append(Signal(
                        tipo=SignalType.OCR_INDISPONIVEL, pagina=page_num,
                        trecho="", detalhe="não foi possível renderizar a página; "
                                           "teste forte não executado"))

            resultado.sinais.extend(_scan_spans(page, page_num, bg, cfg, render_probe=probe))
            resultado.sinais.extend(_scan_render_mode(page, page_num, cfg))
            resultado.sinais.extend(_scan_hidden_chars(page, page_num, cfg))
            resultado.sinais.extend(_scan_base64(page, page_num, cfg))
            resultado.sinais.extend(_scan_instrucao_embutida(page, page_num, cfg))

            if probe is not None:
                resultado.sinais.extend(
                    _scan_divergence_with_probe(page, page_num, cfg, probe))

            resultado.paginas_analisadas = page_num
    finally:
        doc.close()

    resultado.ocr_executado = ocr_global
    resultado.risco = _consolidar_risco(resultado.sinais)
    return resultado


# ───────────────────────────── CLI ─────────────────────────────

def _main():
    import argparse
    import json
    import sys

    p = argparse.ArgumentParser(
        description="Detector determinístico de injeção fantasma em PDFs (TJMG/GEX-IA)."
    )
    p.add_argument("pdf", nargs="+", help="um ou mais PDFs a inspecionar")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    p.add_argument("--sem-ocr", action="store_true",
                   help="desliga o teste forte de divergência OCR (mais rápido)")
    p.add_argument("--cor", type=float, default=None, help="limiar de distância de cor")
    p.add_argument("--fonte", type=float, default=None, help="limiar de tamanho de fonte")
    args = p.parse_args()

    cfg = Config()
    if args.cor is not None:
        cfg.MIN_COLOR_DISTANCE = args.cor
    if args.fonte is not None:
        cfg.MIN_FONT_SIZE = args.fonte

    resultados = [scan_pdf(c, cfg=cfg, usar_ocr=not args.sem_ocr) for c in args.pdf]

    if args.json:
        print(json.dumps([r.to_dict() for r in resultados], ensure_ascii=False, indent=2))
    else:
        for r in resultados:
            print(r.resumo())
            print("─" * 60)

    # código de saída: 2 se algum alto risco, 1 se algum suspeito, 0 se tudo limpo
    if any(r.risco == RiskLevel.ALTO_RISCO for r in resultados):
        sys.exit(2)
    if any(r.risco == RiskLevel.SUSPEITO for r in resultados):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    _main()
