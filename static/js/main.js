document.addEventListener('DOMContentLoaded', function() {
  const calendarEl = document.getElementById('calendar')
  const modal = document.getElementById('event-modal')
  const modalClose = document.getElementById('modal-close')
  const deleteBtn = document.getElementById('delete-btn')
  const resultSection = document.getElementById('result-section')
  const saveResultBtn = document.getElementById('save-result-btn')

  let playersCache = []
  let currentEventId = null

  function fetchPlayers() {
    return fetch('/api/players')
      .then(r => r.json())
      .then(data => { playersCache = data; return data })
  }

  function populatePlayerSelects() {
    try {
      playersCache = Array.isArray(playersCache) ? playersCache : []
      ['p1','p2','p3','p4'].forEach(id => {
        const sel = document.getElementById(id)
        if (!sel) return
        sel.innerHTML = '<option value="">-- --</option>';
        playersCache.forEach(p => {
          const opt = document.createElement('option')
          opt.value = p.id
          opt.textContent = `${p.first_name} ${p.last_name || ''}`
          sel.appendChild(opt)
        })
      })
    } catch (err) {
      console.error('[PADEL] populatePlayerSelects error', err)
    }
  }

  function openModal(eventData, dateStr) {
    // eventData may be null for create
    currentEventId = eventData ? eventData.id : null
    document.getElementById('evt-title').value = eventData ? eventData.title : ''
    document.getElementById('evt-start').value = eventData ? eventData.start.split('T')[0] : (dateStr || '')
    ['p1','p2','p3','p4'].forEach(k => {
      const el = document.getElementById(k)
      if (!el) return
      el.value = eventData && (eventData[k] !== undefined && eventData[k] !== null) ? eventData[k] : ''
    })
    deleteBtn.style.display = eventData ? 'inline-block' : 'none'
    // Mostrar la sección de resultado solo al editar un evento existente
    if (eventData && eventData.id) {
      resultSection.style.display = 'block'
      document.getElementById('evt-score').value = eventData.score || ''
      document.getElementById('evt-winner').value = eventData.winner || '1'
    } else {
      resultSection.style.display = 'none'
    }
    // limpiar errores
    const err = document.getElementById('evt-error')
    if (err) { err.style.display = 'none'; err.textContent = '' }
    modal.style.display = 'block'
  }

  function closeModal() {
    modal.style.display = 'none'
    currentEventId = null
    document.getElementById('evt-score').value = ''
  }

  modalClose.addEventListener('click', closeModal)

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    selectable: true,
    editable: false,
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,timeGridDay'
    },
    dateClick: function(info) {
      openModal(null, info.dateStr)
    },
    eventClick: function(info) {
      // abrir modal con datos del evento
      const e = info.event
      const ev = Object.assign({
        id: e.id,
        title: e.title,
        start: e.startStr,
        end: e.endStr,
      }, e.extendedProps || {})
      openModal(ev)
    },
    events: function(fetchInfo, successCallback, failureCallback) {
      fetch('/api/events')
        .then(r => r.json())
        .then(data => {
          // enriquecer títulos con nombres de jugadores si están en cache
          const mapped = data.map(ev => {
            try {
              const p1 = (playersCache || []).find(p=>p.id==ev.p1)
              const p2 = (playersCache || []).find(p=>p.id==ev.p2)
              const p3 = (playersCache || []).find(p=>p.id==ev.p3)
              const p4 = (playersCache || []).find(p=>p.id==ev.p4)
              if (p1 && p2 && p3 && p4) {
                const short = name => `${name.first_name}${name.last_name? ' ' + name.last_name.split(' ')[0].charAt(0)+'.':''}`
                ev.title = `${short(p1)} / ${short(p2)} vs ${short(p3)} / ${short(p4)}`
                ev.extendedProps = Object.assign({}, ev)
              }
            } catch (e) { /* ignore */ }
            return ev
          })
          successCallback(mapped)
        })
        .catch(err => failureCallback(err))
    }
  })

  // submit form
  document.getElementById('event-form').addEventListener('submit', function(e) {
    e.preventDefault()
    const title = document.getElementById('evt-title').value
    const start = document.getElementById('evt-start').value
    const p1 = parseInt(document.getElementById('p1').value) || null
    const p2 = parseInt(document.getElementById('p2').value) || null
    const p3 = parseInt(document.getElementById('p3').value) || null
    const p4 = parseInt(document.getElementById('p4').value) || null

    // Validación front-end: todos los jugadores seleccionados
    const players = [p1, p2, p3, p4]
    const errEl = document.getElementById('evt-error')
    function showError(msg){ if(errEl){ errEl.textContent = msg; errEl.style.display = 'block' } }
    function clearError(){ if(errEl){ errEl.textContent = ''; errEl.style.display = 'none' } }

    if (players.some(v => !v)) {
      showError('Seleccione los 4 jugadores (dos por pareja) antes de guardar.')
      return
    }
    // Distintos
    const uniq = new Set(players)
    if (uniq.size !== 4) {
      showError('Los cuatro jugadores deben ser distintos entre sí.')
      return
    }
    // Comprobar que los ids existen en cache
    const knownIds = playersCache.map(p => p.id)
    const missing = players.filter(id => !knownIds.includes(id))
    if (missing.length > 0) {
      showError('Algún jugador seleccionado no existe. Actualice la lista de jugadores y vuelva a intentarlo.')
      return
    }
    clearError()

    const payload = { title, start, allDay: true, p1, p2, p3, p4 }
    if (currentEventId) {
      fetch(`/api/events/${currentEventId}`, {
        method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
      }).then(r => {
        if (!r.ok) throw r
        calendar.refetchEvents()
        closeModal()
      }).catch(err => { console.error(err); alert('Error actualizando evento') })
    } else {
      fetch('/api/events', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
        .then(r => {
          if (!r.ok) return r.json().then(j=>{ throw new Error(j.error || 'Error creando evento') })
          return r.json()
        })
        .then(() => { calendar.refetchEvents(); closeModal() })
        .catch(err => { console.error(err); showError('Error creando evento: ' + (err.message || '')) })
    }
  })

  // delete
  deleteBtn.addEventListener('click', function() {
    if (!currentEventId) return
    if (!confirm('Eliminar este evento?')) return
    fetch(`/api/events/${currentEventId}`, { method: 'DELETE' })
      .then(r => { if (!r.ok) throw r; calendar.refetchEvents(); closeModal() })
      .catch(err => { console.error(err); showError('Error borrando evento') })
  })

  // save result
  saveResultBtn.addEventListener('click', function() {
    if (!currentEventId) { showError('Abra un evento antes de guardar resultado'); return }
    const score = document.getElementById('evt-score').value
    const winner = parseInt(document.getElementById('evt-winner').value)
    fetch(`/api/events/${currentEventId}/result`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({score, winner}) })
      .then(r => { if (!r.ok) return r.json().then(j=>{ throw new Error(j.error||'') }); calendar.refetchEvents(); closeModal() })
      .catch(err => { console.error(err); showError('Error guardando resultado: ' + (err.message || '')) })
  })

  // inicializar players y calendario
  // Attach the registrar-evento button immediately so it works even if fetchPlayers fails or is slow.
  const newBtnImmediate = document.getElementById('new-event-btn')
  if (newBtnImmediate) {
    newBtnImmediate.addEventListener('click', function(){
      console.log('[PADEL] Registrar evento button clicked')
      // Ensure we have latest players before opening; if fetch fails, still open modal
      fetchPlayers().then(() => { populatePlayerSelects(); const today = new Date().toISOString().split('T')[0]; openModal(null, today) })
      .catch((err) => { console.warn('[PADEL] fetchPlayers failed', err); const today = new Date().toISOString().split('T')[0]; openModal(null, today) })
    })
    // Also expose a global handler as a fallback callable from HTML or console
    window.openCreateEvent = function() {
      console.log('[PADEL] openCreateEvent called')
      fetchPlayers().then(() => { populatePlayerSelects(); const today = new Date().toISOString().split('T')[0]; openModal(null, today) })
      .catch(() => { const today = new Date().toISOString().split('T')[0]; openModal(null, today) })
    }
  }

  fetchPlayers().then(() => { populatePlayerSelects(); calendar.render() })

})
