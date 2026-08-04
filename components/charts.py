"""Helpers Plotly com a identidade visual dark BRIDA (paleta validada para acessibilidade)."""
import plotly.graph_objects as go
import streamlit as st

from components.theme import CORES


def mostrar(fig: go.Figure, altura: int | None = None, ocultar_rotulos_x: bool = False):
    """Exibe o gráfico com altura fixa.

    Streamlit 1.59 pode reaplicar tema Plotly e devolver rótulos do eixo X;
    por isso, quando solicitado, o eixo X é ocultado por completo (valores
    continuam no texto da barra e no hover).
    """
    h = int(altura if altura is not None else (fig.layout.height or 400))
    if ocultar_rotulos_x:
        fig.for_each_xaxis(lambda eixo: eixo.update(
            visible=False,  # remove ticks, números e linha do eixo X
        ))
    st.plotly_chart(
        fig,
        width="stretch",
        height=h,
        config={"displayModeBar": False},
        theme=None,
    )

_FONTE = "system-ui, -apple-system, 'Segoe UI', sans-serif"
_RAIO_BARRA = 6  # cantos arredondados nas barras — acabamento premium, consistente em todos os gráficos


def _aplicar_layout_padrao(fig: go.Figure, titulo: str = "", altura: int = 360) -> go.Figure:
    fig.update_layout(
        # mesmo tom pro card e pro fundo do gráfico — fundo do gráfico diferente
        # do card cria uma "emenda" visual (a moldura de uma cor, o miolo de outra).
        paper_bgcolor=CORES["fundo_card"],
        plot_bgcolor=CORES["fundo_card"],
        font=dict(color=CORES["texto_secundario"], family=_FONTE, size=12),
        margin=dict(l=10, r=10, t=40 if titulo else 10, b=10),
        height=altura,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=CORES["texto_secundario"])),
        hoverlabel=dict(bgcolor=CORES["fundo_card_alt"], font=dict(color=CORES["texto_primario"])),
        # separador brasileiro em todos os números do gráfico (eixo e hover):
        # milhar '.', decimal ',' — ex.: 3.940 em vez de 3,940
        separators=",.",
    )
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14, color=CORES["texto_primario"], family=_FONTE)))
    # sem grade (nem vertical nem horizontal) — só a linha de base do eixo
    fig.update_xaxes(showgrid=False, linecolor=CORES["eixo"], zerolinecolor=CORES["eixo"])
    fig.update_yaxes(showgrid=False, linecolor=CORES["eixo"], zerolinecolor=CORES["eixo"])
    return fig


def barra_horizontal(
    categorias: list[str], valores: list[float], titulo: str = "",
    cor: str | None = None, altura: int | None = None,
    cores: list[str] | None = None, textos: list[str] | None = None,
) -> go.Figure:
    """Ranking de uma única medida por categoria.

    Por padrão usa uma única cor (`cor`) — para gráficos de QUANTIDADE, que não
    têm faixa de desempenho. Para gráficos de TAXA/desempenho, passe `cores`
    (uma cor por categoria, normalmente via charts.cor_por_taxa). `textos`
    permite rótulos já formatados (ex.: '59,7%') no lugar do valor numérico cru.
    """
    cor_unica = cor or CORES["accent"]
    itens = list(zip(
        categorias, valores,
        cores if cores is not None else [cor_unica] * len(categorias),
        textos if textos is not None else valores,
    ))
    itens.sort(key=lambda item: item[1])
    cats_ord, vals_ord, cores_ord, textos_ord = zip(*itens) if itens else ([], [], [], [])
    fig = go.Figure(
        go.Bar(
            x=list(vals_ord), y=list(cats_ord), orientation="h",
            marker=dict(color=list(cores_ord), cornerradius=_RAIO_BARRA), text=list(textos_ord), textposition="outside",
            textfont=dict(color=CORES["texto_primario"]),
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    h = altura if altura is not None else max(280, 34 * max(len(cats_ord), 1))
    fig = _aplicar_layout_padrao(fig, titulo, altura=h)
    # margem esquerda compacta para caber em colunas lado a lado
    maior_rotulo = max((len(str(c)) for c in cats_ord), default=10)
    maior_valor = max(vals_ord, default=1) or 1
    fig.update_layout(margin=dict(l=min(150, max(80, maior_rotulo * 6)), r=48, t=40 if titulo else 10, b=8))
    # valor já aparece no fim da barra + hover — eixo X numérico é redundante
    fig.update_xaxes(range=[0, maior_valor * 1.35], visible=False)
    # eixo Y categórico: sem grade horizontal entre categorias (poluição visual)
    fig.update_yaxes(automargin=True, ticklabelposition="outside left", showgrid=False)
    return fig


def barra_horizontal_dupla(
    cats_esq: list[str], vals_esq: list[float],
    cats_dir: list[str], vals_dir: list[float],
    altura: int = 400,
    cores_esq: list[str] | None = None, textos_esq: list[str] | None = None,
    cores_dir: list[str] | None = None, textos_dir: list[str] | None = None,
) -> go.Figure:
    """Dois rankings horizontais na MESMA figura — base inferior sempre alinhada.

    Sem `cores_esq`/`cores_dir` cada lado usa uma única cor (azul, quantidade);
    passe uma lista (ex.: charts.cor_por_taxa por item) para gráficos de taxa.
    `textos_esq`/`textos_dir` permitem rótulos já formatados no lugar do valor cru.
    """
    from plotly.subplots import make_subplots

    cor_padrao = CORES["accent"]

    def _ordenar(cats, vals, cores_in, textos_in):
        itens = list(zip(
            cats, vals,
            cores_in if cores_in is not None else [cor_padrao] * len(cats),
            textos_in if textos_in is not None else vals,
        ))
        itens.sort(key=lambda item: item[1])
        if not itens:
            return [], [], [], []
        c, v, co, t = zip(*itens)
        return list(c), list(v), list(co), list(t)

    c1, v1, co1, t1 = _ordenar(cats_esq, vals_esq, cores_esq, textos_esq)
    c2, v2, co2, t2 = _ordenar(cats_dir, vals_dir, cores_dir, textos_dir)

    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.16)
    fig.add_trace(
        go.Bar(
            x=v1, y=c1, orientation="h", marker=dict(color=co1, cornerradius=_RAIO_BARRA),
            text=t1, textposition="outside",
            textfont=dict(color=CORES["texto_primario"]),
            hovertemplate="%{y}: %{text}<extra></extra>", showlegend=False,
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=v2, y=c2, orientation="h", marker=dict(color=co2, cornerradius=_RAIO_BARRA),
            text=t2, textposition="outside",
            textfont=dict(color=CORES["texto_primario"]),
            hovertemplate="%{y}: %{text}<extra></extra>", showlegend=False,
        ),
        row=1, col=2,
    )
    fig = _aplicar_layout_padrao(fig, "", altura=altura)
    fig.update_layout(margin=dict(l=10, r=40, t=10, b=8))
    for col, vals in ((1, v1), (2, v2)):
        maior = max(vals, default=1) or 1
        fig.update_xaxes(range=[0, maior * 1.35], visible=False, row=1, col=col)
        fig.update_yaxes(automargin=True, ticklabelposition="outside left", showgrid=False, row=1, col=col)
    fig.for_each_xaxis(lambda eixo: eixo.update(visible=False))
    return fig


def rosca(labels: list[str], valores: list[float], titulo: str = "") -> go.Figure:
    cores = (CORES["categorica"] * ((len(labels) // len(CORES["categorica"])) + 1))[: len(labels)]
    fig = go.Figure(
        go.Pie(
            labels=labels, values=valores, hole=0.62, marker=dict(colors=cores, line=dict(color=CORES["fundo_card"], width=2)),
            textinfo="label+percent", textfont=dict(color=CORES["texto_primario"]),
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    total = sum(valores)
    fig.add_annotation(text=f"<b>{total}</b><br><span style='font-size:11px'>Total</span>", x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=CORES["texto_primario"]))
    return _aplicar_layout_padrao(fig, titulo)


def barras_empilhadas(categorias: list[str], series: dict[str, list[float]], titulo: str = "") -> go.Figure:
    fig = go.Figure()
    for i, (nome_serie, valores) in enumerate(series.items()):
        cor = CORES["categorica"][i % len(CORES["categorica"])]
        fig.add_trace(go.Bar(name=nome_serie, x=categorias, y=valores, marker=dict(color=cor, cornerradius=_RAIO_BARRA)))
    fig.update_layout(barmode="stack")
    return _aplicar_layout_padrao(fig, titulo)


def linha(x: list, y: list, titulo: str = "", cor: str | None = None) -> go.Figure:
    cor = cor or CORES["accent"]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", line=dict(color=cor, width=2), marker=dict(size=7, color=cor)))
    return _aplicar_layout_padrao(fig, titulo)


def cabecalho(titulo: str, subtitulo: str = ""):
    """Título + subtítulo explicativo acima de um gráfico, em uma única chamada
    (mesmo motivo do components.cards.card: HTML dividido em várias st.markdown
    não fecha corretamente as tags)."""
    sub_html = f'<div style="color:{CORES["texto_secundario"]};font-size:0.82rem;margin-top:2px;">{subtitulo}</div>' if subtitulo else ""
    st.markdown(
        f'<div style="margin-bottom:.4rem;">'
        f'<div style="color:{CORES["texto_primario"]};font-weight:700;font-size:1.05rem;">{titulo}</div>'
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )


def cor_por_taxa(taxa: float) -> str:
    """Faixas de desempenho: verde >=90%, azul 70-89%, laranja 40-69%, vermelho <40%."""
    if taxa >= 90:
        return CORES["status_bom"]
    if taxa >= 70:
        return CORES["accent"]
    if taxa >= 40:
        return CORES["categorica"][1]
    return CORES["status_critico"]


def ranking_horizontal(
    rotulos: list[str], valores: list[float], cores: list[str] | None = None,
    textos_barra: list[str] | None = None, hovertexts: list[str] | None = None,
    altura: int | None = None, sufixo_eixo_x: str = "",
) -> go.Figure:
    """Barra horizontal genérica com cor por barra, texto customizado ao final da
    barra e hover customizado. Espera os dados já ordenados pelo chamador (item 1
    da lista aparece no TOPO do gráfico — por isso a inversão abaixo)."""
    rotulos_r = list(reversed(rotulos))
    valores_r = list(reversed(valores))
    cores_r = list(reversed(cores)) if cores else CORES["accent"]
    textos_r = list(reversed(textos_barra)) if textos_barra else valores_r
    hover_r = list(reversed(hovertexts)) if hovertexts else None

    maior_rotulo = max((len(r) for r in rotulos_r), default=10)
    margem_esquerda = min(300, max(110, maior_rotulo * 7))
    maior_texto = max((len(str(t)) for t in textos_r), default=4)
    # margem generosa: estes gráficos também aparecem lado a lado (metade da
    # largura), onde o mesmo texto ocupa uma fatia proporcionalmente maior
    margem_direita = min(240, max(90, maior_texto * 9))

    fig = go.Figure(
        go.Bar(
            x=valores_r, y=rotulos_r, orientation="h",
            marker=dict(color=cores_r, cornerradius=_RAIO_BARRA),
            text=textos_r, textposition="outside",
            textfont=dict(color=CORES["texto_primario"], size=11),
            hovertext=hover_r, hoverinfo="text" if hover_r else "x+y",
        )
    )
    altura = altura or max(320, 36 * len(rotulos_r) + 40)
    fig = _aplicar_layout_padrao(fig, "", altura=altura)
    fig.update_layout(margin=dict(l=margem_esquerda, r=margem_direita, t=10, b=10))
    # eixo Y é categórico (nomes) — grade horizontal entre categorias só suja
    # a leitura, o próprio espaçamento das barras já separa as categorias.
    fig.update_yaxes(showgrid=False)

    # o valor já aparece no fim de cada barra (e no hover) — o eixo X numérico
    # é sempre redundante aqui, e é a origem recorrente de corte de rótulo em
    # colunas lado a lado. Por isso ele fica oculto por completo (mesmo padrão
    # já usado em barra_horizontal), só a folga do range continua garantindo
    # espaço para o texto "outside" da maior barra não ser cortado.
    maior_valor = max(valores_r, default=1) or 1
    fig.update_xaxes(range=[0, maior_valor * 1.5], visible=False)
    return fig
