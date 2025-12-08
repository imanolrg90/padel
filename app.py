from flask import Flask, request, jsonify, render_template, g
import sqlite3
import os
import itertools

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
    # La inicialización base se maneja con migrate_v3.py, aquí aseguramos lo básico
    with app.app_context():
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT, elo INTEGER DEFAULT 1000)')
        db.execute('CREATE TABLE IF NOT EXISTS leagues (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT)')
        # Events y demás tablas se asumen creadas por migraciones previas
        db.commit()

# --- HELPERS ---
def calculate_elo_change(rating_a, rating_b, actual_score):
    K = 32
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    return round(K * (actual_score - expected_a))

def format_score_string(r):
    parts = []
    if r['s1_a'] > 0 or r['s1_b'] > 0: parts.append(f"{r['s1_a']}-{r['s1_b']}")
    if r['s2_a'] > 0 or r['s2_b'] > 0: parts.append(f"{r['s2_a']}-{r['s2_b']}")
    if r['s3_a'] > 0 or r['s3_b'] > 0: parts.append(f"{r['s3_a']}-{r['s3_b']}")
    return " ".join(parts)

def enrich_event(r, pmap):
    evt = dict(r)
    evt['p1_name'] = pmap.get(evt['p1'], 'J1')
    evt['p2_name'] = pmap.get(evt['p2'], 'J2')
    evt['p3_name'] = pmap.get(evt['p3'], 'J3')
    evt['p4_name'] = pmap.get(evt['p4'], 'J4')
    evt['score_str'] = format_score_string(evt)
    evt['description'] = evt['description'] if evt['description'] else ""
    return evt

# --- VISTAS ---
@app.route('/')
def index(): return render_template('index.html')
@app.route('/players')
def players_page(): return render_template('players.html')
@app.route('/leagues')
def leagues_page(): return render_template('leagues.html')
@app.route('/history')
def history_page(): return render_template('history.html')
@app.route('/stats')
def stats_page(): return render_template('stats.html')

# --- API BASIC ---
@app.route('/api/players', methods=['GET', 'POST'])
def handle_players():
    db = get_db()
    if request.method == 'GET':
        cur = db.cursor()
        cur.execute('SELECT * FROM players ORDER BY first_name ASC, last_name ASC')
        return jsonify([dict(row) for row in cur.fetchall()])
    else:
        d = request.get_json(force=True)
        cur = db.cursor()
        cur.execute('INSERT INTO players (first_name, last_name) VALUES (?, ?)', (d.get('first_name'), d.get('last_name')))
        db.commit()
        return jsonify({'id': cur.lastrowid}), 201

@app.route('/api/players/<int:pid>', methods=['PUT', 'DELETE'])
def update_player(pid):
    db = get_db()
    if request.method == 'DELETE':
        db.execute('DELETE FROM players WHERE id=?', (pid,))
    else:
        d = request.get_json(force=True)
        db.execute('UPDATE players SET first_name=?, last_name=?, elo=? WHERE id=?', (d['first_name'], d['last_name'], d['elo'], pid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/leagues', methods=['GET', 'POST'])
def handle_leagues():
    db = get_db()
    if request.method == 'GET':
        cur = db.cursor()
        cur.execute('SELECT * FROM leagues ORDER BY id DESC')
        return jsonify([dict(row) for row in cur.fetchall()])
    else:
        d = request.get_json(force=True)
        db.execute('INSERT INTO leagues (name, description) VALUES (?, ?)', (d['name'], d.get('description','')))
        db.commit()
        return jsonify({'ok': True})

@app.route('/api/leagues/<int:lid>', methods=['PUT', 'DELETE'])
def update_or_delete_league(lid):
    db = get_db()
    if request.method == 'DELETE':
        db.execute('DELETE FROM leagues WHERE id=?', (lid,))
        db.commit()
        return jsonify({'ok': True})
    else:
        # Lógica de EDICIÓN (PUT)
        d = request.get_json(force=True)
        db.execute('UPDATE leagues SET name=?, description=? WHERE id=?', 
                   (d['name'], d.get('description',''), lid))
        db.commit()
        return jsonify({'ok': True})

# --- GESTIÓN PAREJAS ---
@app.route('/api/pairs', methods=['POST'])
def create_pair():
    d = request.get_json(force=True)
    p1, p2 = int(d['p1']), int(d['p2'])
    if p1 == p2: return jsonify({'error': 'Jugadores iguales'}), 400
    
    db = get_db()
    cur = db.cursor()
    # Verificar si existe (p1,p2) o (p2,p1)
    cur.execute('SELECT id FROM pairs WHERE (p1_id=? AND p2_id=?) OR (p1_id=? AND p2_id=?)', (p1, p2, p2, p1))
    ex = cur.fetchone()
    if ex: return jsonify({'id': ex['id'], 'exists': True})

    cur.execute('SELECT first_name, last_name FROM players WHERE id IN (?,?)', (p1, p2))
    rows = cur.fetchall()
    names = [f"{r['first_name']} {r['last_name'] or ''}".strip() for r in rows]
    # Nombre automático: "Juan & Pedro"
    pname = f"{names[0]} & {names[1]}" if len(names)==2 else "Pareja Nueva"
    
    cur.execute('INSERT INTO pairs (name, p1_id, p2_id) VALUES (?, ?, ?)', (pname, p1, p2))
    db.commit()
    return jsonify({'id': cur.lastrowid, 'name': pname})

@app.route('/api/leagues/<int:lid>/pairs', methods=['GET', 'POST'])
def league_pairs(lid):
    db = get_db()
    if request.method == 'GET':
        cur = db.cursor()
        cur.execute('''
            SELECT pr.id, pr.name, pr.p1_id, pr.p2_id 
            FROM pairs pr JOIN league_pairs lp ON pr.id = lp.pair_id
            WHERE lp.league_id = ?
        ''', (lid,))
        return jsonify([dict(r) for r in cur.fetchall()])
    else:
        d = request.get_json(force=True)
        try:
            db.execute('INSERT INTO league_pairs (league_id, pair_id) VALUES (?, ?)', (lid, d['pair_id']))
            db.commit()
            return jsonify({'ok': True})
        except: return jsonify({'error': 'Ya inscrita'}), 400

@app.route('/api/leagues/<int:lid>/pairs/<int:pid>', methods=['DELETE'])
def remove_league_pair(lid, pid):
    get_db().execute('DELETE FROM league_pairs WHERE league_id=? AND pair_id=?', (lid, pid))
    get_db().commit()
    return jsonify({'ok': True})

# --- EVENTOS ---
@app.route('/api/events', methods=['POST'])
def create_event():
    d = request.get_json(force=True)
    db = get_db()
    lid = d.get('league_id') or None
    try:
        p1, p2, p3, p4 = int(d['p1']), int(d['p2']), int(d['p3']), int(d['p4'])
        if len(set([p1,p2,p3,p4])) != 4: raise ValueError
    except: return jsonify({'error': 'Jugadores inválidos'}), 400

    is_played = d.get('played', False)
    winner, elo_diff = None, 0
    s1a, s1b, s2a, s2b, s3a, s3b = 0,0,0,0,0,0

    if is_played:
        def safe_int(v): return int(v) if (v and v!="") else 0
        s1a, s1b = safe_int(d.get('s1_a')), safe_int(d.get('s1_b'))
        s2a, s2b = safe_int(d.get('s2_a')), safe_int(d.get('s2_b'))
        s3a, s3b = safe_int(d.get('s3_a')), safe_int(d.get('s3_b'))
        winner = int(d.get('winner', 1))

        cur = db.cursor()
        cur.execute('SELECT id, elo FROM players WHERE id IN (?,?,?,?)', (p1, p2, p3, p4))
        elos = {r['id']: r['elo'] for r in cur.fetchall()}
        eloA = (elos[p1]+elos[p2])/2
        eloB = (elos[p3]+elos[p4])/2
        scoreA = 1 if winner == 1 else 0
        delta = calculate_elo_change(eloA, eloB, scoreA)
        
        cur.execute('UPDATE players SET elo=elo+? WHERE id IN (?,?)', (delta, p1, p2))
        cur.execute('UPDATE players SET elo=elo-? WHERE id IN (?,?)', (delta, p3, p4))
        elo_diff = abs(delta)

    db.execute('''
        INSERT INTO events (title, start, allDay, league_id, description, p1, p2, p3, p4, played, winner, elo_diff, s1_a, s1_b, s2_a, s2_b, s3_a, s3_b)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (d.get('title','Partido'), d['start'], lid, d.get('description',''), p1, p2, p3, p4, 1 if is_played else 0, winner, elo_diff, s1a, s1b, s2a, s2b, s3a, s3b))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/events/<int:eid>', methods=['PUT', 'DELETE'])
def update_event(eid):
    db = get_db()
    if request.method == 'DELETE':
        db.execute('DELETE FROM events WHERE id=?', (eid,))
    else:
        d = request.get_json(force=True)
        # Update simple (sin tocar resultado ni ELO, para eso borrar y crear de nuevo si está mal el resultado)
        db.execute('UPDATE events SET start=?, league_id=?, description=?, p1=?, p2=?, p3=?, p4=? WHERE id=?',
                   (d['start'], d.get('league_id'), d.get('description',''), d['p1'], d['p2'], d['p3'], d['p4'], eid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/events/<int:eid>/result', methods=['POST'])
def set_result(eid):
    d = request.get_json(force=True)
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT played, p1, p2, p3, p4, elo_diff FROM events WHERE id=?', (eid,))
    ev = cur.fetchone()
    if not ev: return jsonify({'error': 'No existe'}), 404
    
    # Solo calculamos ELO si NO se había jugado antes
    elo_diff = ev['elo_diff'] or 0
    winner = int(d.get('winner', 1))
    
    if not ev['played']:
        p1, p2, p3, p4 = ev['p1'], ev['p2'], ev['p3'], ev['p4']
        cur.execute('SELECT id, elo FROM players WHERE id IN (?,?,?,?)', (p1, p2, p3, p4))
        elos = {r['id']: r['elo'] for r in cur.fetchall()}
        delta = calculate_elo_change((elos[p1]+elos[p2])/2, (elos[p3]+elos[p4])/2, 1 if winner==1 else 0)
        cur.execute('UPDATE players SET elo=elo+? WHERE id IN (?,?)', (delta, p1, p2))
        cur.execute('UPDATE players SET elo=elo-? WHERE id IN (?,?)', (delta, p3, p4))
        elo_diff = abs(delta)

    def sint(v): return int(v) if v else 0
    db.execute('''UPDATE events SET played=1, winner=?, elo_diff=?, s1_a=?, s1_b=?, s2_a=?, s2_b=?, s3_a=?, s3_b=? WHERE id=?''',
               (winner, elo_diff, sint(d.get('s1_a')), sint(d.get('s1_b')), sint(d.get('s2_a')), sint(d.get('s2_b')), sint(d.get('s3_a')), sint(d.get('s3_b')), eid))
    db.commit()
    return jsonify({'ok': True})

# --- DATA FETCHING ---
@app.route('/api/matches/history', methods=['GET'])
def get_history():
    lid = request.args.get('league_id')
    pid = request.args.get('player_id')
    sql = 'SELECT e.*, l.name as league_name FROM events e LEFT JOIN leagues l ON e.league_id = l.id WHERE played=1'
    p = []
    if lid == 'friendly': sql += ' AND league_id IS NULL'
    elif lid: sql += ' AND league_id = ?'; p.append(lid)
    if pid: sql += ' AND (p1=? OR p2=? OR p3=? OR p4=?)'; p.extend([pid]*4)
    sql += ' ORDER BY start DESC, id DESC'
    
    cur = get_db().cursor()
    cur.execute(sql, tuple(p))
    rows = cur.fetchall()
    cur.execute("SELECT id, first_name, last_name FROM players")
    pmap = {r['id']: f"{r['first_name']} {r['last_name'] or ''}".strip() for r in cur.fetchall()}
    return jsonify([enrich_event(r, pmap) for r in rows])

@app.route('/api/matches/<status>', methods=['GET'])
def get_matches(status):
    is_played = 1 if status == 'recent' else 0
    cur = get_db().cursor()
    order, limit = ("ASC", "") if status == 'pending' else ("DESC", "LIMIT 5")
    cur.execute(f'SELECT e.*, l.name as league_name FROM events e LEFT JOIN leagues l ON e.league_id = l.id WHERE played=? ORDER BY start {order}, id {order} {limit}', (is_played,))
    rows = cur.fetchall()
    cur.execute("SELECT id, first_name, last_name FROM players")
    pmap = {r['id']: f"{r['first_name']} {r['last_name'] or ''}".strip() for r in cur.fetchall()}
    return jsonify([enrich_event(r, pmap) for r in rows])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    lid = request.args.get('league_id')
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, first_name, last_name, elo FROM players')
    pmap = {r['id']: {'name': f"{r['first_name']} {r['last_name'] or ''}".strip(), 'elo': r['elo']} for r in cur.fetchall()}
    
    sql = 'SELECT * FROM events WHERE played=1'
    params = []
    if lid: 
        sql += ' AND league_id = ?'
        params.append(lid)
        
    cur.execute(sql, tuple(params))
    matches = cur.fetchall()
    stats = {}

    for m in matches:
        if lid:
            # Modo Parejas
            idA = tuple(sorted((m['p1'], m['p2'])))
            idB = tuple(sorted((m['p3'], m['p4'])))
            teams = [{'id': idA, 'is_team_a': True}, {'id': idB, 'is_team_a': False}]
        else:
            # Modo Individual
            teams = [{'id': m['p1'], 'is_team_a': True}, {'id': m['p2'], 'is_team_a': True}, {'id': m['p3'], 'is_team_a': False}, {'id': m['p4'], 'is_team_a': False}]
        
        sets = [(m['s1_a'], m['s1_b']), (m['s2_a'], m['s2_b']), (m['s3_a'], m['s3_b'])]
        swA, swB, gwA, gwB = 0,0,0,0
        for (sa,sb) in sets:
            if sa==0 and sb==0: continue
            gwA+=sa; gwB+=sb
            if sa>sb: swA+=1
            elif sb>sa: swB+=1

        for t in teams:
            tid = t['id']
            if tid not in stats: stats[tid] = {'key': tid, 'played':0, 'wins':0, 'losses':0, 'sets_won':0, 'sets_lost':0, 'games_won':0, 'games_lost':0}
            s = stats[tid]
            s['played'] += 1
            
            isA = t['is_team_a']
            s['sets_won'] += swA if isA else swB
            s['sets_lost'] += swB if isA else swA
            s['games_won'] += gwA if isA else gwB
            s['games_lost'] += gwB if isA else gwA
            
            win_cond = (isA and m['winner']==1) or (not isA and m['winner']==2)
            if win_cond: s['wins']+=1
            else: s['losses']+=1

    res = []
    for k, s in stats.items():
        s['win_rate'] = round((s['wins']/s['played']*100), 1) if s['played']>0 else 0
        if lid:
            # Formatear pareja
            pid1, pid2 = k
            p1 = pmap.get(pid1, {'name':'?', 'elo':0})
            p2 = pmap.get(pid2, {'name':'?', 'elo':0})
            s['type'] = 'pair'
            s['p1_name'] = p1['name']; s['p1_elo'] = p1['elo']
            s['p2_name'] = p2['name']; s['p2_elo'] = p2['elo']
            s['elo_sort'] = (p1['elo'] + p2['elo']) / 2
        else:
            p = pmap.get(k, {'name':'?', 'elo':0})
            s['type'] = 'individual'
            s['name'] = p['name']; s['elo'] = p['elo']; s['elo_sort'] = p['elo']
        res.append(s)
        
    res.sort(key=lambda x: (x['wins'], x['win_rate'], x['sets_won'], x['elo_sort']), reverse=True)
    return jsonify(res)

@app.route('/api/leagues/<int:lid>/generate', methods=['POST'])
def generate_league_matches(lid):
    db = get_db()
    cur = db.cursor()

    # 1. Obtener todas las parejas inscritas en la liga
    cur.execute('''
        SELECT pr.id, pr.p1_id, pr.p2_id 
        FROM pairs pr
        JOIN league_pairs lp ON pr.id = lp.pair_id
        WHERE lp.league_id = ?
    ''', (lid,))
    pairs = [dict(r) for r in cur.fetchall()]

    if len(pairs) < 2:
        return jsonify({'error': 'Necesitas al menos 2 parejas para generar partidos'}), 400

    # 2. Obtener partidos YA existentes en esta liga para no duplicar
    # Guardamos sets de IDs de parejas que ya jugaron: { (id_pair_A, id_pair_B), ... }
    cur.execute('SELECT p1, p2, p3, p4 FROM events WHERE league_id = ?', (lid,))
    existing_events = cur.fetchall()
    
    existing_matchups = set()
    for evt in existing_events:
        # Reconstruir quién jugó contra quién
        # Buscamos qué pareja tiene a p1 y p2
        # Nota: Esto asume que las parejas no cambian de integrantes.
        # Para ser robustos, comparamos conjuntos de jugadores.
        teamA = frozenset([evt['p1'], evt['p2']])
        teamB = frozenset([evt['p3'], evt['p4']])
        # Guardamos la combinación sin orden (A vs B es igual que B vs A)
        existing_matchups.add(frozenset([teamA, teamB]))

    # 3. Generar combinaciones (Todos contra todos)
    created_count = 0
    
    # itertools.combinations crea cruces únicos: (A,B), (A,C), (B,C)...
    for pairA, pairB in itertools.combinations(pairs, 2):
        
        # Definir conjuntos de jugadores para comparar con lo existente
        setA = frozenset([pairA['p1_id'], pairA['p2_id']])
        setB = frozenset([pairB['p1_id'], pairB['p2_id']])
        matchup_signature = frozenset([setA, setB])

        # Verificar si hay solapamiento de jugadores (un jugador no puede jugar contra sí mismo en otra pareja)
        # Esto pasa si Imanol está en la Pareja 1 y también en la Pareja 2 (error de datos)
        if not setA.isdisjoint(setB):
            continue 

        # Si el partido ya existe, saltar
        if matchup_signature in existing_matchups:
            continue

        # Crear el evento
        # Título automático
        title = "Jornada de Liga" 
        # Fecha: Hoy por defecto, o podrías implementar lógica de semanas
        import datetime
        today = datetime.date.today().isoformat()

        cur.execute('''
            INSERT INTO events (
                title, start, allDay, league_id, description,
                p1, p2, p3, p4,
                played, elo_diff, s1_a, s1_b, s2_a, s2_b, s3_a, s3_b
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
        ''', (title, today, lid, "Partido generado automáticamente", 
              pairA['p1_id'], pairA['p2_id'], 
              pairB['p1_id'], pairB['p2_id']))
        
        created_count += 1

    db.commit()
    return jsonify({'ok': True, 'count': created_count})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)