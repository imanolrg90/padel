from flask import Flask, request, jsonify, render_template, g
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "events.db")

app = Flask(__name__, static_folder='static', template_folder='templates')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    # Tabla de jugadores
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT
        )
        '''
    )

    # Tabla de eventos / partidos: 4 jugadores (dos parejas), marcador y estado
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT,
            allDay INTEGER DEFAULT 0,
            p1 INTEGER,
            p2 INTEGER,
            p3 INTEGER,
            p4 INTEGER,
            played INTEGER DEFAULT 0,
            score TEXT,
            winner INTEGER,
            FOREIGN KEY(p1) REFERENCES players(id),
            FOREIGN KEY(p2) REFERENCES players(id),
            FOREIGN KEY(p3) REFERENCES players(id),
            FOREIGN KEY(p4) REFERENCES players(id)
        )
        '''
    )
    db.commit()


# Inicializar la base de datos al arrancar la aplicación.
# Algunos entornos de Flask no exponen `before_first_request` como decorador,
# así que ejecutamos la inicialización directamente dentro del contexto de la app.
with app.app_context():
    init_db()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/events', methods=['GET'])
def get_events():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, title, start, end, allDay, p1, p2, p3, p4, played, score, winner FROM events')
    rows = cur.fetchall()
    events = []
    for r in rows:
        events.append({
            'id': r['id'],
            'title': r['title'],
            'start': r['start'],
            'end': r['end'],
            'allDay': bool(r['allDay']),
            'p1': r['p1'],
            'p2': r['p2'],
            'p3': r['p3'],
            'p4': r['p4'],
            'played': bool(r['played']),
            'score': r['score'],
            'winner': r['winner']
        })
    return jsonify(events)


@app.route('/api/events', methods=['POST'])
def create_event():
    data = request.get_json(force=True)
    title = data.get('title')
    start = data.get('start')
    end = data.get('end')
    allDay = 1 if data.get('allDay') else 0
    p1 = data.get('p1')
    p2 = data.get('p2')
    p3 = data.get('p3')
    p4 = data.get('p4')

    # Validaciones básicas: deben existir y ser distintos
    try:
        players = [int(p) for p in (p1, p2, p3, p4)]
    except Exception:
        return jsonify({'error': 'Los cuatro jugadores deben estar seleccionados y ser IDs válidos'}), 400

    if len(set(players)) != 4:
        return jsonify({'error': 'Los cuatro jugadores deben ser distintos'}), 400

    # Comprobar que los players existen
    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*) as cnt FROM players WHERE id IN (?,?,?,?)', tuple(players))
    cnt = cur.fetchone()['cnt']
    if cnt != 4:
        return jsonify({'error': 'Algún jugador seleccionado no existe'}), 400

    if not title or not start:
        return jsonify({'error': 'title and start are required'}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute('INSERT INTO events (title, start, end, allDay, p1, p2, p3, p4) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (title, start, end, allDay, p1, p2, p3, p4))
    db.commit()
    event_id = cur.lastrowid

    return jsonify({
        'id': event_id,
        'title': title,
        'start': start,
        'end': end,
        'allDay': bool(allDay),
        'p1': p1,
        'p2': p2,
        'p3': p3,
        'p4': p4,
        'played': False,
        'score': None,
        'winner': None
    }), 201


@app.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    data = request.get_json(force=True)
    title = data.get('title')
    start = data.get('start')
    end = data.get('end')
    allDay = 1 if data.get('allDay') else 0
    p1 = data.get('p1')
    p2 = data.get('p2')
    p3 = data.get('p3')
    p4 = data.get('p4')

    # Validaciones similares a create
    try:
        players = [int(p) for p in (p1, p2, p3, p4)]
    except Exception:
        return jsonify({'error': 'Los cuatro jugadores deben estar seleccionados y ser IDs válidos'}), 400

    if len(set(players)) != 4:
        return jsonify({'error': 'Los cuatro jugadores deben ser distintos'}), 400

    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*) as cnt FROM players WHERE id IN (?,?,?,?)', tuple(players))
    cnt = cur.fetchone()['cnt']
    if cnt != 4:
        return jsonify({'error': 'Algún jugador seleccionado no existe'}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute('''
        UPDATE events SET title=?, start=?, end=?, allDay=?, p1=?, p2=?, p3=?, p4=? WHERE id=?
    ''', (title, start, end, allDay, p1, p2, p3, p4, event_id))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM events WHERE id=?', (event_id,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/events/<int:event_id>/result', methods=['POST'])
def set_event_result(event_id):
    data = request.get_json(force=True)
    score = data.get('score')
    winner = data.get('winner')  # 1 or 2
    if winner not in (1, 2):
        return jsonify({'error': 'winner must be 1 or 2'}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute('UPDATE events SET played=1, score=?, winner=? WHERE id=?', (score, winner, event_id))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    db = get_db()
    cur = db.cursor()
    # Cargar jugadores
    cur.execute('SELECT id, first_name, last_name FROM players')
    players = {r['id']: {'id': r['id'], 'first_name': r['first_name'], 'last_name': r['last_name'], 'played': 0, 'wins': 0} for r in cur.fetchall()}

    # Cargar eventos jugados
    cur.execute('SELECT p1,p2,p3,p4,winner FROM events WHERE played=1')
    rows = cur.fetchall()
    for r in rows:
        p1,p2,p3,p4,winner = r['p1'], r['p2'], r['p3'], r['p4'], r['winner']
        for pid in (p1,p2,p3,p4):
            if pid in players:
                players[pid]['played'] += 1
        if winner == 1:
            # pareja A (p1,p2) ganaron
            if p1 in players: players[p1]['wins'] += 1
            if p2 in players: players[p2]['wins'] += 1
        elif winner == 2:
            if p3 in players: players[p3]['wins'] += 1
            if p4 in players: players[p4]['wins'] += 1

    # Preparar lista ordenada
    out = []
    for p in players.values():
        played = p['played']
        wins = p['wins']
        losses = played - wins
        win_rate = (wins / played * 100) if played > 0 else 0
        out.append({'id': p['id'], 'first_name': p['first_name'], 'last_name': p['last_name'], 'played': played, 'wins': wins, 'losses': losses, 'win_rate': round(win_rate,2)})

    out.sort(key=lambda x: x['wins'], reverse=True)
    return jsonify(out)


@app.route('/stats')
def stats_page():
    return render_template('stats.html')


@app.route('/players')
def players_page():
    return render_template('players.html')


@app.route('/api/players', methods=['GET'])
def get_players():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, first_name, last_name FROM players')
    rows = cur.fetchall()
    players = []
    for r in rows:
        players.append({'id': r['id'], 'first_name': r['first_name'], 'last_name': r['last_name']})
    return jsonify(players)


@app.route('/api/players', methods=['POST'])
def create_player():
    data = request.get_json(force=True)
    first = data.get('first_name')
    last = data.get('last_name')
    if not first:
        return jsonify({'error': 'first_name required'}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute('INSERT INTO players (first_name, last_name) VALUES (?, ?)', (first, last))
    db.commit()
    pid = cur.lastrowid
    return jsonify({'id': pid, 'first_name': first, 'last_name': last}), 201


@app.route('/api/players/<int:player_id>', methods=['PUT'])
def update_player(player_id):
    data = request.get_json(force=True)
    first = data.get('first_name')
    last = data.get('last_name')
    db = get_db()
    cur = db.cursor()
    cur.execute('UPDATE players SET first_name=?, last_name=? WHERE id=?', (first, last, player_id))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/players/<int:player_id>', methods=['DELETE'])
def delete_player(player_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM players WHERE id=?', (player_id,))
    db.commit()
    return jsonify({'ok': True})


if __name__ == '__main__':
    # Ejecutar directamente: servidor en el puerto 5001
    app.run(host='0.0.0.0', port=5001, debug=True)
