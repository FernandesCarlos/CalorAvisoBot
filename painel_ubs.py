
import datetime
import html
import re
import sqlite3
import textwrap

import pandas as pd
import streamlit as st

import database as db
import gerador_relatorio


# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================

st.set_page_config(
    page_title="Saúde da Mulher | Acompanhamento",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# BOOTSTRAP 5.3.8
# =========================================================

st.markdown(
    """
    <link
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
        rel="stylesheet"
        integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"
        crossorigin="anonymous">
    """.strip(),
    unsafe_allow_html=True,
)


# =========================================================
# ESTILIZAÇÃO
# =========================================================

CSS = """
<style>
    .stApp {
        background: #F4F6F9;
        color: #26374A;
    }

    .block-container {
        max-width: 1500px;
        padding: 2rem 3rem 3rem;
    }

    .dashboard-header {
        background: #FFFFFF;
        border: 1px solid #DDE4EC;
        border-left: 5px solid #315873;
        border-radius: 8px;
        padding: 1.6rem 1.8rem;
    }

    .dashboard-eyebrow {
        color: #496B83;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        margin-bottom: 0.55rem;
    }

    .dashboard-title {
        color: #20364A;
        font-size: clamp(1.55rem, 2.5vw, 2.1rem);
        font-weight: 700;
        line-height: 1.25;
        letter-spacing: -0.025em;
        margin: 0;
    }

    .dashboard-description {
        color: #566579;
        font-size: 1rem;
        line-height: 1.6;
        margin: 0.65rem 0 0;
    }

    .period-card {
        background: #F7F9FC;
        border: 1px solid #DDE4EC;
        border-radius: 7px;
        min-width: 175px;
        padding: 0.9rem 1rem;
    }

    .period-label {
        color: #566579;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .period-value {
        color: #20364A;
        font-size: 1.05rem;
        font-weight: 700;
        margin-top: 0.3rem;
    }

    .period-date {
        color: #566579;
        font-size: 0.8rem;
        margin-top: 0.25rem;
    }

    .section-description {
        color: #566579;
        font-size: 0.92rem;
        line-height: 1.55;
        margin-top: -0.4rem;
        margin-bottom: 1.1rem;
    }

    .metric-card {
        background: #FFFFFF;
        border: 1px solid #DDE4EC !important;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(31, 52, 73, 0.035);
        min-height: 138px;
    }

    .metric-label {
        color: #566579;
        font-size: 0.86rem;
        font-weight: 600;
        line-height: 1.4;
        margin-bottom: 0.8rem;
    }

    .metric-value {
        color: #20364A;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.2;
        overflow-wrap: anywhere;
    }

    .metric-note {
        color: #64748B;
        font-size: 0.78rem;
        margin-top: 0.5rem;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF;
        border-color: #DDE4EC;
        border-radius: 8px;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button {
        width: 100%;
        min-height: 2.6rem;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.87rem;
        white-space: normal;
        line-height: 1.3;
        transition: background-color 0.15s ease;
    }

    div[data-testid="stButton"] button {
        background: #315873;
        color: #FFFFFF;
        border: 1px solid #315873;
    }

    div[data-testid="stButton"] button:hover {
        background: #25465D;
        color: #FFFFFF;
        border-color: #25465D;
    }

    div[data-testid="stDownloadButton"] button {
        background: #FFFFFF;
        color: #315873;
        border: 1px solid #315873;
    }

    div[data-testid="stDownloadButton"] button:hover {
        background: #EDF3F7;
        color: #25465D;
        border-color: #25465D;
    }

    div[data-testid="stAlert"] {
        border-radius: 7px;
    }

    h1, h2, h3 {
        color: #20364A !important;
    }

    h2 {
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }

    h3 {
        font-size: 1.05rem !important;
        font-weight: 650 !important;
    }

    hr {
        border-color: #DDE4EC;
        margin: 1.5rem 0;
    }

    @media (max-width: 900px) {
        .block-container {
            padding: 1.2rem 1rem 2rem;
        }

        .dashboard-header {
            padding: 1.2rem;
        }

        .metric-value {
            font-size: 1.7rem;
        }
    }
</style>
"""

st.markdown(
    textwrap.dedent(CSS).strip(),
    unsafe_allow_html=True,
)


# =========================================================
# FUNÇÃO DE RENDERIZAÇÃO HTML
# Evita que HTML indentado apareça como bloco de código.
# =========================================================

def renderizar_html(conteudo):
    conteudo = "\n".join(
        linha.lstrip()
        for linha in conteudo.splitlines()
    ).strip()

    st.markdown(
        conteudo,
        unsafe_allow_html=True,
    )


# =========================================================
# PERÍODO DE REFERÊNCIA
# =========================================================

hoje = datetime.date.today()
data_formatada = hoje.strftime("%d/%m/%Y")

parametros_7_dias = (
    hoje.isoformat(),
    hoje.isoformat(),
)

parametros_14_dias = (
    hoje.isoformat(),
    hoje.isoformat(),
)


# =========================================================
# CONSULTAS AO BANCO
# =========================================================

conn = sqlite3.connect("saude_mulher.db")

try:

    # -----------------------------------------------------
    # Total de pacientes ativas
    # -----------------------------------------------------

    df_pacientes = pd.read_sql_query(
        """
        SELECT COUNT(*) AS total
        FROM usuarias
        WHERE ativo = 1
        """,
        conn,
    )

    total_mulheres = int(
        df_pacientes.iloc[0]["total"]
    )

    # -----------------------------------------------------
    # Calores registrados nos diários: últimos 7 dias
    # -----------------------------------------------------

    df_diario_semana = pd.read_sql_query(
        """
        SELECT COALESCE(SUM(calores), 0) AS total
        FROM registros_diarios
        WHERE date(data)
            BETWEEN date(?, '-6 days') AND date(?)
        """,
        conn,
        params=parametros_7_dias,
    )

    total_diario = int(
        df_diario_semana.iloc[0]["total"] or 0
    )

    # -----------------------------------------------------
    # Episódios avulsos: últimos 7 dias
    # -----------------------------------------------------

    df_avulso_semana = pd.read_sql_query(
        """
        SELECT COUNT(*) AS total
        FROM episodios_calor
        WHERE date(data)
            BETWEEN date(?, '-6 days') AND date(?)
        """,
        conn,
        params=parametros_7_dias,
    )

    total_avulso = int(
        df_avulso_semana.iloc[0]["total"] or 0
    )

    total_calores_semana = (
        total_diario + total_avulso
    )

    # -----------------------------------------------------
    # Gráfico: registros diários dos últimos 14 dias
    # -----------------------------------------------------

    df_diario = pd.read_sql_query(
        """
        SELECT
            date(data) AS dia,
            SUM(COALESCE(calores, 0)) AS total
        FROM registros_diarios
        WHERE date(data)
            BETWEEN date(?, '-13 days') AND date(?)
        GROUP BY date(data)
        ORDER BY date(data)
        """,
        conn,
        params=parametros_14_dias,
    )

    # -----------------------------------------------------
    # Gráfico: episódios avulsos dos últimos 14 dias
    # -----------------------------------------------------

    df_avulso = pd.read_sql_query(
        """
        SELECT
            date(data) AS dia,
            COUNT(*) AS total
        FROM episodios_calor
        WHERE date(data)
            BETWEEN date(?, '-13 days') AND date(?)
        GROUP BY date(data)
        ORDER BY date(data)
        """,
        conn,
        params=parametros_14_dias,
    )

    df_diario["dia"] = pd.to_datetime(
        df_diario["dia"],
        errors="coerce",
    )

    df_avulso["dia"] = pd.to_datetime(
        df_avulso["dia"],
        errors="coerce",
    )

    df_grafico = pd.merge(
        df_diario,
        df_avulso,
        on="dia",
        how="outer",
        suffixes=("_diario", "_avulso"),
    )

    df_grafico["total_diario"] = (
        df_grafico["total_diario"].fillna(0)
    )

    df_grafico["total_avulso"] = (
        df_grafico["total_avulso"].fillna(0)
    )

    df_grafico["total_calores"] = (
        df_grafico["total_diario"]
        + df_grafico["total_avulso"]
    )

    # Inclui também os dias sem registros.
    calendario = pd.DataFrame({
        "dia": pd.date_range(
            end=pd.Timestamp(hoje),
            periods=14,
            freq="D",
        )
    })

    df_grafico = calendario.merge(
        df_grafico[["dia", "total_calores"]],
        on="dia",
        how="left",
    )

    df_grafico["total_calores"] = (
        df_grafico["total_calores"]
        .fillna(0)
        .astype(int)
    )

    df_grafico["dia_label"] = (
        df_grafico["dia"].dt.strftime("%d/%m")
    )

    # -----------------------------------------------------
    # TODAS AS PACIENTES ATIVAS
    # Inclui pacientes sem diário recente.
    # -----------------------------------------------------

    query_acompanhamento = """
        WITH diarios_semana AS (
            SELECT
                identificador,

                AVG(
                    CAST(COALESCE(calores, 0) AS REAL)
                ) AS media_calores,

                MAX(
                    CASE
                        WHEN TRIM(CAST(sono AS TEXT)) = '1'
                        THEN 1
                        ELSE 0
                    END
                ) AS sono_ruim,

                COUNT(DISTINCT date(data))
                    AS dias_registrados

            FROM registros_diarios

            WHERE date(data)
                BETWEEN date(?, '-6 days') AND date(?)

            GROUP BY identificador
        )

        SELECT
            u.identificador,
            u.apelido,
            u.idade,

            COALESCE(d.media_calores, 0)
                AS media_calores,

            COALESCE(d.sono_ruim, 0)
                AS sono_ruim,

            COALESCE(d.dias_registrados, 0)
                AS dias_registrados

        FROM usuarias u

        LEFT JOIN diarios_semana d
            ON u.identificador = d.identificador

        WHERE u.ativo = 1

        ORDER BY u.apelido
    """

    df_acompanhamento = pd.read_sql_query(
        query_acompanhamento,
        conn,
        params=parametros_7_dias,
    )

finally:
    conn.close()


# =========================================================
# CLASSIFICAÇÃO DAS PRIORIDADES
# =========================================================

df_acompanhamento["media_calores"] = pd.to_numeric(
    df_acompanhamento["media_calores"],
    errors="coerce",
).fillna(0)

df_acompanhamento["sono_ruim"] = pd.to_numeric(
    df_acompanhamento["sono_ruim"],
    errors="coerce",
).fillna(0).astype(int)

df_acompanhamento["dias_registrados"] = pd.to_numeric(
    df_acompanhamento["dias_registrados"],
    errors="coerce",
).fillna(0).astype(int)


def classificar_prioridade(row):
    """
    Classificação administrativa para organizar a revisão.
    Não representa diagnóstico nem triagem clínica validada.
    """

    if row["dias_registrados"] == 0:
        return "Sem diário recente"

    muitos_calores = row["media_calores"] >= 4
    sono_sinalizado = row["sono_ruim"] == 1

    if muitos_calores and sono_sinalizado:
        return "Maior urgência"

    if muitos_calores or sono_sinalizado:
        return "Média urgência"

    return "Baixa urgência"


df_acompanhamento["prioridade"] = (
    df_acompanhamento.apply(
        classificar_prioridade,
        axis=1,
    )
)

ordem_prioridade = {
    "Maior urgência": 0,
    "Média urgência": 1,
    "Baixa urgência": 2,
    "Sem diário recente": 3,
}

df_acompanhamento["_ordem"] = (
    df_acompanhamento["prioridade"].map(
        ordem_prioridade
    )
)

df_acompanhamento = (
    df_acompanhamento
    .sort_values(
        by=["_ordem", "media_calores"],
        ascending=[True, False],
    )
    .drop(columns="_ordem")
    .reset_index(drop=True)
)


# =========================================================
# CABEÇALHO
# =========================================================

renderizar_html(
    f"""
    <div class="container-fluid px-0 mb-4">
        <div class="dashboard-header">
            <div class="d-flex flex-wrap justify-content-between align-items-start gap-4">

                <div class="flex-grow-1">
                    <div class="dashboard-eyebrow">
                        Atenção Primária à Saúde
                    </div>

                    <h1 class="dashboard-title">
                        Acompanhamento da Saúde da Mulher
                    </h1>

                    <p class="dashboard-description">
                        Visão consolidada dos registros de sintomas
                        e do acompanhamento das pacientes.
                    </p>
                </div>

                <div class="period-card">
                    <div class="period-label">
                        Período de referência
                    </div>

                    <div class="period-value">
                        Últimos 7 dias
                    </div>

                    <div class="period-date">
                        Atualizado em {html.escape(data_formatada)}
                    </div>
                </div>

            </div>
        </div>
    </div>
    """
)


# =========================================================
# AVISO DE DEMONSTRAÇÃO
# =========================================================

st.info(
    "**Ambiente de demonstração:** os dados exibidos "
    "são fictícios e utilizados para testar o sistema."
)


# =========================================================
# 1. INDICADORES GERAIS
# =========================================================

st.subheader("Visão geral")

st.markdown(
    """
    <p class="section-description">
        Principais indicadores do acompanhamento no período.
    </p>
    """,
    unsafe_allow_html=True,
)

formatar_inteiro = lambda numero: f"{int(numero):,}".replace(",", ".")

renderizar_html(
    f"""
    <div class="container-fluid px-0 mb-4">
        <div class="row g-3">

            <div class="col-12 col-md-4">
                <div class="card metric-card h-100">
                    <div class="card-body p-4">
                        <div class="metric-label">
                            Pacientes em acompanhamento
                        </div>
                        <div class="metric-value">
                            {formatar_inteiro(total_mulheres)}
                        </div>
                        <div class="metric-note">
                            Pacientes com cadastro ativo
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 col-md-4">
                <div class="card metric-card h-100">
                    <div class="card-body p-4">
                        <div class="metric-label">
                            Ondas de calor registradas
                        </div>
                        <div class="metric-value">
                            {formatar_inteiro(total_calores_semana)}
                        </div>
                        <div class="metric-note">
                            Diários e episódios avulsos
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 col-md-4">
                <div class="card metric-card h-100">
                    <div class="card-body p-4">
                        <div class="metric-label">
                            Período analisado
                        </div>
                        <div class="metric-value">
                            7 dias
                        </div>
                        <div class="metric-note">
                            Inclui a data de hoje
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>
    """
)

st.divider()


# =========================================================
# 2. GRÁFICO GERAL
# =========================================================

st.subheader("Frequência diária de ondas de calor")

st.markdown(
    """
    <p class="section-description">
        Total de calores informados nos diários e nos
        registros avulsos ao longo dos últimos 14 dias.
    </p>
    """,
    unsafe_allow_html=True,
)

if df_grafico["total_calores"].sum() > 0:

    st.bar_chart(
        data=df_grafico,
        x="dia_label",
        y="total_calores",
        color="#496F8A",
        use_container_width=True,
    )

    st.caption(
        "Os valores representam a soma dos registros diários "
        "e dos episódios avulsos em cada data."
    )

else:

    st.info(
        "Ainda não existem registros de calores no período selecionado."
    )


st.divider()


# =========================================================
# 3. ACOMPANHAMENTO DE PACIENTES
# =========================================================

st.subheader("Acompanhamento de pacientes")

st.markdown(
    """
    <p class="section-description">
        Consulte todas as pacientes ativas e filtre a lista
        conforme os critérios de revisão dos registros recentes.
    </p>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Os níveis são critérios administrativos definidos para este "
    "sistema, não uma classificação clínica validada."
)


# ---------------------------------------------------------
# Contagem de cada categoria
# ---------------------------------------------------------

contagens = (
    df_acompanhamento["prioridade"].value_counts()
)

total_pacientes = len(df_acompanhamento)

qtd_maior = int(
    contagens.get("Maior urgência", 0)
)

qtd_media = int(
    contagens.get("Média urgência", 0)
)

qtd_baixa = int(
    contagens.get("Baixa urgência", 0)
)

qtd_sem_diario = int(
    contagens.get("Sem diário recente", 0)
)


# ---------------------------------------------------------
# Cartões de contagem
# ---------------------------------------------------------

renderizar_html(
    f"""
    <div class="container-fluid px-0 mb-4">
        <div class="row g-3">

            <div class="col-12 col-md-3">
                <div class="card metric-card h-100"
                     style="border-top: 4px solid #B42318 !important;">
                    <div class="card-body p-3">
                        <div class="metric-label">Maior urgência</div>
                        <div class="metric-value">
                            {qtd_maior}
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 col-md-3">
                <div class="card metric-card h-100"
                     style="border-top: 4px solid #946200 !important;">
                    <div class="card-body p-3">
                        <div class="metric-label">Média urgência</div>
                        <div class="metric-value">
                            {qtd_media}
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 col-md-3">
                <div class="card metric-card h-100"
                     style="border-top: 4px solid #26734D !important;">
                    <div class="card-body p-3">
                        <div class="metric-label">Baixa urgência</div>
                        <div class="metric-value">
                            {qtd_baixa}
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 col-md-3">
                <div class="card metric-card h-100"
                     style="border-top: 4px solid #596579 !important;">
                    <div class="card-body p-3">
                        <div class="metric-label">Sem diário recente</div>
                        <div class="metric-value">
                            {qtd_sem_diario}
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>
    """
)


# ---------------------------------------------------------
# Filtros: prioridade e busca
# ---------------------------------------------------------

col_filtro, col_busca = st.columns(
    [1.2, 1],
    gap="medium",
)

with col_filtro:

    prioridade_selecionada = st.selectbox(
        "Filtrar por prioridade",
        options=[
            "Todas as pacientes",
            "Maior urgência",
            "Média urgência",
            "Baixa urgência",
            "Sem diário recente",
        ],
        index=0,
        key="filtro_prioridade_pacientes",
    )

with col_busca:

    texto_busca = st.text_input(
        "Buscar paciente",
        placeholder="Digite o apelido da paciente",
        key="busca_paciente",
    )


# ---------------------------------------------------------
# Aplica os filtros
# ---------------------------------------------------------

if prioridade_selecionada == "Todas as pacientes":

    df_filtrado = df_acompanhamento.copy()

else:

    df_filtrado = df_acompanhamento[
        df_acompanhamento["prioridade"]
        == prioridade_selecionada
    ].copy()


if texto_busca.strip():

    df_filtrado = df_filtrado[
        df_filtrado["apelido"]
        .fillna("")
        .astype(str)
        .str.contains(
            texto_busca.strip(),
            case=False,
            na=False,
            regex=False,
        )
    ]


st.caption(
    f"Exibindo {len(df_filtrado)} de "
    f"{total_pacientes} pacientes ativas."
)


# ---------------------------------------------------------
# Cores das categorias
# ---------------------------------------------------------

cores_prioridade = {
    "Maior urgência": "#B42318",
    "Média urgência": "#946200",
    "Baixa urgência": "#26734D",
    "Sem diário recente": "#596579",
}

fundos_prioridade = {
    "Maior urgência": "#FDECEC",
    "Média urgência": "#FFF4D6",
    "Baixa urgência": "#E8F5ED",
    "Sem diário recente": "#EEF1F5",
}


# ---------------------------------------------------------
# Lista de pacientes
# ---------------------------------------------------------

if df_filtrado.empty:

    st.info(
        "Nenhuma paciente corresponde aos filtros selecionados."
    )

else:

    cab1, cab2, cab3, cab4 = st.columns(
        [1.8, 2.5, 2.0, 1.8],
        gap="medium",
    )

    cab1.markdown("**Paciente**")
    cab2.markdown("**Prioridade e motivo**")
    cab3.markdown("**Registros recentes**")
    cab4.markdown("**Relatório**")

    st.divider()

    for _, row in df_filtrado.iterrows():

        identificador = row["identificador"]

        apelido = str(
            row["apelido"] or "Paciente"
        ).strip()

        idade = row["idade"]

        media_calores = float(
            row["media_calores"]
        )

        sono_ruim = int(
            row["sono_ruim"]
        )

        dias_registrados = int(
            row["dias_registrados"]
        )

        prioridade = row["prioridade"]

        cor = cores_prioridade[prioridade]
        fundo = fundos_prioridade[prioridade]

        # Chaves individuais para os botões e o arquivo.
        chave_png = f"relatorio_png_{identificador}"
        chave_nome = f"relatorio_nome_{identificador}"
        chave_gerar = f"gerar_relatorio_{identificador}"

        with st.container(border=True):

            c1, c2, c3, c4 = st.columns(
                [1.8, 2.5, 2.0, 1.8],
                gap="medium",
            )

            # ---------------------------------------------
            # Nome e idade
            # ---------------------------------------------

            with c1:

                st.markdown(
                    f"**{html.escape(apelido)}**"
                )

                if pd.notna(idade):

                    st.caption(
                        f"{int(idade)} anos"
                    )

                else:

                    st.caption(
                        "Idade não informada"
                    )

            # ---------------------------------------------
            # Prioridade e justificativa
            # ---------------------------------------------

            with c2:

                renderizar_html(
                    f"""
                    <span style="
                        display: inline-block;
                        background: {fundo};
                        color: {cor};
                        border: 1px solid {cor}33;
                        border-radius: 5px;
                        padding: 4px 9px;
                        font-size: 0.8rem;
                        font-weight: 700;
                    ">{html.escape(prioridade)}</span>
                    """
                )

                if prioridade == "Maior urgência":

                    st.caption(
                        "Média elevada de calores e "
                        "registro de sono sinalizado."
                    )

                elif prioridade == "Média urgência":

                    motivos = []

                    if media_calores >= 4:

                        motivos.append(
                            "Média elevada de calores"
                        )

                    if sono_ruim == 1:

                        motivos.append(
                            "Sono sinalizado"
                        )

                    st.caption(
                        " e ".join(motivos) + "."
                    )

                elif prioridade == "Baixa urgência":

                    st.caption(
                        "Nenhum dos critérios atuais "
                        "de prioridade foi identificado."
                    )

                else:

                    st.caption(
                        "Sem diário recente para avaliar "
                        "pelos critérios atuais."
                    )

            # ---------------------------------------------
            # Dados do diário
            # ---------------------------------------------

            with c3:

                if dias_registrados > 0:

                    st.markdown(
                        f"**{dias_registrados} dia(s)**"
                    )

                    st.caption(
                        f"Média de {media_calores:.1f} "
                        "calores por diário."
                    )

                    if sono_ruim == 1:

                        st.caption(
                            "Sono sinalizado nos registros."
                        )

                else:

                    st.markdown(
                        "**Sem diário recente**"
                    )

                    st.caption(
                        "Não há registros suficientes "
                        "para esta classificação."
                    )

            # ---------------------------------------------
            # Geração e download do relatório
            # ---------------------------------------------

            with c4:

                if st.button(
                    "Gerar relatório",
                    key=chave_gerar,
                    use_container_width=True,
                    type="primary",
                ):

                    # Remove uma versão anterior antes de gerar.
                    st.session_state.pop(
                        chave_png,
                        None,
                    )

                    st.session_state.pop(
                        chave_nome,
                        None,
                    )

                    try:

                        with st.spinner(
                            "Preparando relatório..."
                        ):

                            dados_relatorio = (
                                db.obter_dados_completos_relatorio(
                                    identificador
                                )
                            )

                            if not dados_relatorio:

                                st.warning(
                                    "Não há dados para gerar "
                                    "o relatório desta paciente."
                                )

                            else:

                                imagem_buffer = (
                                    gerador_relatorio.gerar_png_relatorio(
                                        dados_relatorio
                                    )
                                )

                                # Guarda os bytes na sessão.
                                st.session_state[chave_png] = (
                                    imagem_buffer.getvalue()
                                )

                                nome_seguro = re.sub(
                                    r"[^a-zA-Z0-9_-]+",
                                    "_",
                                    apelido.lower(),
                                ).strip("_")

                                if not nome_seguro:

                                    nome_seguro = "paciente"

                                st.session_state[chave_nome] = (
                                    f"diario_{nome_seguro}.png"
                                )

                    except Exception as erro:

                        st.error(
                            "Não foi possível gerar o relatório: "
                            f"{erro}"
                        )

                # O botão de download aparece após gerar o PNG.
                if chave_png in st.session_state:

                    st.download_button(
                        "Baixar PNG",
                        data=st.session_state[chave_png],
                        file_name=st.session_state[chave_nome],
                        mime="image/png",
                        key=f"baixar_{identificador}",
                        use_container_width=True,
                    )


# =========================================================
# RODAPÉ
# =========================================================

st.divider()

renderizar_html(
    """
    <footer class="container-fluid px-0 pt-2 pb-3">
        <p class="small text-secondary mb-0">
            Painel de apoio ao acompanhamento. Os indicadores
            dependem dos registros disponíveis e não substituem
            a avaliação clínica individual.
        </p>
    </footer>
    """
)