import sqlite3

def visualizar_dados():
    # Conecta ao arquivo do banco de dados
    conn = sqlite3.connect("saude_mulher.db")
    cursor = conn.cursor()

    print("\n--- 👩‍🦰 USUÁRIAS CADASTRADAS ---")
    cursor.execute("SELECT chat_id, apelido, idade, data_cadastro FROM usuarias")
    usuarias = cursor.fetchall()
    if not usuarias:
        print("Nenhuma usuária cadastrada ainda.")
    for u in usuarias:
        print(f"ID: {u[0]} | Apelido: {u[1]} | Idade: {u[2]} | Cadastrada em: {u[3]}")

    print("\n--- ☀️ REGISTROS DO DIÁRIO ---")
    cursor.execute("SELECT chat_id, data_registro, calores_qtd, sono, humor FROM diario")
    diarios = cursor.fetchall()
    if not diarios:
        print("Nenhum registro diário ainda.")
    for d in diarios:
        print(f"ID: {d[0]} | Data: {d[1]} | Calores: {d[2]} | Sono: {d[3]} | Humor: {d[4]}")

    print("\n--- 🔥 CALORES AVULSOS (Quando digita 'calor') ---")
    cursor.execute("SELECT chat_id, data_hora FROM calores_avulsos")
    calores = cursor.fetchall()
    if not calores:
        print("Nenhum calor avulso registrado.")
    for c in calores:
        print(f"ID: {c[0]} | Registrado às: {c[1]}")

    print("\n-----------------------------------\n")
    conn.close()

if __name__ == "__main__":
    visualizar_dados()