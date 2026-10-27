import datetime
import pytz
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TEXTO_COMANDOS = (
    "📌 **O que você pode fazer a qualquer momento:**\n"
    "🔥 Escreva **calor** - Para registrar uma onda de calor na mesma hora.\n"
    "📊 Escreva **relatório** - Para ver o seu gráfico e estatísticas.\n"
    "🗑️ Escreva **deletar** - Para apagar todos os seus dados do sistema."
)

# --- FUNÇÕES DE AUXÍLIO ---
def verificar_emergencia(texto: str) -> str:
    texto = texto.lower()
    if any(p in texto for p in ["desespero", "me machucar", "suicídio", "suicidio", "matar", "morrer"]):
        return "EMOCIONAL"
    if any(p in texto for p in ["sangramento", "dor forte", "não estou aguentando", "não aguento mais"]):
        return "FISICO"
    return "NENHUM"

def avaliar_triagem(dados: dict) -> bool:
    idade = dados.get("idade", 0)
    sintomas = 0
    if dados.get("ciclo") == "1": sintomas += 1
    if dados.get("calores") in ["1", "2"]: sintomas += 1
    if dados.get("sono") in ["1", "2"]: sintomas += 1
    if dados.get("humor") in ["1", "2"]: sintomas += 1
    return (40 <= idade <= 55) and (sintomas >= 2)


# --- COMANDO INICIAL ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if db.usuaria_ja_cadastrada(chat_id):
        context.user_data["estado"] = "CONCLUIDO"
        await update.message.reply_text(
            f"Olá novamente! 👋 Seu registro está ativo.\n\n{TEXTO_COMANDOS}",
            parse_mode="Markdown"
        )
        return

    context.user_data.clear()
    context.user_data["estado"] = "CONSENTIMENTO"
    
    mensagem_apresentacao = (
        "Olá! 👋 Eu sou a sua assistente virtual de saúde da mulher.\n\n"
        "Estou aqui para te ajudar a entender e acompanhar os seus sintomas do dia a dia, "
        "especialmente nesta fase de transição da menopausa.\n\n"
        "💡 **Dicas importantes de como funciono:**\n"
        "• **Ondas de calor:** Se sentir um calorão, escreva a palavra **calor** aqui no chat a qualquer hora, e eu anoto.\n"
        "• **Sinais de alerta:** Se você mandar mensagens sobre **dor forte**, **sangramento intenso** "
        "ou **desespero**, eu vou pausar as perguntas na hora para te orientar sobre onde buscar ajuda imediata.\n\n"
        "🔒 **Sua privacidade:** Seus dados servem apenas para o seu acompanhamento. Você pode apagar tudo escrevendo **deletar** quando quiser.\n\n"
        "Posso começar algumas perguntinhas rápidas para te conhecer melhor?"
    )
    
    botoes = [[InlineKeyboardButton("SIM", callback_data="sim"), InlineKeyboardButton("NÃO", callback_data="nao")]]
    await update.message.reply_text(mensagem_apresentacao, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")


# --- COMANDO DE TESTE (Opção de viagem no tempo/diário forçado) ---
async def forcar_diario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.application.user_data[chat_id]["estado"] = "DIARIO_1"
    await context.bot.send_message(
        chat_id=chat_id,
        text="☀️ **[TESTE] Acompanhamento Diário:**\n\nQuantos calores você teve hoje? (Digite no teclado)",
        parse_mode="Markdown"
    )


# --- ROTEADOR DE CLIQUES NOS BOTÕES (INLINE) ---
async def roteador_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    resposta = query.data 
    estado_atual = context.user_data.get("estado")
    chat_id = query.message.chat_id
    
    await query.edit_message_reply_markup(reply_markup=None)

    # 1. HORÁRIO E DELETAR
    if resposta.startswith("h_"):
        horario_escolhido = resposta.split("_")[1]
        db.salvar_horario_diario(chat_id, horario_escolhido)
        
        context.user_data["estado"] = "DIARIO_1"
        await query.message.reply_text(
            f"⏰ Combinado! Vou te enviar o diário todos os dias às **{horario_escolhido}**.\n\n"
            "☀️ **Para já começarmos o seu registro de hoje:**\n\nQuantos calores você teve hoje? (Digite no teclado)", 
            parse_mode="Markdown"
        )
        return

    if resposta == "confirmar_delete":
        db.deletar_dados_usuaria(chat_id)
        context.user_data.clear()
        await query.message.reply_text("🗑️ Todos os seus dados foram apagados com sucesso.\nSe quiser voltar no futuro, basta mandar /start.")
        return
    elif resposta == "cancelar_delete":
        await query.message.reply_text("✅ Operação cancelada. Seus dados continuam seguros e armazenados.")
        return

    # 2. FLUXO DE TRIAGEM
    if estado_atual == "CONSENTIMENTO":
        if resposta == "sim":
            context.user_data["estado"] = "APELIDO"
            botoes = [[InlineKeyboardButton("Pular", callback_data="pular")]]
            await query.message.reply_text("Ótimo! Qual o seu apelido? (Ou digite no teclado)", reply_markup=InlineKeyboardMarkup(botoes))
        elif resposta == "nao":
            context.user_data["estado"] = "CONCLUIDO"
            await query.message.reply_text("Tudo bem! Seus dados não foram registrados. Caso mude de ideia, basta digitar /start. Cuide-se! 🌻")
        return
        
    elif estado_atual == "APELIDO" and resposta == "pular":
        context.user_data["apelido"] = None
        context.user_data["estado"] = "BAIRRO"
        botoes = [[InlineKeyboardButton("Pular", callback_data="pular")]]
        await query.message.reply_text("De qual bairro você é? (Ou digite no teclado)", reply_markup=InlineKeyboardMarkup(botoes))
        
    elif estado_atual == "BAIRRO" and resposta == "pular":
        context.user_data["bairro"] = None
        context.user_data["estado"] = "IDADE"
        await query.message.reply_text("Quantos anos você tem? (Digite o número no teclado)")

    elif estado_atual == "CICLO":
        context.user_data["ciclo"] = resposta
        context.user_data["estado"] = "CALORES_TRIAGEM"
        botoes = [
            [InlineKeyboardButton("Sim, sempre", callback_data="1")],
            [InlineKeyboardButton("Às vezes", callback_data="2")],
            [InlineKeyboardButton("Não", callback_data="3")]
        ]
        await query.message.reply_text("Você sente ondas de calor ou acorda suando à noite?", reply_markup=InlineKeyboardMarkup(botoes))

    elif estado_atual == "CALORES_TRIAGEM":
        context.user_data["calores"] = resposta
        context.user_data["estado"] = "SONO_TRIAGEM"
        botoes = [
            [InlineKeyboardButton("Sim", callback_data="1"), InlineKeyboardButton("Um pouco", callback_data="2")],
            [InlineKeyboardButton("Não", callback_data="3")]
        ]
        await query.message.reply_text("Seu sono piorou ultimamente?", reply_markup=InlineKeyboardMarkup(botoes))

    elif estado_atual == "SONO_TRIAGEM":
        context.user_data["sono"] = resposta
        context.user_data["estado"] = "HUMOR_TRIAGEM"
        botoes = [
            [InlineKeyboardButton("Sim", callback_data="1"), InlineKeyboardButton("Um pouco", callback_data="2")],
            [InlineKeyboardButton("Não", callback_data="3")]
        ]
        await query.message.reply_text("Você tem se sentido mais irritada, ansiosa ou esquecida do que antes?", reply_markup=InlineKeyboardMarkup(botoes))

    elif estado_atual == "HUMOR_TRIAGEM":
        context.user_data["humor"] = resposta
        db.salvar_usuaria(chat_id, context.user_data)
        
        if avaliar_triagem(context.user_data):
            await query.message.reply_text("📝 **Resultado:** Pelas suas respostas, você apresenta sinais compatíveis com a transição da menopausa. Procure sua UBS!", parse_mode="Markdown")
        else:
            await query.message.reply_text("✅ Triagem finalizada!")
        
        context.user_data["estado"] = "ESCOLHER_HORARIO"
        botoes_horario = [
            [InlineKeyboardButton("08:00", callback_data="h_08:00"), InlineKeyboardButton("10:00", callback_data="h_10:00"), InlineKeyboardButton("12:00", callback_data="h_12:00")],
            [InlineKeyboardButton("14:00", callback_data="h_14:00"), InlineKeyboardButton("16:00", callback_data="h_16:00"), InlineKeyboardButton("18:00", callback_data="h_18:00")],
            [InlineKeyboardButton("20:00", callback_data="h_20:00"), InlineKeyboardButton("22:00", callback_data="h_22:00")]
        ]
        await query.message.reply_text(
            "Em qual horário você prefere receber as perguntinhas do diário?",
            reply_markup=InlineKeyboardMarkup(botoes_horario)
        )

    # 3. DIÁRIO E SEMANAL
    elif estado_atual == "DIARIO_2":
        context.user_data["diario_sono"] = resposta
        context.user_data["estado"] = "DIARIO_3"
        botoes = [
            [InlineKeyboardButton("Mal", callback_data="1"), InlineKeyboardButton("Normal", callback_data="2")],
            [InlineKeyboardButton("Bem", callback_data="3")]
        ]
        await query.message.reply_text("Como está o seu humor hoje?", reply_markup=InlineKeyboardMarkup(botoes))

    elif estado_atual == "DIARIO_3":
        context.user_data["diario_humor"] = resposta
        context.user_data["estado"] = "CONCLUIDO"
        db.salvar_diario(chat_id, context.user_data.get("diario_calores_qtd"), context.user_data.get("diario_sono"), context.user_data.get("diario_humor"))
        await query.message.reply_text(f"Obrigado pelo seu registro diário! 🌻\n\n{TEXTO_COMANDOS}", parse_mode="Markdown")

    elif estado_atual == "SEMANAL_1":
        context.user_data["estado"] = "CONCLUIDO"
        # Semanal usa a mesma estrutura, guardamos noutro local se necessário, 
        # mas aqui finalizamos o estado
        await query.message.reply_text(f"Obrigado pelo registro da semana! 🌻\n\n{TEXTO_COMANDOS}", parse_mode="Markdown")


# --- ROTEADOR DE TEXTOS DIGITADOS ---
async def roteador_textos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    texto_lower = texto.lower()
    estado_atual = context.user_data.get("estado", "CONCLUIDO")
    chat_id = update.message.chat_id
    
    # 1. VERIFICAÇÃO DE EMERGÊNCIA
    tipo_emergencia = verificar_emergencia(texto)
    if tipo_emergencia == "EMOCIONAL":
        context.user_data["estado"] = "CONCLUIDO"
        await update.message.reply_text("🚨 Atenção: Percebi que você está passando por um momento muito difícil.\n\nPor favor, procure ajuda imediatamente. Ligue para o 188 (CVV - Centro de Valorização da Vida) para apoio emocional gratuito e sigiloso, ou vá até a UBS mais próxima. Você não está sozinha!")
        return
    elif tipo_emergencia == "FISICO":
        context.user_data["estado"] = "CONCLUIDO"
        await update.message.reply_text("🚨 **Alerta:** Esses sintomas precisam de avaliação médica. Procure a UBS o quanto antes.", parse_mode="Markdown")
        return

    # 2. MENU DE COMANDOS POR TEXTO
    if texto_lower in ["calor", "calores"]:
        agora = datetime.datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%H:%M")
        db.registrar_episodio_calor(chat_id, temperatura_ambiente=None)
        await update.message.reply_text(f"🔥 Registrado! Calor anotado às {agora}.")
        return

    if texto_lower in ["relatório", "relatorio"]:
        await update.message.reply_text("📊 Gerando o seu relatório visual. Só um momento...")
        dados_relatorio = db.obter_dados_completos_relatorio(chat_id)
        if not dados_relatorio:
            await update.message.reply_text("Ainda não tenho dados suficientes para gerar o seu relatório. Continue usando o bot!")
            return
            
        imagem_png = gerador_relatorio.gerar_png_relatorio(dados_relatorio)
        await update.message.reply_photo(
            photo=imagem_png,
            caption="Aqui está o seu relatório detalhado! Você pode salvar essa imagem e levar na sua próxima consulta. 🌻"
        )
        return

    if texto_lower == "deletar":
        botoes = [
            [InlineKeyboardButton("Sim, apagar tudo", callback_data="confirmar_delete")],
            [InlineKeyboardButton("Cancelar", callback_data="cancelar_delete")]
        ]
        await update.message.reply_text(
            "⚠️ **Atenção!** Esta ação vai apagar **TODOS** os seus dados e o seu histórico de acompanhamento.\n\nTem certeza de que deseja excluir sua conta?",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown"
        )
        return

    # 3. TRATAMENTO DA TRIAGEM E DIÁRIO
    if estado_atual == "APELIDO":
        context.user_data["apelido"] = texto
        context.user_data["estado"] = "BAIRRO"
        botoes = [[InlineKeyboardButton("Pular", callback_data="pular")]]
        await update.message.reply_text("De qual bairro você é? (Ou clique em pular)", reply_markup=InlineKeyboardMarkup(botoes))
        
    elif estado_atual == "BAIRRO":
        context.user_data["bairro"] = texto
        context.user_data["estado"] = "IDADE"
        await update.message.reply_text("Quantos anos você tem? (Digite apenas números)")
        
    elif estado_atual == "IDADE":
        if not texto.isdigit():
            await update.message.reply_text("⚠️ Digite apenas números para a sua idade.")
            return
        context.user_data["idade"] = int(texto)
        context.user_data["estado"] = "CICLO"
        botoes = [
            [InlineKeyboardButton("Sim, mudou", callback_data="1")],
            [InlineKeyboardButton("Não mudou", callback_data="2")],
            [InlineKeyboardButton("Já não menstruo", callback_data="3")]
        ]
        await update.message.reply_text("Sua menstruação mudou nos últimos meses?", reply_markup=InlineKeyboardMarkup(botoes))

    elif estado_atual == "DIARIO_1":
        if not texto.isdigit():
            await update.message.reply_text("⚠️ Digite um número. Quantos calores você teve hoje?")
            return
        context.user_data["diario_calores_qtd"] = int(texto)
        context.user_data["estado"] = "DIARIO_2"
        botoes = [
            [InlineKeyboardButton("Dormi mal", callback_data="1")],
            [InlineKeyboardButton("Mais ou menos", callback_data="2")],
            [InlineKeyboardButton("Dormi bem", callback_data="3")]
        ]
        await update.message.reply_text("Como foi o seu sono esta noite?", reply_markup=InlineKeyboardMarkup(botoes))


# --- DISPAROS AGENDADOS DINÂMICOS ---
async def verificador_de_horarios(context: ContextTypes.DEFAULT_TYPE):
    agora = datetime.datetime.now(pytz.timezone("America/Sao_Paulo"))
    
    if "ultima_hora_rodada" not in context.bot_data:
        context.bot_data["ultima_hora_rodada"] = -1
        
    if agora.minute == 0 and context.bot_data["ultima_hora_rodada"] != agora.hour:
        context.bot_data["ultima_hora_rodada"] = agora.hour
        hora_formatada = f"{agora.hour:02d}:00" 
        
        usuarios_da_hora = db.obter_usuarias_por_horario(hora_formatada)
        for chat_id in usuarios_da_hora:
            context.application.user_data[chat_id]["estado"] = "DIARIO_1"
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="☀️ **Acompanhamento Diário:**\n\nQuantos calores você teve hoje? (Digite no teclado)",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


def main():
    db.init_db()

    TOKEN = "9016700340:AAGOrx-1KQTE-lJKDE5FFQyafan0_RUG4ms" 
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testardiario", forcar_diario)) 
    app.add_handler(CallbackQueryHandler(roteador_botoes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, roteador_textos))

    # O bot verifica o relógio a cada 60 segundos
    app.job_queue.run_repeating(verificador_de_horarios, interval=60)

    print("Bot rodando com escolha de horários, relatórios em PNG e MVP DB...")
    app.run_polling()

if __name__ == "__main__":
    main()