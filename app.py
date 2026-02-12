import os
import sqlite3
import random
import itertools
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "padel_manager.db")

# --- DATABASE ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, elo INTEGER DEFAULT 100, matches INTEGER DEFAULT 0, wins INTEGER DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS venues (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS leagues (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT)')
        
        # NUEVA TABLA: Relación Muchos a Muchos (Jugadores <-> Ligas)
        db.execute('''CREATE TABLE IF NOT EXISTS league_players (
            league_id INTEGER,
            player_id INTEGER,
            PRIMARY KEY (league_id, player_id),
            FOREIGN KEY(league_id) REFERENCES leagues(id),
            FOREIGN KEY(player_id) REFERENCES players(id)
        )''')

        db.execute('''CREATE TABLE IF NOT EXISTS league_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER, date TEXT, venue_id INTEGER,
            p1_id INTEGER, p2_id INTEGER, p3_id INTEGER, p4_id INTEGER,
            s1_a INTEGER, s1_b INTEGER, s2_a INTEGER, s2_b INTEGER, s3_a INTEGER, s3_b INTEGER,
            winner_team INTEGER, elo_exchanged INTEGER, comment TEXT
        )''')
        
        db.execute('CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, date TEXT, match_duration INTEGER, total_duration INTEGER, mode TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER, round_num INTEGER, start_time TEXT, court_num INTEGER, p1_id INTEGER, p2_id INTEGER, p3_id INTEGER, p4_id INTEGER, score_a INTEGER DEFAULT 0, score_b INTEGER DEFAULT 0, played INTEGER DEFAULT 0)')

        # Migraciones
        try: db.execute("ALTER TABLE league_matches ADD COLUMN comment TEXT DEFAULT ''"); db.commit()
        except: pass
        try: db.execute("ALTER TABLE league_matches ADD COLUMN league_id INTEGER"); db.commit()
        except: pass
        try: db.execute("ALTER TABLE tournaments ADD COLUMN mode TEXT DEFAULT 'individual'"); db.commit()
        except: pass
        
        db.commit()

# --- ELO LOGIC ---
def calculate_elo_points(my_avg, opp_avg, won):
    if won: return 2 if opp_avg > my_avg else 1
    else: return 2 if opp_avg < my_avg else 1

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')
@app.route('/matches')
def matches_page(): return render_template('matches.html')
@app.route('/players')
def players_page(): return render_template('players.html')
@app.route('/leagues')
def leagues_page(): return render_template('leagues.html')

# --- API LIGAS ---
@app.route('/api/leagues', methods=['GET', 'POST', 'DELETE'])
def handle_leagues():
    db = get_db()
    if request.method == 'POST':
        db.execute('INSERT INTO leagues (name, created_at) VALUES (?, date("now"))', (request.json['name'],))
        db.commit(); return jsonify({'ok': True})
    if request.method == 'DELETE':
        lid = request.args.get('id')
        db.execute('DELETE FROM league_players WHERE league_id=?', (lid,)) # Borrar relaciones
        db.execute('DELETE FROM league_matches WHERE league_id=?', (lid,))
        db.execute('DELETE FROM leagues WHERE id=?', (lid,))
        db.commit(); return jsonify({'ok': True})
    return jsonify([dict(r) for r in db.execute('SELECT * FROM leagues ORDER BY id DESC').fetchall()])

# --- NUEVO: API GESTIÓN JUGADORES EN LIGAS ---
@app.route('/api/leagues/<int:lid>/players', methods=['GET', 'POST', 'DELETE'])
def handle_league_players(lid):
    db = get_db()
    
    # Añadir jugador a liga
    if request.method == 'POST':
        pid = request.json['player_id']
        try:
            db.execute('INSERT INTO league_players (league_id, player_id) VALUES (?,?)', (lid, pid))
            db.commit()
        except sqlite3.IntegrityError:
            pass # Ya existe
        return jsonify({'ok': True})

    # Quitar jugador de liga
    if request.method == 'DELETE':
        pid = request.args.get('player_id')
        db.execute('DELETE FROM league_players WHERE league_id=? AND player_id=?', (lid, pid))
        db.commit()
        return jsonify({'ok': True})

    # GET: Devolver estado de todos los jugadores respecto a esta liga (In / Out)
    all_players = db.execute('SELECT * FROM players ORDER BY name').fetchall()
    league_p_ids = [r['player_id'] for r in db.execute('SELECT player_id FROM league_players WHERE league_id=?', (lid,)).fetchall()]
    
    result = []
    for p in all_players:
        p_dict = dict(p)
        p_dict['in_league'] = p['id'] in league_p_ids
        result.append(p_dict)
    
    return jsonify(result)

# --- API JUGADORES (MODIFICADA) ---
@app.route('/api/players', methods=['GET', 'POST', 'PUT', 'DELETE'])
def handle_players():
    db = get_db()
    
    if request.method == 'POST':
        db.execute('INSERT INTO players (name) VALUES (?)', (request.json['name'],)); db.commit(); return jsonify({'ok': True})
    elif request.method == 'PUT':
        d = request.json; db.execute('UPDATE players SET name=?, elo=? WHERE id=?', (d['name'], int(d['elo']), d['id'])); db.commit(); return jsonify({'ok': True})
    elif request.method == 'DELETE':
        db.execute('DELETE FROM players WHERE id=?', (request.args.get('id'),)); db.commit(); return jsonify({'ok': True})

    # --- LECTURA RANKING ---
    league_id = request.args.get('league_id')
    
    # 1. Seleccionar jugadores base
    # Si hay liga seleccionada, SOLO traemos los asociados a esa liga
    if league_id and league_id != 'null':
        cur = db.execute('''
            SELECT p.* FROM players p
            JOIN league_players lp ON p.id = lp.player_id
            WHERE lp.league_id = ?
        ''', (league_id,))
    else:
        # Si no hay liga (modo global o vista jugadores), traemos todos
        cur = db.execute('SELECT * FROM players')
        
    players = {row['id']: dict(row) for row in cur.fetchall()}
    
    # Inicializar stats a 0 para el cálculo dinámico
    for pid in players:
        players[pid].update({'elo':100, 'matches':0, 'wins':0, 'sets_won':0, 'sets_lost':0, 'venues':{}, 'match_history':[]})

    # 2. Obtener partidos (Filtrados por liga)
    query = 'SELECT m.*, v.name as venue_name FROM league_matches m LEFT JOIN venues v ON m.venue_id = v.id'
    params = []
    if league_id and league_id != 'null':
        query += ' WHERE m.league_id = ?'; params.append(league_id)
    query += ' ORDER BY m.id ASC'
    
    matches = db.execute(query, params).fetchall()

    # 3. Recalcular ELO
    for m in matches:
        p_ids = [m['p1_id'], m['p2_id'], m['p3_id'], m['p4_id']]
        
        # IMPORTANTE: Si un jugador participó en un partido pero ya no está en la liga (fue borrado de la lista),
        # aún necesitamos sus datos para calcular el ELO de los demás correctamente en ese momento histórico.
        # Por eso, si falta alguno en 'players', lo cargamos temporalmente solo para cálculo.
        missing = [pid for pid in p_ids if pid not in players]
        if missing:
            # Traemos los datos básicos del jugador faltante para poder hacer la media
            placeholders = ','.join('?' * len(missing))
            temps = db.execute(f'SELECT * FROM players WHERE id IN ({placeholders})', missing).fetchall()
            for t in temps:
                players[t['id']] = dict(t)
                players[t['id']].update({'elo':100, 'matches':0, 'wins':0, 'sets_won':0, 'sets_lost':0, 'venues':{}, 'match_history':[], 'is_ghost': True}) 
                # 'is_ghost' marca que no debe salir en el ranking final

        avg_a = (players[m['p1_id']]['elo'] + players[m['p2_id']]['elo']) / 2
        avg_b = (players[m['p3_id']]['elo'] + players[m['p4_id']]['elo']) / 2
        
        def s_int(v): return int(v or 0)
        s1a, s1b, s2a, s2b, s3a, s3b = s_int(m['s1_a']), s_int(m['s1_b']), s_int(m['s2_a']), s_int(m['s2_b']), s_int(m['s3_a']), s_int(m['s3_b'])
        sw_a = (1 if s1a>s1b else 0) + (1 if s2a>s2b else 0) + (1 if s3a>s3b else 0)
        sw_b = (1 if s1b>s1a else 0) + (1 if s2b>s2a else 0) + (1 if s3b>s3a else 0)
        winner = 1 if sw_a > sw_b else 2
        
        pts = calculate_elo_points(avg_a if winner==1 else avg_b, avg_b if winner==1 else avg_a, True)

        for pid in p_ids:
            is_team_a = pid in [m['p1_id'], m['p2_id']]
            won = (is_team_a and winner==1) or (not is_team_a and winner==2)
            p_change = pts if won else -pts
            
            players[pid]['elo'] += p_change
            players[pid]['matches'] += 1
            if won: players[pid]['wins'] += 1
            players[pid]['sets_won'] += sw_a if is_team_a else sw_b
            players[pid]['sets_lost'] += sw_b if is_team_a else sw_a
            
            players[pid]['match_history'].append({
                'date': m['date'], 'venue': m['venue_name'] or 'Pista', 'result': f"{s1a}-{s1b}, {s2a}-{s2b}" + (f", {s3a}-{s3b}" if (s3a+s3b)>0 else ""),
                'opponent': f"{players[m['p3_id']]['name']} & {players[m['p4_id']]['name']}" if is_team_a else f"{players[m['p1_id']]['name']} & {players[m['p2_id']]['name']}",
                'points': p_change, 'won': won, 'comment': m['comment']
            })
            
            v_name = m['venue_name'] or "Desconocida"
            if v_name not in players[pid]['venues']: players[pid]['venues'][v_name] = {'w':0, 'l':0}
            if won: players[pid]['venues'][v_name]['w'] += 1
            else: players[pid]['venues'][v_name]['l'] += 1

    # 4. Limpieza final (Quitar ghosts y calcular medallas)
    final_list = []
    for pid, p in players.items():
        if p.get('is_ghost'): continue # No lo añadimos al ranking final si no pertenece a la liga
        
        talisman, cursed = "-", "-"
        if p['venues']:
            sorted_v = sorted(p['venues'].items(), key=lambda x: (x[1]['w']/(x[1]['w']+x[1]['l']), x[1]['w']), reverse=True)
            if sorted_v[0][1]['w'] > 0: talisman = sorted_v[0][0]
            if sorted_v[-1][1]['l'] > 0: cursed = sorted_v[-1][0]
            if talisman == cursed: cursed = "-"
        p['talisman'], p['cursed'] = talisman, cursed
        del p['venues']
        final_list.append(p)

    return jsonify(sorted(final_list, key=lambda x: (x['elo'], x['wins']), reverse=True))

@app.route('/api/league/matches', methods=['GET', 'POST', 'PUT', 'DELETE'])
def handle_league_matches():
    db = get_db()
    if request.method == 'POST':
        d = request.json
        db.execute('''INSERT INTO league_matches (league_id, date, venue_id, p1_id, p2_id, p3_id, p4_id, s1_a, s1_b, s2_a, s2_b, s3_a, s3_b, winner_team, comment)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
                   (d.get('league_id'), d['date'], d['venue'], d['p1'], d['p2'], d['p3'], d['p4'], d['s1a'], d['s1b'], d['s2a'], d['s2b'], d['s3a'], d['s3b'], 0, d.get('comment','')))
        db.commit(); return jsonify({'ok': True})
    
    if request.method == 'PUT':
        d = request.json
        db.execute('''UPDATE league_matches SET date=?, venue_id=?, p1_id=?, p2_id=?, p3_id=?, p4_id=?, s1_a=?, s1_b=?, s2_a=?, s2_b=?, s3_a=?, s3_b=?, comment=? WHERE id=?''',
                   (d['date'], d['venue'], d['p1'], d['p2'], d['p3'], d['p4'], d['s1a'], d['s1b'], d['s2a'], d['s2b'], d['s3a'], d['s3b'], d.get('comment',''), d['id']))
        db.commit(); return jsonify({'ok': True})

    if request.method == 'DELETE':
        db.execute('DELETE FROM league_matches WHERE id=?', (request.args.get('id'),)); db.commit(); return jsonify({'ok': True})

    if request.method == 'GET':
        lid = request.args.get('league_id')
        query = 'SELECT m.*, p1.name p1n, p2.name p2n, p3.name p3n, p4.name p4n, v.name venue_name, l.name league_name FROM league_matches m LEFT JOIN players p1 ON m.p1_id=p1.id LEFT JOIN players p2 ON m.p2_id=p2.id LEFT JOIN players p3 ON m.p3_id=p3.id LEFT JOIN players p4 ON m.p4_id=p4.id LEFT JOIN venues v ON m.venue_id=v.id LEFT JOIN leagues l ON m.league_id=l.id'
        if lid: return jsonify([dict(r) for r in db.execute(query + ' WHERE m.league_id=?', (lid,)).fetchall()])
        return jsonify([dict(r) for r in db.execute(query + ' ORDER BY m.id DESC').fetchall()])

@app.route('/api/venues', methods=['GET', 'POST'])
def handle_venues():
    db = get_db()
    if request.method == 'POST': db.execute('INSERT INTO venues (name) VALUES (?)', (request.json['name'],)); db.commit(); return jsonify({'ok':True})
    return jsonify([dict(r) for r in db.execute('SELECT * FROM venues ORDER BY name').fetchall()])

# --- API AMERICANAS ---
@app.route('/api/tournaments', methods=['GET'])
def get_tournaments():
    return jsonify([dict(r) for r in get_db().execute('SELECT * FROM tournaments ORDER BY id DESC').fetchall()])

@app.route('/api/tournaments/<int:tid>', methods=['GET', 'DELETE'])
def handle_tournament(tid):
    db = get_db()
    if request.method == 'DELETE':
        db.execute('DELETE FROM matches WHERE tournament_id=?', (tid,)); db.execute('DELETE FROM tournaments WHERE id=?', (tid,)); db.commit(); return jsonify({'ok': True})
    
    t = db.execute('SELECT * FROM tournaments WHERE id=?', (tid,)).fetchone()
    matches = db.execute('SELECT m.*, p1.name p1n, p2.name p2n, p3.name p3n, p4.name p4n FROM matches m LEFT JOIN players p1 ON m.p1_id=p1.id LEFT JOIN players p2 ON m.p2_id=p2.id LEFT JOIN players p3 ON m.p3_id=p3.id LEFT JOIN players p4 ON m.p4_id=p4.id WHERE tournament_id=? ORDER BY round_num, court_num', (tid,)).fetchall()
    
    stats = {}
    for m in matches:
        if m['played']:
            for i, team in enumerate([[m['p1_id'], m['p2_id']], [m['p3_id'], m['p4_id']]]):
                sc, opp_sc = (m['score_a'], m['score_b']) if i==0 else (m['score_b'], m['score_a'])
                for pid in team:
                    if pid not in stats: stats[pid] = {'name': m[f'p{team.index(pid)+(1 if i==0 else 3)}n'], 'wins':0, 'diff':0, 'points':0}
                    stats[pid]['points']+=sc; stats[pid]['diff']+=(sc-opp_sc); 
                    if sc>opp_sc: stats[pid]['wins']+=1
    
    return jsonify({'tournament': dict(t), 'matches': [dict(m) for m in matches], 'ranking': sorted(stats.values(), key=lambda x: (x['wins'], x['diff']), reverse=True)})


@app.route('/api/generate', methods=['POST'])
def generate_americana():
    d = request.json
    db = get_db()
    
    tid = d.get('id')
    
    # 1. Configuración del Torneo
    if tid:
        # Regenerar (Sortear de nuevo)
        t_current = db.execute('SELECT * FROM tournaments WHERE id=?', (tid,)).fetchone()
        m_dur = int(d.get('match_duration', t_current['match_duration']))
        t_dur = int(d.get('total_duration', t_current['total_duration']))
        mode = t_current['mode']
        db.execute('DELETE FROM matches WHERE tournament_id=?', (tid,))
    else:
        # Nuevo Torneo
        m_dur = int(d.get('match_duration', 20))
        t_dur = int(d.get('total_duration', 120))
        mode = d.get('mode', 'individual')
        cur = db.execute('''INSERT INTO tournaments (name, date, match_duration, total_duration, mode) 
                            VALUES (?, date("now"), ?, ?, ?)''',
                         (d.get('name', 'Americana'), m_dur, t_dur, mode))
        tid = cur.lastrowid
    
    num_rounds = t_dur // m_dur
    if num_rounds < 1: num_rounds = 1
    
    # 2. ALGORITMO INTELIGENTE DE CRUCES
    if mode == 'individual':
        players = d.get('players', [])
        all_ids = players[:]
        
        # Historiales para evitar repeticiones
        # played_with: Diccionario { id_jugador: {ids_compañeros_previos} }
        played_with = {pid: set() for pid in all_ids}
        # played_against: Diccionario { id_jugador: {ids_rivales_previos} }
        played_against = {pid: set() for pid in all_ids}

        for r in range(1, num_rounds + 1):
            best_round_matches = []
            min_penalty = float('inf')
            
            # Intentamos X veces encontrar la mejor combinación para esta ronda
            # Cuantos más intentos, mejor optimización, pero más lento (1000 es rápido para <20 jugadores)
            attempts = 1000 
            
            for _ in range(attempts):
                current_penalty = 0
                current_matches = []
                temp_ids = all_ids[:]
                random.shuffle(temp_ids) # Mezcla aleatoria inicial
                
                # Simulamos los partidos de esta mezcla
                valid_attempt = True
                match_groups = []
                
                for i in range(0, len(temp_ids), 4):
                    if i+3 >= len(temp_ids): break # Necesitamos 4 jugadores
                    
                    # Definimos equipos: A (0,1) vs B (2,3)
                    p1, p2, p3, p4 = temp_ids[i], temp_ids[i+1], temp_ids[i+2], temp_ids[i+3]
                    
                    # --- CÁLCULO DE PENALIZACIÓN ---
                    
                    # 1. PRIORIDAD MÁXIMA: Evitar repetir compañero (+100 de castigo)
                    if p2 in played_with[p1]: current_penalty += 100
                    if p4 in played_with[p3]: current_penalty += 100
                    
                    # 2. PRIORIDAD MEDIA: Evitar repetir rivales (+1 de castigo)
                    # Equipo A vs Equipo B
                    # Rivales de p1: p3, p4
                    if p3 in played_against[p1]: current_penalty += 1
                    if p4 in played_against[p1]: current_penalty += 1
                    # Rivales de p2: p3, p4
                    if p3 in played_against[p2]: current_penalty += 1
                    if p4 in played_against[p2]: current_penalty += 1
                    
                    match_groups.append([p1, p2, p3, p4])

                # Si esta combinación es mejor que la que teníamos, la guardamos
                if current_penalty < min_penalty:
                    min_penalty = current_penalty
                    best_round_matches = match_groups
                
                # Si encontramos una combinación perfecta (penalización 0), paramos de buscar
                if min_penalty == 0:
                    break
            
            # 3. Guardar la mejor ronda encontrada en la BD y actualizar historiales
            for idx, m in enumerate(best_round_matches):
                p1, p2, p3, p4 = m
                court = idx + 1
                
                # Guardar partido
                db.execute('''INSERT INTO matches (tournament_id, round_num, court_num, p1_id, p2_id, p3_id, p4_id) 
                              VALUES (?,?,?,?,?,?,?)''', 
                           (tid, r, court, p1, p2, p3, p4))
                
                # Actualizar historiales (memoria del algoritmo)
                # Compañeros
                played_with[p1].add(p2); played_with[p2].add(p1)
                played_with[p3].add(p4); played_with[p4].add(p3)
                
                # Rivales
                for pa in [p1, p2]:
                    for pb in [p3, p4]:
                        played_against[pa].add(pb); played_against[pb].add(pa)

    else:
        # Modo Parejas Fijas (Lógica similar pero solo controlando rivales)
        pairs = d.get('pairs') 
        played_against_pairs = {i: set() for i in range(len(pairs))} # Usamos índice de pareja
        
        for r in range(1, num_rounds + 1):
            best_round_matches = []
            min_penalty = float('inf')
            
            for _ in range(500):
                current_penalty = 0
                temp_pairs_idx = list(range(len(pairs)))
                random.shuffle(temp_pairs_idx)
                current_matches = []
                
                for i in range(0, len(temp_pairs_idx), 2):
                    if i+1 >= len(temp_pairs_idx): break
                    
                    idxA = temp_pairs_idx[i]
                    idxB = temp_pairs_idx[i+1]
                    
                    # Penalización por repetir enfrentamiento
                    if idxB in played_against_pairs[idxA]: current_penalty += 50
                    
                    current_matches.append([idxA, idxB])
                
                if current_penalty < min_penalty:
                    min_penalty = current_penalty
                    best_round_matches = current_matches
                if min_penalty == 0: break
            
            for idx, m in enumerate(best_round_matches):
                pairA_idx, pairB_idx = m
                pA = pairs[pairA_idx]
                pB = pairs[pairB_idx]
                court = idx + 1
                
                db.execute('''INSERT INTO matches (tournament_id, round_num, court_num, p1_id, p2_id, p3_id, p4_id) 
                              VALUES (?,?,?,?,?,?,?)''',
                           (tid, r, court, pA[0], pA[1], pB[0], pB[1]))
                
                # Actualizar historial
                played_against_pairs[pairA_idx].add(pairB_idx)
                played_against_pairs[pairB_idx].add(pairA_idx)

    db.commit()
    return jsonify({'ok': True, 'id': tid})

@app.route('/api/matches/<int:mid>/score', methods=['POST'])
def save_score(mid):
    get_db().execute('UPDATE matches SET score_a=?, score_b=?, played=1 WHERE id=?', (request.json['score_a'], request.json['score_b'], mid)); get_db().commit(); return jsonify({'ok': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)
