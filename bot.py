import datetime
import os
import re
import pytz
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import database as db
import gerador_relatorio


# =========================================================
# CONFIGURAÇÕES
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TZ = pytz.timezone("America/Sao_Paulo")

TEXTO_COMANDOS = (
    "📌 **O que você pode fazer a qualquer momento:**\n\n"
    "🔥 Escreva **calor** - Para registrar uma onda de calor na mesma hora.\n"
    "📊 Escreva **relatório** - Para ver o seu gráfico e estatísticas.\n"
    "🗑️ Escreva **deletar** - Para apagar todos os seus dados do sistema."
)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def verificar_emergencia(texto: str) -> str:
    texto = texto.lower()

    if any(
        palavra in texto
        for palavra in [
            "desespero",
            "me machucar",
            "suicídio",
            "suicidio",
            "matar",
            "morrer",
        ]
    ):
        return "EMOCIONAL"

    if any(
        palavra in texto
        for palavra in [
            "sangramento",
            "dor forte",
            "não estou aguentando",
            "não aguento mais",
        ]
    ):
        return "FISICO"

    return "NENHUM"


def validar_cpf(cpf: str) -> bool:
    """
    Valida o formato e os dígitos verificadores do CPF.
    O CPF não é armazenado pelo bot.
    """

    cpf = re.sub(r"\D", "", cpf)

    if not re.fullmatch(r"\d{11}", cpf):
        return False

    # Rejeita CPFs formados por números repetidos.
    if cpf == cpf[0] * 11:
        return False

    numeros = [int(digito) for digito in cpf]

    # Verifica os dois dígitos verificadores.
    for posicao in (9, 10):
        soma = sum(
            numeros[i] * (posicao + 1 - i)
            for i in range(posicao)
        )

        resto = (soma * 10) % 11

        if resto == 10:
            resto = 0

        if resto != numeros[posicao]:
            return False

    return True


def avaliar_triagem(dados: dict) -> bool:
    idade = dados.get("idade", 0)
    sintomas = 0

    if dados.get("ciclo") == "1":
        sintomas += 1

    if dados.get("calores") in ["1", "2"]:
        sintomas += 1

    if dados.get("sono") in ["1", "2"]:
        sintomas += 1

    if dados.get("humor") in ["1", "2"]:
        sintomas += 1

    return (40 <= idade <= 55) and (sintomas >= 2)


# =========================================================
# ETAPAS DO CADASTRO
# =========================================================

async def perguntar_cep(
    mensagem,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["estado"] = "CEP"

    await mensagem.reply_text(
        "📮 **Informe seu CEP**\n\n"
        "Digite os 8 números, com ou sem hífen.\n"
        "Exemplo: 74000-000",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


async def perguntar_cpf(
    mensagem,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["estado"] = "CPF"

    await mensagem.reply_text(
        "🔐 **Agora, informe seu CPF.**\n\n"
        "Digite os números com ou sem pontos e hífen.\n"
        "Exemplo de formato: 123.456.789-09\n\n",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


async def iniciar_pergunta_idade(
    mensagem,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["estado"] = "IDADE"

    await mensagem.reply_text(
        "✅ Obrigada! Vamos continuar o cadastro.\n\n"
        "**Quantos anos você tem?** Digite apenas o número.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


async def iniciar_triagem(
    mensagem,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["estado"] = "CICLO"

    botoes = [
        [
            InlineKeyboardButton(
                "Sim, mudou",
                callback_data="1",
            )
        ],
        [
            InlineKeyboardButton(
                "Não mudou",
                callback_data="2",
            )
        ],
        [
            InlineKeyboardButton(
                "Já não menstruo",
                callback_data="3",
            )
        ],
    ]

    await mensagem.reply_text(
        "Sua menstruação mudou nos últimos meses?",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


# =========================================================
# COMANDO INICIAL
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    if db.usuaria_ja_cadastrada(chat_id):
        context.user_data["estado"] = "CONCLUIDO"

        await update.message.reply_text(
            f"Olá novamente! 👋 Seu registro está ativo.\n\n"
            f"{TEXTO_COMANDOS}",
            parse_mode="Markdown",
        )
        return

    context.user_data.clear()
    context.user_data["estado"] = "CONSENTIMENTO"

    mensagem = (
        "Olá! 👋 Eu sou a sua assistente virtual de saúde da mulher.\n\n"
        "Estou aqui para te ajudar a entender e acompanhar os seus "
        "sintomas do dia a dia, especialmente nesta fase de transição "
        "da menopausa.\n\n"
        "💡 **Como funciono:**\n"
        "• **Ondas de calor:** escreva a palavra calor aqui no chat "
        "para registrar um episódio.\n"
        "• **Sinais de alerta:** se você relatar sintomas preocupantes, "
        "vou interromper as perguntas para orientar você a buscar ajuda.\n\n"
        "🔒 **Privacidade:** seus dados são utilizados para o acompanhamento. "
        "Você pode apagar os dados armazenados pelo sistema escrevendo "
        "**deletar**. O CPF informado durante o cadastro não será armazenado.\n\n"
        "Posso começar algumas perguntinhas rápidas para te conhecer melhor?"
    )

    botoes = [
        [
            InlineKeyboardButton(
                "SIM, continuar",
                callback_data="sim",
            ),
            InlineKeyboardButton(
                "NÃO",
                callback_data="nao",
            ),
        ]
    ]

    await update.message.reply_text(
        mensagem,
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown",
    )


# =========================================================
# COMANDO DE TESTE DO DIÁRIO
# =========================================================

async def forcar_diario(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["estado"] = "DIARIO_1"

    await update.message.reply_text(
        "☀️ *[TESTE] Acompanhamento diário*\n\n"
        "Quantos episódios de calor você teve hoje?",
        parse_mode="Markdown",
    )


# =========================================================
# ROTEADOR DE CLIQUES NOS BOTÕES
# =========================================================

async def roteador_botoes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    resposta = query.data
    estado_atual = context.user_data.get("estado")
    chat_id = query.message.chat_id

    await query.edit_message_reply_markup(reply_markup=None)

    # -----------------------------------------------------
    # EXCLUSÃO DE DADOS
    # -----------------------------------------------------

    if resposta == "confirmar_delete":
        db.deletar_dados_usuaria(chat_id)
        context.user_data.clear()

        await query.message.reply_text(
            "🗑️ Seus dados foram excluídos do sistema. "
            "Se quiser voltar, envie /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if resposta == "cancelar_delete":
        await query.message.reply_text(
            "✅ Exclusão cancelada. Seus dados não foram apagados."
        )
        return

    # -----------------------------------------------------
    # CONSENTIMENTO
    # -----------------------------------------------------

    if estado_atual == "CONSENTIMENTO":
        if resposta == "sim":
            context.user_data["estado"] = "NOME_COMPLETO"

            await query.message.reply_text(
                "Qual é o seu nome completo?"
            )

        elif resposta == "nao":
            context.user_data["estado"] = "CONCLUIDO"

            await query.message.reply_text(
                "Tudo bem! Não vamos iniciar o cadastro. Cuide-se! 🌻"
            )

        return

    # -----------------------------------------------------
    # TRIAGEM: CICLO MENSTRUAL
    # -----------------------------------------------------

    if estado_atual == "CICLO":
        context.user_data["ciclo"] = resposta
        context.user_data["estado"] = "CALORES_TRIAGEM"

        botoes = [
            [
                InlineKeyboardButton(
                    "Sim, sempre",
                    callback_data="1",
                )
            ],
            [
                InlineKeyboardButton(
                    "Às vezes",
                    callback_data="2",
                )
            ],
            [
                InlineKeyboardButton(
                    "Não",
                    callback_data="3",
                )
            ],
        ]

        await query.message.reply_text(
            "Você sente ondas de calor ou acorda suando à noite?",
            reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    # -----------------------------------------------------
    # TRIAGEM: ONDAS DE CALOR
    # -----------------------------------------------------

    if estado_atual == "CALORES_TRIAGEM":
        context.user_data["calores"] = resposta
        context.user_data["estado"] = "SONO_TRIAGEM"

        botoes = [
            [
                InlineKeyboardButton("Sim", callback_data="1"),
                InlineKeyboardButton("Um pouco", callback_data="2"),
            ],
            [
                InlineKeyboardButton("Não", callback_data="3"),
            ],
        ]

        await query.message.reply_text(
            "Seu sono piorou ultimamente?",
            reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    # -----------------------------------------------------
    # TRIAGEM: SONO
    # -----------------------------------------------------

    if estado_atual == "SONO_TRIAGEM":
        context.user_data["sono"] = resposta
        context.user_data["estado"] = "HUMOR_TRIAGEM"

        botoes = [
            [
                InlineKeyboardButton("Sim", callback_data="1"),
                InlineKeyboardButton("Um pouco", callback_data="2"),
            ],
            [
                InlineKeyboardButton("Não", callback_data="3"),
            ],
        ]

        await query.message.reply_text(
            "Você tem se sentido mais irritada, ansiosa ou "
            "esquecida do que antes?",
            reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    # -----------------------------------------------------
    # TRIAGEM: HUMOR E RESULTADO
    # -----------------------------------------------------

    if estado_atual == "HUMOR_TRIAGEM":
        context.user_data["humor"] = resposta

        # O CPF não está em context.user_data e, portanto,
        # não é enviado nesta chamada ao banco de dados.
        db.salvar_usuaria(chat_id, context.user_data)

        if avaliar_triagem(context.user_data):
            await query.message.reply_text(
                "📝 *Resultado da triagem*\n\n"
                "Suas respostas apresentam sinais que podem ser "
                "compatíveis com a transição da menopausa. "
                "Isso não é um diagnóstico. Converse com uma equipe "
                "de saúde para obter orientação individualizada.",
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text(
                "✅ Triagem finalizada. Este resultado não substitui "
                "uma avaliação profissional."
            )

        # Após a triagem, solicita o horário do diário.
        context.user_data["estado"] = "ESCOLHER_HORARIO"

        botoes_horario = [
            [
                InlineKeyboardButton("08:00", callback_data="h_08:00"),
                InlineKeyboardButton("10:00", callback_data="h_10:00"),
                InlineKeyboardButton("12:00", callback_data="h_12:00"),
            ],
            [
                InlineKeyboardButton("14:00", callback_data="h_14:00"),
                InlineKeyboardButton("16:00", callback_data="h_16:00"),
                InlineKeyboardButton("18:00", callback_data="h_18:00"),
            ],
            [
                InlineKeyboardButton("20:00", callback_data="h_20:00"),
                InlineKeyboardButton("22:00", callback_data="h_22:00"),
            ],
        ]

        await query.message.reply_text(
            "⏰ **Em qual horário você prefere receber o diário?**",
            reply_markup=InlineKeyboardMarkup(botoes_horario),
            parse_mode="Markdown",
        )
        return

    # -----------------------------------------------------
    # SELEÇÃO DO HORÁRIO DO DIÁRIO
    # -----------------------------------------------------

    if resposta.startswith("h_"):
        horario_escolhido = resposta[2:]

        db.salvar_horario_diario(
            chat_id,
            horario_escolhido,
        )

        context.user_data["estado"] = "DIARIO_1"

        await query.message.reply_text(
            f"⏰ Combinado! O horário escolhido foi "
            f"*{horario_escolhido}*.\n\n"
            "Quantos episódios de calor você teve hoje?",
            parse_mode="Markdown",
        )
        return

    # -----------------------------------------------------
    # DIÁRIO: SONO
    # -----------------------------------------------------

    if estado_atual == "DIARIO_2":
        context.user_data["diario_sono"] = resposta
        context.user_data["estado"] = "DIARIO_3"

        botoes = [
            [
                InlineKeyboardButton("Mal", callback_data="1"),
                InlineKeyboardButton("Normal", callback_data="2"),
            ],
            [
                InlineKeyboardButton("Bem", callback_data="3"),
            ],
        ]

        await query.message.reply_text(
            "Como está o seu humor hoje?",
            reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    # -----------------------------------------------------
    # DIÁRIO: HUMOR E SALVAMENTO
    # -----------------------------------------------------

    if estado_atual == "DIARIO_3":
        context.user_data["diario_humor"] = resposta
        context.user_data["estado"] = "CONCLUIDO"

        db.salvar_diario(
            chat_id,
            context.user_data.get("diario_calores_qtd"),
            context.user_data.get("diario_sono"),
            context.user_data.get("diario_humor"),
        )

        await query.message.reply_text(
            f"🌻 Registro concluído!\n\n{TEXTO_COMANDOS}",
            parse_mode="Markdown",
        )
        return

    # -----------------------------------------------------
    # REGISTRO SEMANAL
    # -----------------------------------------------------

    if estado_atual == "SEMANAL_1":
        context.user_data["estado"] = "CONCLUIDO"

        await query.message.reply_text(
            f"🌻 Registro da semana concluído.\n\n{TEXTO_COMANDOS}",
            parse_mode="Markdown",
        )


# =========================================================
# ROTEADOR DE TEXTOS DIGITADOS
# =========================================================

async def roteador_textos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    texto = update.message.text.strip()
    texto_lower = texto.lower()
    estado_atual = context.user_data.get("estado", "CONCLUIDO")
    chat_id = update.effective_chat.id

    # -----------------------------------------------------
    # VERIFICAÇÃO DE MENSAGENS URGENTES
    # -----------------------------------------------------

    tipo_emergencia = verificar_emergencia(texto)

    if tipo_emergencia == "EMOCIONAL":
        context.user_data["estado"] = "CONCLUIDO"

        await update.message.reply_text(
            "🚨 Sinto muito que você esteja passando por isso. "
            "Se houver risco imediato, procure um serviço de emergência. "
            "No Brasil, o CVV atende pelo 188 para apoio emocional. "
            "Em uma emergência médica, ligue 192 ou vá a um pronto atendimento."
        )
        return

    if tipo_emergencia == "FISICO":
        context.user_data["estado"] = "CONCLUIDO"

        await update.message.reply_text(
            "🚨 Esses sintomas precisam de avaliação profissional. "
            "Se forem intensos ou houver risco imediato, procure "
            "atendimento de urgência. O bot não consegue avaliar emergências."
        )
        return

    # -----------------------------------------------------
    # COMANDO: REGISTRAR CALOR
    # -----------------------------------------------------

    if texto_lower in ["calor", "calores"]:
        agora = datetime.datetime.now(TZ).strftime("%H:%M")

        db.registrar_episodio_calor(
            chat_id,
            temperatura_ambiente=None,
        )

        await update.message.reply_text(
            f"🔥 Episódio registrado às *{agora}*.",
            parse_mode="Markdown",
        )
        return

    # -----------------------------------------------------
    # COMANDO: RELATÓRIO
    # -----------------------------------------------------

    if texto_lower in ["relatório", "relatorio"]:
        await update.message.reply_text(
            "📊 Preparando seu relatório..."
        )

        dados_relatorio = db.obter_dados_completos_relatorio(chat_id)

        if not dados_relatorio:
            await update.message.reply_text(
                "Ainda não há dados suficientes. "
                "Continue registrando seu acompanhamento."
            )
            return

        imagem_png = gerador_relatorio.gerar_png_relatorio(
            dados_relatorio
        )

        await update.message.reply_photo(
            photo=imagem_png,
            caption=(
                "Este é um resumo dos registros informados. "
                "Você pode conversar sobre ele com a equipe de saúde. 🌻"
            ),
        )
        return

    # -----------------------------------------------------
    # COMANDO: APAGAR DADOS
    # -----------------------------------------------------

    if texto_lower == "deletar":
        botoes = [
            [
                InlineKeyboardButton(
                    "Sim, apagar tudo",
                    callback_data="confirmar_delete",
                )
            ],
            [
                InlineKeyboardButton(
                    "Cancelar",
                    callback_data="cancelar_delete",
                )
            ],
        ]

        await update.message.reply_text(
            "⚠️ *Deseja excluir seus dados?*\n\n"
            "Essa ação apagará seu cadastro e o histórico "
            "armazenado pelo sistema.",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown",
        )
        return

    # =====================================================
    # CADASTRO INICIAL
    # =====================================================

    # -----------------------------------------------------
    # 1. NOME COMPLETO
    # -----------------------------------------------------

    if estado_atual == "NOME_COMPLETO":
        if len(texto) < 3:
            await update.message.reply_text(
                "Digite seu nome completo para continuar."
            )
            return

        context.user_data["nome_completo"] = texto[:120]

        await perguntar_cep(update.message, context)
        return

    # -----------------------------------------------------
    # 2. CEP
    # Não pesquisa UBS nem usa GPS.
    # -----------------------------------------------------

    if estado_atual == "CEP":
        cep = re.sub(r"\D", "", texto)

        if not re.fullmatch(r"\d{8}", cep):
            await update.message.reply_text(
                "CEP inválido. Digite os 8 números, "
                "com ou sem hífen.\n\n"
                "Exemplo: 74000-000"
            )
            return

        # Mantém o CEP nos dados temporários do cadastro.
        context.user_data["cep"] = cep

        await perguntar_cpf(update.message, context)
        return

    # -----------------------------------------------------
    # 3. CPF
    # Valida, mas não armazena o CPF.
    # -----------------------------------------------------

    if estado_atual == "CPF":
        cpf_digitado = re.sub(r"\D", "", texto)

        if not validar_cpf(cpf_digitado):
            await update.message.reply_text(
                "CPF inválido. Confira os números e os dígitos "
                "verificadores e tente novamente.\n\n"
                "Você pode digitar o CPF com ou sem pontos e hífen."
            )
            return

        # Não colocar o CPF em context.user_data ou no banco de dados.
        # A variável será descartada após esta etapa.
        del cpf_digitado

        await iniciar_pergunta_idade(update.message, context)
        return

    # -----------------------------------------------------
    # 4. IDADE
    # -----------------------------------------------------

    if estado_atual == "IDADE":
        if not texto.isdigit() or not 18 <= int(texto) <= 110:
            await update.message.reply_text(
                "Digite uma idade válida, entre 18 e 110 anos."
            )
            return

        context.user_data["idade"] = int(texto)

        await iniciar_triagem(update.message, context)
        return

    # =====================================================
    # DIÁRIO
    # =====================================================

    # -----------------------------------------------------
    # DIÁRIO: QUANTIDADE DE EPISÓDIOS DE CALOR
    # -----------------------------------------------------

    if estado_atual == "DIARIO_1":
        if not texto.isdigit() or not 0 <= int(texto) <= 100:
            await update.message.reply_text(
                "Digite um número entre 0 e 100: "
                "quantos episódios de calor você teve hoje?"
            )
            return

        context.user_data["diario_calores_qtd"] = int(texto)
        context.user_data["estado"] = "DIARIO_2"

        botoes = [
            [
                InlineKeyboardButton(
                    "Dormi mal",
                    callback_data="1",
                )
            ],
            [
                InlineKeyboardButton(
                    "Mais ou menos",
                    callback_data="2",
                )
            ],
            [
                InlineKeyboardButton(
                    "Dormi bem",
                    callback_data="3",
                )
            ],
        ]

        await update.message.reply_text(
            "Como foi seu sono esta noite?",
            reply_markup=InlineKeyboardMarkup(botoes),
        )
        return


# =========================================================
# DISPAROS AGENDADOS DO DIÁRIO
# =========================================================

async def verificador_de_horarios(
    context: ContextTypes.DEFAULT_TYPE,
):
    agora = datetime.datetime.now(TZ)

    if "ultima_hora_rodada" not in context.bot_data:
        context.bot_data["ultima_hora_rodada"] = -1

    if (
        agora.minute == 0
        and context.bot_data["ultima_hora_rodada"] != agora.hour
    ):
        context.bot_data["ultima_hora_rodada"] = agora.hour

        hora_formatada = f"{agora.hour:02d}:00"

        usuarios_da_hora = db.obter_usuarias_por_horario(
            hora_formatada
        )

        for chat_id in usuarios_da_hora:
            estado_usuario = context.application.user_data.setdefault(
                chat_id,
                {},
            )

            estado_usuario["estado"] = "DIARIO_1"

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "☀️ *Acompanhamento diário*\n\n"
                        "Quantos episódios de calor você teve hoje?"
                    ),
                    parse_mode="Markdown",
                )

            except Exception:
                logging.exception(
                    "Não foi possível enviar lembrete para o chat %s",
                    chat_id,
                )


# =========================================================
# INICIALIZAÇÃO DO BOT
# =========================================================

def main():
    db.init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "Defina a variável de ambiente TELEGRAM_BOT_TOKEN "
            "com o token do bot gerado pelo BotFather."
        )

    app = ApplicationBuilder().token(token).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("testardiario", forcar_diario)
    )

    app.add_handler(
        CallbackQueryHandler(roteador_botoes)
    )

    # Não há mais handler de localização.
    # Não há mais consulta de UBS.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            roteador_textos,
        )
    )

    app.job_queue.run_repeating(
        verificador_de_horarios,
        interval=60,
    )

    print("Calor Aviso iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()