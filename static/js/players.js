document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('player-form')
  const tableBody = document.querySelector('#players-table tbody')

  function loadPlayers() {
    fetch('/api/players')
      .then(r => r.json())
      .then(data => {
        tableBody.innerHTML = ''
        data.forEach(p => {
          const tr = document.createElement('tr')
          tr.innerHTML = `<td>${p.id}</td><td>${p.first_name}</td><td>${p.last_name || ''}</td><td><button data-id="${p.id}" class="del">Borrar</button></td>`
          tableBody.appendChild(tr)
        })
        ;[...tableBody.querySelectorAll('.del')].forEach(btn => btn.addEventListener('click', ev => {
          const id = btn.getAttribute('data-id')
          if (!confirm('Borrar jugador?')) return
          fetch(`/api/players/${id}`, { method: 'DELETE' })
            .then(r => { if (!r.ok) throw r; loadPlayers() })
            .catch(err => { console.error(err); alert('Error borrando') })
        }))
      })
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault()
    const first = document.getElementById('first_name').value
    const last = document.getElementById('last_name').value
    fetch('/api/players', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ first_name: first, last_name: last }) })
      .then(r => r.json())
      .then(() => { form.reset(); loadPlayers() })
      .catch(err => { console.error(err); alert('Error creando jugador') })
  })

  loadPlayers()
})
