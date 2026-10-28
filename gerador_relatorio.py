
"""
Gera um relatório visual acessível de acompanhamento do Calor Aviso em PNG.

A função gerar_png_relatorio(dados) retorna um io.BytesIO, compatível com
telegram.Bot.send_photo / Update.message.reply_photo.
"""
from __future__ import annotations

import datetime
import io
import math
from collections import Counter
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


# =========================================================
# CONFIGURAÇÃO VISUAL
# =========================================================

C = {
    "papel": "#FAF8F3",
    "tinta": "#24302B",
    "texto": "#39443E",
    "suave": "#566159",
    "linha": "#DCDDD4",
    "acento": "#0065FC",
    "acento_claro": "#B8C9ED",
    "verde": "#47634D",
    "branco": "#FFFFFF",
}

# Aumente este valor para ampliar todas as fontes do relatório.
ESCALA_FONTE = 1.30

# Tamanho da página em polegadas.
# A página maior oferece mais espaço para acomodar os textos.
LARGURA_PAGINA = 9.5
ALTURA_PAGINA = 13.43

DPI = 180

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12 * ESCALA_FONTE,
    "text.color": C["tinta"],
    "axes.labelcolor": C["suave"],
    "xtick.color": C["suave"],
    "ytick.color": C["suave"],
    "figure.facecolor": C["papel"],
    "savefig.facecolor": C["papel"],
})


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def _parse_datetime(valor: Any) -> datetime.datetime | None:
    if isinstance(valor, datetime.datetime):
        return valor

    if isinstance(valor, datetime.date):
        return datetime.datetime.combine(valor, datetime.time.min)

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
            return datetime.datetime.strptime(texto, formato)
        except ValueError:
            continue

    return None


def _numero(valor: Any) -> float | None:
    if valor is None or str(valor).strip() == "":
        return None

    try:
        resultado = float(valor)
        return resultado if math.isfinite(resultado) else None
    except (TypeError, ValueError):
        return None



def _nome_pessoa(dados: dict[str, Any]) -> str:
    """Obtém o nome cadastrado, inclusive quando vem dentro de um dicionário."""

    chaves = (
        "nome_completo",
        "nome",
        "apelido",
        "nome_usuaria",
        "nome_usuario",
        "usuaria",
    )

    for chave in chaves:
        valor = dados.get(chave)

        if isinstance(valor, dict):
            for subchave in ("nome_completo", "nome", "apelido", "nome"):
                nome = valor.get(subchave)

                if isinstance(nome, str) and nome.strip():
                    nome = nome.strip()

                    if nome.lower() not in {
                        "usuaria", "usuário", "usuario", "paciente"
                    }:
                        return nome

        elif isinstance(valor, str) and valor.strip():
            nome = valor.strip()

            if nome.lower() not in {
                "usuaria", "usuário", "usuario", "paciente"
            }:
                return nome

    return "Nome não informado"



# =========================================================
# CÁLCULO DAS ESTATÍSTICAS
# =========================================================

def calcular_estatisticas(dados: dict[str, Any]) -> dict[str, Any]:
    diarios = dados.get("diarios", []) or []
    avulsos = dados.get("avulsos", []) or []

    data_inicio = _parse_datetime(dados.get("data_cadastro"))

    if data_inicio:
        agora = datetime.datetime.now(data_inicio.tzinfo)
        dias_analisados = max(1, (agora - data_inicio).days)
    else:
        dias_analisados = 1

    calores_por_data: dict[str, float] = {}
    total_calores = 0.0
    horarios_avulsos: list[int] = []

    # Registros do diário.
    for registro in diarios:
        if not registro:
            continue

        data_registro = _parse_datetime(registro[0])

        valor = (
            _numero(registro[1])
            if len(registro) > 1
            else None
        )

        quantidade = valor if valor is not None else 0
        total_calores += quantidade

        if data_registro:
            chave_data = data_registro.strftime("%Y-%m-%d")

            calores_por_data[chave_data] = (
                calores_por_data.get(chave_data, 0)
                + quantidade
            )

    # Registros avulsos.
    for registro in avulsos:
        if not registro:
            continue

        data_registro = _parse_datetime(registro[0])

        if not data_registro:
            continue

        chave_data = data_registro.strftime("%Y-%m-%d")

        calores_por_data[chave_data] = (
            calores_por_data.get(chave_data, 0) + 1
        )

        total_calores += 1
        horarios_avulsos.append(data_registro.hour)

    media_calores = total_calores / dias_analisados

    horario_frequente = "Sem registros avulsos"

    if horarios_avulsos:
        hora = Counter(horarios_avulsos).most_common(1)[0][0]

        horario_frequente = (
            f"{hora:02d}h–{(hora + 1) % 24:02d}h"
        )

    valores_sono: list[float] = []
    valores_humor: list[float] = []

    for registro in diarios:
        if len(registro) < 4:
            continue

        sono = _numero(registro[2])
        humor = _numero(registro[3])

        if sono is not None:
            valores_sono.append(sono)

        if humor is not None:
            valores_humor.append(humor)

    def descrever_media(
        valores: list[float],
        rotulos: tuple[str, str, str],
    ) -> str:
        if not valores:
            return "Sem registros"

        media = sum(valores) / len(valores)

        if media < 1.6:
            return rotulos[0]

        if media < 2.4:
            return rotulos[1]

        return rotulos[2]

    datas_ordenadas = sorted(calores_por_data)
    datas = datas_ordenadas[-7:]

    return {
        "dias_analisados": dias_analisados,
        "media_calores": round(media_calores, 1),
        "total_calores": (
            int(total_calores)
            if float(total_calores).is_integer()
            else round(total_calores, 1)
        ),
        "horario_frequente": horario_frequente,
        "sono": descrever_media(
            valores_sono,
            ("Mais difícil", "Razoável", "Boa"),
        ),
        "humor": descrever_media(
            valores_humor,
            ("Mais difícil", "Regular", "Bom"),
        ),
        "datas": datas,
        "valores": [
            calores_por_data[data]
            for data in datas
        ],
    }


# =========================================================
# FUNÇÕES DE DESENHO
# =========================================================

def _texto(
    fig,
    x: float,
    y: float,
    texto: str,
    *,
    tamanho: float = 10,
    cor: str | None = None,
    peso: str = "normal",
    familia: str | None = None,
    alinhamento: str = "left",
    estilo: str = "normal",
) -> None:
    """Desenha texto com fonte ampliada."""

    props = {
        "fontsize": tamanho * ESCALA_FONTE,
        "color": cor or C["tinta"],
        "weight": peso,
        "ha": alinhamento,
        "va": "center",
        "fontstyle": estilo,
    }

    if familia:
        props["fontfamily"] = familia

    fig.text(x, y, texto, **props)


def _linha(
    fig,
    x1: float,
    y: float,
    x2: float,
    *,
    cor: str | None = None,
    largura: float = 0.8,
) -> None:
    fig.add_artist(
        plt.Line2D(
            [x1, x2],
            [y, y],
            transform=fig.transFigure,
            color=cor or C["linha"],
            linewidth=largura,
            solid_capstyle="round",
        )
    )


# =========================================================
# GERAÇÃO DO RELATÓRIO PNG
# =========================================================

def gerar_png_relatorio(dados: dict[str, Any]) -> io.BytesIO:
    stats = calcular_estatisticas(dados)
    nome = _nome_pessoa(dados)

    hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    media = f"{stats['media_calores']:.1f}".replace(".", ",")

    fig = plt.figure(
        figsize=(LARGURA_PAGINA, ALTURA_PAGINA),
        facecolor=C["papel"],
    )

    fig.subplots_adjust(0, 0, 1, 1)

    # -----------------------------------------------------
    # CABEÇALHO
    # -----------------------------------------------------

    _texto(
        fig, 0.085, 0.963,
        "CALOR AVISO",
        tamanho=12,
        cor=C["verde"],
        peso="bold",
    )

    _texto(
        fig, 0.915, 0.963,
        "RELATÓRIO PESSOAL",
        tamanho=10,
        cor=C["suave"],
        alinhamento="right",
    )

    _linha(
        fig, 0.085, 0.943, 0.915,
        cor=C["tinta"],
        largura=1.2,
    )

    _texto(
        fig, 0.085, 0.900,
        "Seu acompanhamento",
        tamanho=28,
        peso="bold",
        familia="DejaVu Serif",
    )

    _texto(
        fig, 0.085, 0.861,
        nome,
        tamanho=17,
        cor=C["verde"],
        peso="bold",
    )

    _texto(
        fig, 0.085, 0.827,
        (
            f"{stats['dias_analisados']} dias desde o início "
            f"do acompanhamento"
        ),
        tamanho=11,
        cor=C["suave"],
    )

    _texto(
        fig, 0.085, 0.800,
        f"Relatório gerado em {hoje}",
        tamanho=11,
        cor=C["suave"],
    )

    _linha(fig, 0.085, 0.777, 0.915)

    # -----------------------------------------------------
    # RESUMO
    # -----------------------------------------------------

    _texto(
        fig, 0.085, 0.748,
        "EM RESUMO",
        tamanho=11,
        cor=C["suave"],
        peso="bold",
    )

    _texto(
        fig, 0.085, 0.695,
        media,
        tamanho=38,
        familia="DejaVu Serif",
        cor=C["acento"],
        peso="bold",
    )

    _texto(
        fig, 0.087, 0.660,
        "episódios por dia, em média",
        tamanho=12,
        cor=C["texto"],
    )

    # Separador vertical.
    fig.add_artist(
        plt.Line2D(
            [0.395, 0.395],
            [0.655, 0.740],
            transform=fig.transFigure,
            color=C["linha"],
            linewidth=1,
        )
    )

    _texto(
        fig, 0.435, 0.724,
        "TOTAL REGISTRADO",
        tamanho=10,
        cor=C["suave"],
        peso="bold",
    )

    _texto(
        fig, 0.435, 0.690,
        str(stats["total_calores"]),
        tamanho=22,
        peso="bold",
    )

    _texto(
        fig, 0.435, 0.658,
        "episódios",
        tamanho=11,
        cor=C["suave"],
    )

    _texto(
        fig, 0.675, 0.724,
        "HORÁRIO MAIS FREQUENTE",
        tamanho=9,
        cor=C["suave"],
        peso="bold",
    )

    horario = stats["horario_frequente"]

    if len(horario) > 17:
        horario = "Sem dados"

    _texto(
        fig, 0.675, 0.690,
        horario,
        tamanho=15,
        peso="bold",
    )

    _texto(
        fig, 0.675, 0.658,
        "entre os registros avulsos",
        tamanho=9,
        cor=C["suave"],
    )

    _linha(fig, 0.085, 0.625, 0.915)

    # -----------------------------------------------------
    # GRÁFICO DE EPISÓDIOS
    # -----------------------------------------------------

    _texto(
        fig, 0.085, 0.593,
        "Episódios de calor",
        tamanho=20,
        peso="bold",
        familia="DejaVu Serif",
    )

    _texto(
        fig, 0.085, 0.560,
        "Últimos dias em que houve registros",
        tamanho=12,
        cor=C["suave"],
    )

    ax = fig.add_axes([0.12, 0.375, 0.76, 0.145])
    ax.set_facecolor("none")

    datas = stats["datas"]
    valores = stats["valores"]

    if datas:
        labels = [
            datetime.datetime.strptime(
                data, "%Y-%m-%d"
            ).strftime("%d/%m")
            for data in datas
        ]

        positions = list(range(len(valores)))

        cores = [C["acento_claro"]] * len(valores)
        cores[-1] = C["acento"]

        barras = ax.bar(
            positions,
            valores,
            color=cores,
            width=0.55,
            zorder=3,
        )

        ax.set_xticks(positions, labels=labels)

        ymax = max(1, max(valores) * 1.35)
        ax.set_ylim(0, ymax)

        ax.yaxis.set_major_locator(
            MaxNLocator(nbins=4, integer=True)
        )

        ax.grid(
            axis="y",
            color=C["linha"],
            linewidth=0.8,
            zorder=0,
        )

        ax.set_axisbelow(True)

        ax.tick_params(
            axis="x",
            labelsize=12 * ESCALA_FONTE,
            length=0,
            pad=10,
        )

        ax.tick_params(
            axis="y",
            labelsize=11 * ESCALA_FONTE,
            length=0,
            pad=8,
        )

        for spine in ax.spines.values():
            spine.set_visible(False)

        if max(valores) > 0:
            ax.bar_label(
                barras,
                labels=[f"{v:g}" for v in valores],
                padding=5,
                fontsize=11 * ESCALA_FONTE,
                color=C["texto"],
            )
        else:
            ax.set_yticks([0])

    else:
        ax.axis("off")

        ax.text(
            0.5,
            0.5,
            "Ainda não há registros suficientes\n"
            "para montar o gráfico.",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=13 * ESCALA_FONTE,
            color=C["suave"],
            wrap=True,
        )

    _linha(fig, 0.085, 0.350, 0.915)

    # -----------------------------------------------------
    # SONO E HUMOR
    # -----------------------------------------------------

    _texto(
        fig, 0.085, 0.318,
        "Como você tem se sentido",
        tamanho=19,
        peso="bold",
        familia="DejaVu Serif",
    )

    _texto(
        fig, 0.085, 0.279,
        "SONO",
        tamanho=11,
        cor=C["suave"],
        peso="bold",
    )

    _texto(
        fig, 0.085, 0.244,
        stats["sono"],
        tamanho=17,
        peso="bold",
        cor=C["verde"],
    )

    _texto(
        fig, 0.085, 0.214,
        "Com base nas respostas do diário",
        tamanho=10,
        cor=C["suave"],
    )

    fig.add_artist(
        plt.Line2D(
            [0.505, 0.505],
            [0.205, 0.290],
            transform=fig.transFigure,
            color=C["linha"],
            linewidth=1,
        )
    )

    _texto(
        fig, 0.55, 0.279,
        "HUMOR",
        tamanho=11,
        cor=C["suave"],
        peso="bold",
    )

    _texto(
        fig, 0.55, 0.244,
        stats["humor"],
        tamanho=17,
        peso="bold",
        cor=C["verde"],
    )

    _texto(
        fig, 0.55, 0.214,
        "Com base nas respostas do diário",
        tamanho=10,
        cor=C["suave"],
    )

    _linha(fig, 0.085, 0.184, 0.915)

    # -----------------------------------------------------
    # PERGUNTAS PARA A CONSULTA
    # -----------------------------------------------------

    _texto(
        fig, 0.085, 0.153,
        "Para conversar na consulta",
        tamanho=19,
        peso="bold",
        familia="DejaVu Serif",
    )

    perguntas = [
        "O que pode estar relacionado aos meus episódios de calor?",
        "O que pode ajudar a melhorar meu sono?",
        "Quais opções de acompanhamento fazem sentido para mim?",
    ]

    # Espaçamento maior entre as perguntas para facilitar a leitura.
    for i, pergunta in enumerate(perguntas):
        y = 0.119 - i * 0.031

        _texto(
            fig, 0.092, y,
            f"{i + 1:02d}",
            tamanho=11,
            cor=C["acento"],
            peso="bold",
        )

        _texto(
            fig, 0.135, y,
            pergunta,
            tamanho=10.5,
            cor=C["texto"],
        )

    # -----------------------------------------------------
    # RODAPÉ
    # -----------------------------------------------------

    _linha(fig, 0.085, 0.039, 0.915)

    _texto(
        fig, 0.085, 0.024,
        "Este resumo reúne informações registradas por você;",
        tamanho=8.5,
        cor=C["suave"],
    )

    # O aviso final é mantido na imagem com fonte legível.
    # Usamos uma segunda linha acima da margem inferior.
    _texto(
        fig, 0.085, 0.010,
        "não é um diagnóstico médico. Procure uma UBS ou profissional de saúde.",
        tamanho=8.5,
        cor=C["suave"],
    )

    # -----------------------------------------------------
    # EXPORTAÇÃO
    # -----------------------------------------------------

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=DPI,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.15,
    )

    buffer.seek(0)
    plt.close(fig)

    return buffer
