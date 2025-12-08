document.addEventListener('DOMContentLoaded', function(){
  const list = document.getElementById('mini-list')
  const ctx = document.getElementById('mini-chart')
  let chart = null
  function load(){
    fetch('/api/stats')
      .then(r=>r.json())
      .then(data=>{
        // top 5 in list
        list.innerHTML = ''
        const top = data.slice(0,5)
        top.forEach(p=>{
          const li = document.createElement('li')
          li.style.padding = '6px 0'
          li.textContent = `${p.first_name} ${p.last_name || ''} — ${p.wins}W / ${p.played}P (${p.win_rate}%)`
          list.appendChild(li)
        })
        // chart: wins for top 5
        const labels = top.map(p=>`${p.first_name} ${p.last_name||''}`)
        const wins = top.map(p=>p.wins)
        if (ctx){
          if (chart) chart.destroy()
          chart = new Chart(ctx, {
            type: 'bar',
            data: { labels, datasets:[{ label:'Victorias', data: wins, backgroundColor:'rgba(255,90,31,0.9)' }] },
            options: { responsive:true, plugins:{ legend:{ display:false } }, scales:{ x:{ ticks:{ color:'#fff' } }, y:{ ticks:{ color:'#fff' } } } }
          })
        }
      })
  }
  load()
})
