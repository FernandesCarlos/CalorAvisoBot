
import io
import math
import datetime
from collections import Counter

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import MaxNLocator


# =========================================================
# PALETA VISUAL
# =========================================================

CORES = {
    "fundo": "#F3F6FB",
    "cabecalho": "#1D2D50",
    "primaria": "#536DFE",
    "destaque": "#FF8066",
    "verde": "#1D9B84",
    "roxo": "#9B72CF",
    "texto": "#25324A",
    "secundario": "#4B556B",
    "borda": "#E0E5EF",
    "branco": "#FFFFFF",
    "texto_claro": "#E8EEFA",
    "linha": "#E0E5EF",
}


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def _parse_datetime(valor):
    """Converte os formatos de data aceitos pelo relatório."""

    if isinstance(valor, datetime.datetime):
        return valor

    if isinstance(valor, datetime.date):
        return datetime.datetime.combine(
            valor, datetime.time.min
        )

    texto = str(valor or "").strip()

    if not texto:
        return None

    try:
        return datetime.datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        )
    except ValueError:
        pass

    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    )

    for formato in formatos:
        try:
            return datetime.datetime.strptime(
                texto, formato
            )
        except ValueError:
            continue

    return None


def _numero(valor):
    """Converte um valor para número, ignorando valores inválidos."""

    if valor is None or str(valor).strip() == "":
        return None

    try:
        resultado = float(valor)

        if math.isfinite(resultado):
            return resultado

    except (TypeError, ValueError):
        pass

    return None


def _adicionar_cartao(
    fig,
    x,
    y,
    largura,
    altura,
    cor=None,
):
    """
    Desenha um cartão dentro das coordenadas da figura.
    As coordenadas x, y, largura e altura variam de 0 a 1.
    """

    cartao = FancyBboxPatch(
        (x, y),
        largura,
        altura,
        boxstyle="round,pad=0.004,rounding_size=0.012",
        transform=fig.transFigure,
        facecolor=CORES["branco"],
        edgecolor=CORES["borda"],
        linewidth=0.9,
        zorder=0,
        clip_on=False,
    )

    fig.add_artist(cartao)

    # Faixa colorida decorativa, dentro do cartão
    if cor:
        faixa = FancyBboxPatch(
            (x + 0.014, y + 0.015),
            0.006,
            altura - 0.030,
            boxstyle="round,pad=0.001,rounding_size=0.003",
            transform=fig.transFigure,
            facecolor=cor,
            edgecolor="none",
            zorder=1,
            clip_on=False,
        )

        fig.add_artist(faixa)


# =========================================================
# CÁLCULO DAS ESTATÍSTICAS
# =========================================================

def calcular_estatisticas(dados):

    diarios = dados.get("diarios", [])
    avulsos = dados.get("avulsos", [])

    # -----------------------------------------------------
    # Período de acompanhamento
    # -----------------------------------------------------

    data_inicio = _parse_datetime(
        dados.get("data_cadastro")
    )

    if data_inicio:
        agora = datetime.datetime.now(
            data_inicio.tzinfo
        )

        dias_analisados = max(
            1,
            (agora - data_inicio).days
        )
    else:
        dias_analisados = 1

    # -----------------------------------------------------
    # Quantidade de calores por data
    # -----------------------------------------------------

    calores_por_data = {}
    total_calores = 0
    horarios_avulsos = []

    for registro in diarios:

        if not registro:
            continue

        data_registro = _parse_datetime(
            registro[0]
        )

        valor = (
            _numero(registro[1])
            if len(registro) > 1
            else None
        )

        quantidade = (
            valor if valor is not None else 0
        )

        total_calores += quantidade

        if data_registro:
            data = data_registro.strftime(
                "%Y-%m-%d"
            )

            calores_por_data[data] = (
                calores_por_data.get(data, 0)
                + quantidade
            )

    # Cada registro avulso representa um episódio
    for registro in avulsos:

        if not registro:
            continue

        data_registro = _parse_datetime(
            registro[0]
        )

        if not data_registro:
            continue

        data = data_registro.strftime(
            "%Y-%m-%d"
        )

        calores_por_data[data] = (
            calores_por_data.get(data, 0) + 1
        )

        total_calores += 1

        horarios_avulsos.append(
            data_registro.hour
        )

    media_calores = (
        total_calores / dias_analisados
    )

    # -----------------------------------------------------
    # Horário mais frequente
    # -----------------------------------------------------

    horario_frequente = "Sem dados"

    if horarios_avulsos:

        hora = Counter(
            horarios_avulsos
        ).most_common(1)[0][0]

        proxima_hora = (hora + 1) % 24

        horario_frequente = (
            f"{hora:02d}h–{proxima_hora:02d}h"
        )

    # -----------------------------------------------------
    # Qualidade do sono e humor
    # -----------------------------------------------------

    valores_sono = []
    valores_humor = []

    for registro in diarios:

        if len(registro) < 4:
            continue

        sono = _numero(registro[2])
        humor = _numero(registro[3])

        if sono is not None:
            valores_sono.append(sono)

        if humor is not None:
            valores_humor.append(humor)

    desc_sono = "Sem dados"
    desc_humor = "Sem dados"

    if valores_sono:

        media_sono = (
            sum(valores_sono)
            / len(valores_sono)
        )

        if media_sono < 1.6:
            desc_sono = "Ruim"
        elif media_sono < 2.4:
            desc_sono = "Razoável"
        else:
            desc_sono = "Boa"

    if valores_humor:

        media_humor = (
            sum(valores_humor)
            / len(valores_humor)
        )

        if media_humor < 1.6:
            desc_humor = "Baixo/Mal"
        elif media_humor < 2.4:
            desc_humor = "Normal"
        else:
            desc_humor = "Bom"

    # -----------------------------------------------------
    # Últimas sete datas com registros
    # -----------------------------------------------------

    datas_ordenadas = sorted(
        calores_por_data.keys()
    )

    datas = datas_ordenadas[-7:]

    valores = [
        calores_por_data[data]
        for data in datas
    ]

    return {
        "dias_analisados": dias_analisados,
        "media_calores": round(
            media_calores, 1
        ),
        "horario_frequente": horario_frequente,
        "sono": desc_sono,
        "humor": desc_humor,
        "datas": datas,
        "valores": valores,
    }


# =========================================================
# GERAÇÃO DO RELATÓRIO PNG
# =========================================================

def gerar_png_relatorio(dados):

    estatisticas = calcular_estatisticas(
        dados
    )

    nome = str(
        dados.get("apelido") or "Paciente"
    ).strip().capitalize()

    media = (
        f"{estatisticas['media_calores']:.1f}"
        .replace(".", ",")
    )

    # Figura vertical com mais espaço entre as seções
    fig = plt.figure(
        figsize=(8, 11.5),
        facecolor=CORES["fundo"],
    )

    # =====================================================
    # 1. CABEÇALHO
    # =====================================================

    cabecalho = fig.add_axes(
        [0, 0.86, 1, 0.14]
    )

    cabecalho.set_facecolor(
        CORES["cabecalho"]
    )

    cabecalho.set_xticks([])
    cabecalho.set_yticks([])

    for borda in cabecalho.spines.values():
        borda.set_visible(False)

    fig.text(
        0.07, 0.965,
        "RELATÓRIO DE ACOMPANHAMENTO",
        fontsize=11,
        weight="bold",
        color=CORES["texto_claro"],
        va="center",
    )

    fig.text(
        0.07, 0.921,
        f"Olá, {nome}!",
        fontsize=29,
        weight="bold",
        color=CORES["branco"],
        va="center",
    )

    data_geracao = datetime.datetime.now().strftime(
        "%d/%m/%Y"
    )

    fig.text(
        0.07, 0.878,
        (
            f"Acompanhamento há "
            f"{estatisticas['dias_analisados']} dias"
            f"  |  Gerado em {data_geracao}"
        ),
        fontsize=12,
        color=CORES["texto_claro"],
        va="center",
    )

    # =====================================================
    # 2. INDICADORES EM CARTÕES: DUAS COLUNAS
    # =====================================================

    fig.text(
        0.06, 0.829,
        "RESUMO DO ACOMPANHAMENTO",
        fontsize=13,
        weight="bold",
        color=CORES["texto"],
        va="center",
    )

    indicadores = [
        (
            "MÉDIA DE CALORES",
            f"{media} por dia",
            CORES["destaque"],
        ),
        (
            "HORÁRIO FREQUENTE",
            estatisticas["horario_frequente"],
            CORES["primaria"],
        ),
        (
            "QUALIDADE DO SONO",
            estatisticas["sono"],
            CORES["verde"],
        ),
        (
            "HUMOR PREDOMINANTE",
            estatisticas["humor"],
            CORES["roxo"],
        ),
    ]

    # Cartões mais largos, organizados em duas linhas
    largura_cartao = 0.425
    altura_cartao = 0.105

    posicoes_cartoes = [
        (0.06, 0.690),
        (0.515, 0.690),
        (0.06, 0.565),
        (0.515, 0.565),
    ]

    for (
        titulo,
        valor,
        cor,
    ), (
        x,
        y,
    ) in zip(
        indicadores,
        posicoes_cartoes,
    ):

        _adicionar_cartao(
            fig,
            x,
            y,
            largura_cartao,
            altura_cartao,
            cor,
        )

        # Título alinhado dentro dos limites do cartão
        fig.text(
            x + 0.035,
            y + 0.073,
            titulo,
            fontsize=10,
            weight="bold",
            color=CORES["secundario"],
            va="center",
        )

        # Valor em uma linha separada para evitar sobreposição
        fig.text(
            x + 0.035,
            y + 0.035,
            valor,
            fontsize=15,
            weight="bold",
            color=CORES["texto"],
            va="center",
        )

    # =====================================================
    # 3. GRÁFICO
    # =====================================================

    _adicionar_cartao(
        fig,
        0.06,
        0.300,
        0.88,
        0.235,
    )

    fig.text(
        0.095, 0.497,
        "Calores registrados",
        fontsize=15,
        weight="bold",
        color=CORES["texto"],
        va="center",
    )

    fig.text(
        0.095, 0.466,
        "Evolução dos últimos dias com registros",
        fontsize=11,
        color=CORES["secundario"],
        va="center",
    )

    # O gráfico fica totalmente dentro do cartão
    grafico_ax = fig.add_axes(
        [0.12, 0.335, 0.76, 0.105]
    )

    grafico_ax.set_facecolor("none")

    if estatisticas["datas"]:

        valores = estatisticas["valores"]

        datas_formatadas = [
            datetime.datetime.strptime(
                data, "%Y-%m-%d"
            ).strftime("%d/%m")
            for data in estatisticas["datas"]
        ]

        posicoes = list(
            range(len(valores))
        )

        cores_barras = [
            CORES["primaria"]
            for _ in valores
        ]

        # Destaque do registro mais recente
        cores_barras[-1] = CORES["destaque"]

        barras = grafico_ax.bar(
            posicoes,
            valores,
            color=cores_barras,
            width=0.58,
            zorder=3,
        )

        grafico_ax.set_xticks(
            posicoes
        )

        grafico_ax.set_xticklabels(
            datas_formatadas
        )

        maior_valor = max(valores)

        grafico_ax.set_ylim(
            0,
            max(1, maior_valor * 1.35),
        )

        grafico_ax.yaxis.set_major_locator(
            MaxNLocator(
                nbins=4,
                integer=True,
            )
        )

        if maior_valor > 0:

            grafico_ax.bar_label(
                barras,
                labels=[
                    f"{v:g}"
                    for v in valores
                ],
                padding=3,
                fontsize=10,
                color=CORES["texto"],
            )

        grafico_ax.grid(
            axis="y",
            color=CORES["linha"],
            linewidth=0.8,
            zorder=0,
        )

        grafico_ax.set_axisbelow(True)

        grafico_ax.tick_params(
            axis="x",
            labelsize=10,
            colors=CORES["secundario"],
            length=0,
            pad=5,
        )

        grafico_ax.tick_params(
            axis="y",
            labelsize=9,
            colors=CORES["secundario"],
            length=0,
            pad=4,
        )

        for lado in [
            "top",
            "right",
            "left",
            "bottom",
        ]:
            grafico_ax.spines[
                lado
            ].set_visible(False)

    else:

        grafico_ax.axis("off")

        grafico_ax.text(
            0.5, 0.5,
            "Ainda não há registros no diário",
            ha="center",
            va="center",
            fontsize=12,
            color=CORES["secundario"],
            transform=grafico_ax.transAxes,
        )

    # =====================================================
    # 4. PERGUNTAS PARA A CONSULTA
    # =====================================================

    _adicionar_cartao(
        fig,
        0.06,
        0.075,
        0.88,
        0.190,
        CORES["verde"],
    )

    fig.text(
        0.095, 0.233,
        "PERGUNTAS PARA LEVAR À CONSULTA",
        fontsize=12,
        weight="bold",
        color=CORES["texto"],
        va="center",
    )

    perguntas = [
        "Os meus calores estão dentro do esperado para a minha fase?",
        "Existe algo que eu possa fazer para melhorar o sono?",
        "Esses sintomas justificam avaliar opções de tratamento?",
    ]

    posicoes_y = [
        0.194,
        0.151,
        0.108,
    ]

    for pergunta, y in zip(
        perguntas,
        posicoes_y,
    ):

        fig.text(
            0.095,
            y,
            f"•  {pergunta}",
            fontsize=10.5,
            color=CORES["secundario"],
            va="center",
        )

    # =====================================================
    # 5. RODAPÉ
    # =====================================================

    fig.text(
        0.5, 0.032,
        (
            "Este relatório é informativo e não substitui avaliação médica.\n"
            "Procure uma UBS ou um profissional de saúde de confiança."
        ),
        fontsize=9.5,
        color=CORES["secundario"],
        ha="center",
        va="center",
        linespacing=1.5,
    )

    # =====================================================
    # 6. EXPORTAÇÃO PNG EM MEMÓRIA
    # =====================================================

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=180,
        facecolor=fig.get_facecolor(),
    )

    buffer.seek(0)

    plt.close(fig)

    return buffer
