document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('event-modal');
  const modalClose = document.getElementById('modal-close');
  const leagueSelect = document.getElementById('main-league-select');
  
  // Inputs Modal
  const evtLeagueSelect = document.getElementById('evt-league');
  const modeIndiv = document.getElementById('mode-individual');
  const modePairs = document.getElementById('mode-pairs');
  const checkPlayed = document.getElementById('is-played-check');
  const resultSection = document.getElementById('result-section');
  const checkWrapper = document.getElementById('check-wrapper');

  let currentEventId = null;
  
  // Variables para Tom Select y Datos
  let tsInstances = {}; // Para jugadores individuales
  let tsPairA, tsPairB; // Para parejas
  let currentLeaguePairs = []; // Cache de parejas para buscar IDs
  
  // Variables para Ordenación
  let rankingData = [];
  let sortConfig = { key: 'elo_sort', dir: 'desc' };

  init();

  function init(){
    loadLeagues();
    loadPlayerSelects(); 
    refresh();

    if (checkPlayed && resultSection) {
        checkPlayed.addEventListener('change', function() {
            resultSection.style.display = checkPlayed.checked ? 'block' : 'none';
        });
    }

    if (evtLeagueSelect) {
        evtLeagueSelect.addEventListener('change', function(e) {
            toggleEventMode(e.target.value);
        });
    }
  }

  function refresh() {
    loadRanking(leagueSelect.value);
    loadMatches('pending', 'pending-list');
    loadMatches('recent', 'agenda-list');
  }

  if(leagueSelect) leagueSelect.addEventListener('change', () => loadRanking(leagueSelect.value));

  // --- 1. LOGICA RANKING Y ORDENACIÓN ---
  
  function loadRanking(lid) {
    const tbody = document.getElementById('league-ranking-body');
    if(!tbody) return;
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#aaa">Cargando...</td></tr>';
    
    let url = '/api/stats'; 
    if(lid) url += `?league_id=${lid}`;

    fetch(url).then(r=>r.json()).then(data => {
      rankingData = data; 
      renderRankingTable(); 
    });
  }

  window.sortTable = function(key) {
      if (sortConfig.key === key) {
          sortConfig.dir = (sortConfig.dir === 'desc') ? 'asc' : 'desc';
      } else {
          sortConfig.key = key;
          sortConfig.dir = 'desc';
      }
      renderRankingTable();
  }

  function renderRankingTable() {
      const tbody = document.getElementById('league-ranking-body');
      const table = document.querySelector('.players-table');
      const thead = table.querySelector('thead tr');
      
      if(!rankingData.length) { 
          tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:15px;color:#aaa">Sin datos</td></tr>'; 
          return; 
      }

      // Ordenar
      rankingData.sort((a, b) => {
          let valA = a[sortConfig.key];
          let valB = b[sortConfig.key];
          if (typeof valA === 'string') return sortConfig.dir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
          return sortConfig.dir === 'asc' ? valA - valB : valB - valA;
      });

      // Cabeceras Dinámicas
      const isPairMode = (rankingData[0].type === 'pair');
      const th = (label, key, tooltip) => `<th class="sortable stat-head" onclick="sortTable('${key}')" title="${tooltip || ''}">${label}</th>`;

      if (isPairMode) {
          thead.innerHTML = `<th>#</th><th class="sortable" onclick="sortTable('p1_name')" style="min-width:200px">Pareja</th>${th('PJ','played')}${th('V','wins')}${th('SG','sets_won')}${th('SP','sets_lost')}${th('JG','games_won')}${th('JP','games_lost')}${th('% V','win_rate')}`;
      } else {
          thead.innerHTML = `<th>#</th><th class="sortable" onclick="sortTable('name')" style="min-width:120px">Jugador</th><th class="sortable" onclick="sortTable('elo')" style="color:#fff">ELO</th>${th('PJ','played')}${th('V','wins')}${th('SG','sets_won')}${th('SP','sets_lost')}${th('JG','games_won')}${th('JP','games_lost')}${th('% V','win_rate')}`;
      }

      // Pintar
      tbody.innerHTML = '';
      rankingData.forEach((p, i) => {
        let medal = (i===0)?'🥇':(i===1)?'🥈':(i===2)?'🥉':(i+1);
        let nameCell = isPairMode 
            ? `<div style="display:flex; flex-direction:column; gap:2px;"><div>${p.p1_name} <span class="elo-badge">${p.p1_elo}</span></div><div style="font-size:0.8rem; color:#aaa">+</div><div>${p.p2_name} <span class="elo-badge">${p.p2_elo}</span></div></div>`
            : p.name;

        let rowHtml = `<tr><td style="font-weight:bold; vertical-align:middle">${medal}</td><td style="font-weight:600; vertical-align:middle">${nameCell}</td>`;
        if (!isPairMode) rowHtml += `<td style="vertical-align:middle"><span class="elo-badge">${p.elo}</span></td>`;
        
        rowHtml += `<td style="vertical-align:middle">${p.played}</td><td style="color:#fff; font-weight:bold; vertical-align:middle">${p.wins}</td><td style="color:var(--ball); vertical-align:middle">${p.sets_won}</td><td style="opacity:0.6; vertical-align:middle">${p.sets_lost}</td><td style="color:var(--ball); vertical-align:middle">${p.games_won}</td><td style="opacity:0.6; vertical-align:middle">${p.games_lost}</td><td style="vertical-align:middle">${p.win_rate}%</td></tr>`;
        tbody.innerHTML += rowHtml;
      });
  }

  // --- 2. GESTIÓN DEL MODAL Y MODOS ---

  function toggleEventMode(lid, callback = null) {
      if(!lid) {
          // AMISTOSO
          modeIndiv.style.display = 'block';
          modePairs.style.display = 'none';
          loadPlayerSelects("", callback); 
      } else {
          // LIGA
          modeIndiv.style.display = 'none';
          modePairs.style.display = 'block';
          loadLeaguePairs(lid, callback);
      }
  }

  function loadLeaguePairs(lid, callback = null) {
      fetch(`/api/leagues/${lid}/pairs`).then(r=>r.json()).then(data => {
          currentLeaguePairs = data;
          const opts = data.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
          const html = '<option value="">Seleccionar Pareja...</option>' + opts;
          
          document.getElementById('pair-a').innerHTML = html;
          document.getElementById('pair-b').innerHTML = html;

          if(window.TomSelect) {
              if(tsPairA) tsPairA.destroy();
              if(tsPairB) tsPairB.destroy();
              tsPairA = new TomSelect('#pair-a', {create:false});
              tsPairB = new TomSelect('#pair-b', {create:false});
          }
          if(callback) callback();
      });
  }

  function loadPlayerSelects(lid = "", callback = null) {
    let url = '/api/players';
    fetch(url).then(r=>r.json()).then(ps => {
      ['p1','p2','p3','p4'].forEach(id => {
        const el = document.getElementById(id);
        if(el) {
            el.innerHTML='<option value="">Buscar jugador...</option>';
            ps.forEach(p => el.innerHTML+=`<option value="${p.id}">${p.first_name} ${p.last_name||''}</option>`);
            if(window.TomSelect) {
               if(tsInstances[id]) tsInstances[id].destroy(); 
               tsInstances[id] = new TomSelect(`#${id}`, { create: false, sortField: { field: "text", direction: "asc" }, maxOptions: 50 });
            }
        }
      });
      if(callback) callback();
    });
  }

  // --- 3. ABRIR MODAL (CREAR / EDITAR) ---
  window.openModal = function(m = null) {
    const form = document.getElementById('event-form');
    const btnSave = document.getElementById('btn-save');
    const btnDel = document.getElementById('btn-delete');
    document.getElementById('evt-error').style.display='none';

    if(m) {
      // EDITAR
      currentEventId = m.id;
      document.getElementById('modal-title').innerText = "Editar Partido";
      document.getElementById('evt-start').value = m.start;
      document.getElementById('evt-league').value = m.league_id || "";
      document.getElementById('evt-desc').value = m.description || "";
      
      toggleEventMode(m.league_id || "", function() {
          if (m.league_id) {
              const pairA = findPairFromPlayers(m.p1, m.p2);
              const pairB = findPairFromPlayers(m.p3, m.p4);
              if(pairA && tsPairA) tsPairA.setValue(pairA.id);
              if(pairB && tsPairB) tsPairB.setValue(pairB.id);
          } else {
              if(tsInstances['p1']) tsInstances['p1'].setValue(m.p1);
              if(tsInstances['p2']) tsInstances['p2'].setValue(m.p2);
              if(tsInstances['p3']) tsInstances['p3'].setValue(m.p3);
              if(tsInstances['p4']) tsInstances['p4'].setValue(m.p4);
          }
      });
      
      if (m.played) {
          checkWrapper.style.display = 'none'; 
          resultSection.style.display = 'block';
          checkPlayed.checked = true;
          fillScore(m);
          btnSave.innerText = "Actualizar Datos";
      } else {
          checkWrapper.style.display = 'none'; 
          resultSection.style.display = 'block'; 
          checkPlayed.checked = true; 
          clearScore();
          btnSave.innerText = "Guardar Resultado (Jugar)";
      }
      btnDel.style.display = 'inline-block';

    } else {
      // CREAR
      currentEventId = null;
      form.reset();
      
      document.getElementById('evt-league').value = "";
      toggleEventMode(""); 
      
      document.getElementById('modal-title').innerText = "Nuevo Partido";
      document.getElementById('evt-start').value = new Date().toISOString().split('T')[0];
      checkWrapper.style.display = 'flex';
      checkPlayed.checked = false;
      resultSection.style.display = 'none';
      btnSave.innerText = "Crear";
      btnDel.style.display = 'none';
    }
    modal.style.display = 'block';
  }

  modalClose.onclick = () => modal.style.display = 'none';
  window.onclick = (e) => { if(e.target==modal) modal.style.display='none'; };

  // --- 4. SUBMIT ---
  document.getElementById('event-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const isPlayed = checkPlayed ? checkPlayed.checked : false;
    const lid = document.getElementById('evt-league').value;
    let p1, p2, p3, p4;

    if (lid && modePairs.style.display !== 'none') {
        const idA = parseInt(document.getElementById('pair-a').value);
        const idB = parseInt(document.getElementById('pair-b').value);
        const pairA = currentLeaguePairs.find(p => p.id === idA);
        const pairB = currentLeaguePairs.find(p => p.id === idB);
        
        if(!pairA || !pairB) { alert('Selecciona parejas válidas'); return; }
        p1 = pairA.p1_id; p2 = pairA.p2_id; p3 = pairB.p1_id; p4 = pairB.p2_id;
    } else {
        p1=document.getElementById('p1').value; p2=document.getElementById('p2').value;
        p3=document.getElementById('p3').value; p4=document.getElementById('p4').value;
    }

    const payload = {
      start: document.getElementById('evt-start').value,
      league_id: lid,
      description: document.getElementById('evt-desc').value,
      p1, p2, p3, p4,
      played: isPlayed
    };

    if (isPlayed) {
        payload.winner = document.getElementById('evt-winner').value;
        payload.s1_a = document.getElementById('s1_a').value; payload.s1_b = document.getElementById('s1_b').value;
        payload.s2_a = document.getElementById('s2_a').value; payload.s2_b = document.getElementById('s2_b').value;
        payload.s3_a = document.getElementById('s3_a').value; payload.s3_b = document.getElementById('s3_b').value;
    }

    let url = '/api/events';
    let method = 'POST';
    if (currentEventId) {
        if (isPlayed) { url = `/api/events/${currentEventId}/result`; method = 'POST'; } 
        else { url = `/api/events/${currentEventId}`; method = 'PUT'; }
    }
    
    if (currentEventId && isPlayed) {
         fetch(`/api/events/${currentEventId}`, {method: 'PUT', body: JSON.stringify(payload), headers:{'Content-Type':'application/json'}})
         .then(() => fetch(`/api/events/${currentEventId}/result`, {method: 'POST', body: JSON.stringify(payload), headers:{'Content-Type':'application/json'}}))
         .then(r => r.json()).then(d => { if(d.error) throw new Error(d.error); refresh(); modal.style.display='none'; })
         .catch(err => alert(err.message));
    } else {
        fetch(url, {method, body: JSON.stringify(payload), headers:{'Content-Type':'application/json'}})
        .then(r => r.json()).then(d => { if(d.error) throw new Error(d.error); refresh(); modal.style.display='none'; })
        .catch(err => alert(err.message));
    }
  });

  document.getElementById('btn-delete').addEventListener('click', () => {
    if(confirm('¿Borrar?')) fetch(`/api/events/${currentEventId}`, {method:'DELETE'}).then(() => { refresh(); modal.style.display='none'; });
  });

  // Utils
  function findPairFromPlayers(pid1, pid2) {
      if(!currentLeaguePairs) return null;
      return currentLeaguePairs.find(p => (p.p1_id == pid1 && p.p2_id == pid2) || (p.p1_id == pid2 && p.p2_id == pid1));
  }
  function fillScore(m) {
      document.getElementById('s1_a').value = m.s1_a||''; document.getElementById('s1_b').value = m.s1_b||'';
      document.getElementById('s2_a').value = m.s2_a||''; document.getElementById('s2_b').value = m.s2_b||'';
      document.getElementById('s3_a').value = m.s3_a||''; document.getElementById('s3_b').value = m.s3_b||'';
      document.getElementById('evt-winner').value = m.winner||'1';
  }
  function clearScore() {
      document.getElementById('s1_a').value=''; document.getElementById('s1_b').value='';
      document.getElementById('s2_a').value=''; document.getElementById('s2_b').value='';
      document.getElementById('s3_a').value=''; document.getElementById('s3_b').value='';
  }
  function loadMatches(type, elemId) {
    const container = document.getElementById(elemId);
    if(!container) return;
    fetch(`/api/matches/${type}`).then(r=>r.json()).then(matches => {
      container.innerHTML = '';
      if(!matches.length) { container.innerHTML = `<div style="text-align:center;color:#666;font-style:italic;padding:10px;font-size:0.9rem">No hay ${type=='pending'?'pendientes':'recientes'}</div>`; return; }
      matches.forEach(m => {
        const isPending = (type === 'pending');
        const p1c = (!isPending && m.winner==1) ? 'winner-text' : 'loser-text';
        const p2c = (!isPending && m.winner==2) ? 'winner-text' : 'loser-text';
        let eloA = '', eloB = '';
        if(!isPending && m.elo_diff) {
            const diff = m.elo_diff;
            if(m.winner == 1) { eloA = `<span class="elo-plus">(+${diff})</span>`; eloB = `<span class="elo-minus">(-${diff})</span>`; } 
            else { eloA = `<span class="elo-minus">(-${diff})</span>`; eloB = `<span class="elo-plus">(+${diff})</span>`; }
        }
        const div = document.createElement('div');
        div.className = `match-card ${isPending ? 'pending-card' : ''}`;
        if(isPending) div.onclick = () => openModal(m);
        let content = `<div class="match-date"><span>${m.start}</span> <span class="vs-badge" style="font-size:0.7rem">${m.league_name||'Amistoso'}</span></div><div class="team-row ${p1c}"><span>${m.p1_name} / ${m.p2_name} ${eloA}</span></div><div class="team-row ${p2c}"><span>${m.p3_name} / ${m.p4_name} ${eloB}</span></div>`;
        if(isPending) content += `<div class="pending-tag">JUGAR</div><div style="text-align:center;font-size:0.8rem;color:#666">VS</div>`;
        else content += `<div class="match-score">${m.score_str || '-'}</div>`;
        div.innerHTML = content;
        container.appendChild(div);
      });
    });
  }
  
  // --- CARGA DE LIGAS CON DESCRIPCIÓN ---
  function loadLeagues() {
    fetch('/api/leagues').then(r=>r.json()).then(ls => {
      const s1 = document.getElementById('main-league-select');
      const s2 = document.getElementById('evt-league');
      if(s1 && s2) {
          s1.innerHTML='<option value="">-- Clasificación Global --</option>';
          s2.innerHTML='<option value="">-- Amistoso (Individual) --</option>';
          ls.forEach(l => { 
              const label = l.description ? `${l.name} (${l.description})` : l.name;
              const opt = `<option value="${l.id}">${label}</option>`;
              s1.innerHTML += opt; 
              s2.innerHTML += opt; 
          });
      }
    });
  }
});