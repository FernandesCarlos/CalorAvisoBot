import sqlite3
import datetime
import pytz

NOME_BANCO = "saude_mulher.db"

def conectar():
    return sqlite3.connect(NOME_BANCO)

def init_db():
    """Cria as tabelas no banco de dados com base na estrutura do MVP."""
    conn = conectar()
    cursor = conn.cursor()
    
    # 1. Tabela de mulheres (Dados pessoais mínimos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarias (
            identificador INTEGER PRIMARY KEY, -- É o chat_id do Telegram
            apelido TEXT,
            bairro TEXT,
            consentimento INTEGER, -- 1 para Sim
            -- (Campos de triagem mantidos para o algoritmo funcionar)
            idade INTEGER,
            ciclo TEXT,
            calores_triagem TEXT,
            sono_triagem TEXT,
            humor_triagem TEXT,
            ativo INTEGER DEFAULT 1,
            data_cadastro DATETIME,
            horario_diario TEXT DEFAULT '18:00'
        )
    """)
    
    # 2. Tabela de registros diários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_diarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador INTEGER,
            data TEXT,
            calores INTEGER,
            sono TEXT,
            humor TEXT,
            FOREIGN KEY(identificador) REFERENCES usuarias(identificador)
        )
    """)
    
    # 3. Tabela de episódios de calor (Registro de momento exato)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodios_calor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador INTEGER,
            data TEXT,
            hora TEXT,
            temperatura_dia REAL, -- Temperatura climática da cidade no momento
            FOREIGN KEY(identificador) REFERENCES usuarias(identificador)
        )
    """)
    
    conn.commit()
    conn.close()

def pegar_data_hora_atual():
    fuso = pytz.timezone("America/Sao_Paulo")
    agora = datetime.datetime.now(fuso)
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M")
    completo = agora.strftime("%Y-%m-%d %H:%M:%S")
    return data, hora, completo


def salvar_usuaria(identificador, dados):
    """Salva os dados da usuária, incluindo o nome informado no cadastro."""
    _, _, data_completa = pegar_data_hora_atual()

    # O cadastro coleta nome_completo, não apelido.
    nome = (
        dados.get("nome_completo")
        or dados.get("apelido")
        or ""
    ).strip()

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO usuarias
        (
            identificador,
            apelido,
            bairro,
            consentimento,
            idade,
            ciclo,
            calores_triagem,
            sono_triagem,
            humor_triagem,
            ativo,
            data_cadastro
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (
        identificador,
        nome,
        dados.get("bairro"),
        1,
        dados.get("idade"),
        dados.get("ciclo"),
        dados.get("calores"),
        dados.get("sono"),
        dados.get("humor"),
        data_completa
    ))

    conn.commit()
    conn.close()


def salvar_diario(identificador, calores_qtd, sono, humor):
    """Salva as perguntas do dia a dia."""
    data, _, _ = pegar_data_hora_atual()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registros_diarios (identificador, data, calores, sono, humor)
        VALUES (?, ?, ?, ?, ?)
    """, (identificador, data, calores_qtd, sono, humor))
    conn.commit()
    conn.close()

def registrar_episodio_calor(identificador, temperatura_ambiente=None):
    """Salva o episódio avulso separando data, hora e a temperatura externa."""
    data, hora, _ = pegar_data_hora_atual()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO episodios_calor (identificador, data, hora, temperatura_dia)
        VALUES (?, ?, ?, ?)
    """, (identificador, data, hora, temperatura_ambiente))
    conn.commit()
    conn.close()

# --- Funções auxiliares mantidas ---
def salvar_horario_diario(identificador, horario):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarias SET horario_diario = ? WHERE identificador = ?", (horario, identificador))
    conn.commit()
    conn.close()

def obter_usuarias_por_horario(horario):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT identificador FROM usuarias WHERE ativo = 1 AND horario_diario = ?", (horario,))
    linhas = cursor.fetchall()
    conn.close()
    return [linha[0] for linha in linhas]

def usuaria_ja_cadastrada(identificador):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT identificador FROM usuarias WHERE identificador = ?", (identificador,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

def deletar_dados_usuaria(identificador):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros_diarios WHERE identificador = ?", (identificador,))
    cursor.execute("DELETE FROM episodios_calor WHERE identificador = ?", (identificador,))
    cursor.execute("DELETE FROM usuarias WHERE identificador = ?", (identificador,))
    conn.commit()
    conn.close()

def obter_relatorio_calores(identificador):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(calores) FROM registros_diarios WHERE identificador = ?", (identificador,))
    total_diario = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM episodios_calor WHERE identificador = ?", (identificador,))
    total_avulsos = cursor.fetchone()[0] or 0
    conn.close()
    return total_diario + total_avulsos


def obter_dados_completos_relatorio(identificador):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT apelido, data_cadastro
        FROM usuarias
        WHERE identificador = ?
    """, (identificador,))

    perfil = cursor.fetchone()

    if not perfil:
        conn.close()
        return None

    nome = (perfil[0] or "").strip()
    data_cadastro = perfil[1]

    cursor.execute("""
        SELECT data, calores, sono, humor
        FROM registros_diarios
        WHERE identificador = ?
    """, (identificador,))

    diarios = cursor.fetchall()

    cursor.execute("""
        SELECT data, hora
        FROM episodios_calor
        WHERE identificador = ?
    """, (identificador,))

    avulsos = cursor.fetchall()

    conn.close()

    diarios_formatados = [
        (f"{d[0]} 00:00:00", d[1], d[2], d[3])
        for d in diarios
    ]

    avulsos_formatados = [
        (f"{a[0]} {a[1]}:00",)
        for a in avulsos
    ]

    return {
        "nome_completo": nome or "Nome não informado",
        "apelido": nome,
        "data_cadastro": data_cadastro,
        "diarios": diarios_formatados,
        "avulsos": avulsos_formatados
    }
