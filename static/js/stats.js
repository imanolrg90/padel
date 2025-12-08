document.addEventListener('DOMContentLoaded', function() {
  const tbody = document.querySelector('#stats-table tbody')
  let chart = null
  function load() {
    fetch('/api/stats')
      .then(r => r.json())
      .then(data => {
        tbody.innerHTML = ''
        const labels = []
        const wins = []
        data.forEach(p => {
          const tr = document.createElement('tr')
          tr.innerHTML = `<td>${p.id}</td><td>${p.first_name} ${p.last_name || ''}</td><td>${p.played}</td><td>${p.wins}</td><td>${p.losses}</td><td>${p.win_rate}%</td>`
          tbody.appendChild(tr)
          labels.push(`${p.first_name} ${p.last_name || ''}`)
          wins.push(p.wins)
        })
        // draw chart
        const ctx = document.getElementById('stats-chart')
        if (ctx) {
          if (chart) chart.destroy()
          chart = new Chart(ctx, {
            type: 'bar',
            data: { labels, datasets: [{ label: 'Victorias', data: wins, backgroundColor: 'rgba(54,162,235,0.6)' }] },
            options: { responsive: true, plugins: { legend: { display: false } } }
          })
        }
      })
  }

  function exportCSV() {
    fetch('/api/stats')
      .then(r => r.json())
      .then(data => {
        const cols = ['id','first_name','last_name','played','wins','losses','win_rate']
        const rows = data.map(r => cols.map(c => r[c]))
        const csv = [cols.join(','), ...rows.map(r => r.map(v=>`"${String(v).replace(/"/g,'""')}"`).join(','))].join('\n')
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'stats.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  document.getElementById('export-csv').addEventListener('click', exportCSV)
  document.getElementById('refresh-stats').addEventListener('click', load)

  load()
})
