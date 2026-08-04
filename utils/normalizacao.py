"""Normalização de texto e nomes usada em toda a base para comparações consistentes."""
import re
import unicodedata

_PARENTESES_RE = re.compile(r"\([^)]*\)")
_NAO_LETRA_RE = re.compile(r"[^A-Z\s]")
_ESPACOS_RE = re.compile(r"\s+")
_SUFIXOS_RE = re.compile(r"\b(REALOCADO|REALOCADA)\b")


def remover_acentos(texto: str) -> str:
    forma = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in forma if not unicodedata.combining(c))


def normalizar_nome(nome: str) -> str:
    """Converte um nome para a forma canônica usada em todas as comparações de match.

    Regras: maiúsculo, remove trechos entre parênteses (tags como (B2C), (KA)),
    remove acentos, remove sufixos administrativos como "- REALOCADO",
    remove qualquer caractere que não seja letra/espaço, colapsa espaços.
    O nome original (para exibição) deve ser mantido em outro campo, esta função
    nunca deve substituir o valor original.
    """
    if nome is None:
        return ""
    texto = str(nome).strip().upper()
    texto = _PARENTESES_RE.sub(" ", texto)
    texto = remover_acentos(texto)
    texto = _SUFIXOS_RE.sub(" ", texto)
    texto = _NAO_LETRA_RE.sub(" ", texto)
    texto = _ESPACOS_RE.sub(" ", texto).strip()
    return texto


def normalizar_texto(valor) -> str:
    """Limpeza leve para campos de texto genéricos (cargo, e-mail, etc.): strip + colapso de espaços."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    texto = _ESPACOS_RE.sub(" ", texto)
    return texto


def esta_vazio(valor) -> bool:
    if valor is None:
        return True
    texto = str(valor).strip()
    return texto == "" or texto.lower() == "nan"
