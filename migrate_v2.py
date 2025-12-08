import sqlite3
import os

DB_PATH = "events.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ No se encontró {DB_PATH}")
        return

    print(f"🔄 Conectando a {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Crear tabla de PAREJAS (Teams)
    print("🛠 Creando tabla 'pairs'...")
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,  -- Opcional: "Los Invencibles", si no se pone, se genera automático
            p1_id INTEGER,
            p2_id INTEGER,
            FOREIGN KEY(p1_id) REFERENCES players(id),
            FOREIGN KEY(p2_id) REFERENCES players(id)
        )
    ''')

    # 2. Crear tabla de INSCRIPCIONES DE PAREJAS A LIGAS
    # (Sustituye conceptualmente a league_players)
    print("🛠 Creando tabla 'league_pairs'...")
    cur.execute('''
        CREATE TABLE IF NOT EXISTS league_pairs (
            league_id INTEGER,
            pair_id INTEGER,
            PRIMARY KEY (league_id, pair_id),
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE,
            FOREIGN KEY(pair_id) REFERENCES pairs(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print("\n✅ MIGRACIÓN COMPLETADA. Ahora puedes ejecutar app.py")

if __name__ == "__main__":
    migrate()