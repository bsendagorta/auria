// AURIA · Marcador para capturar actuaciones de @BomberosBizkaia
// -------------------------------------------------------------
// Qué hace: en la página https://x.com/BomberosBizkaia, al pulsarlo, baja por la lista de tuits,
// recoge las actuaciones visibles (tipo, municipio y hora exacta sacada del id del tuit) y las
// muestra en un recuadro para que las copies (Cmd/Ctrl+C) y las pegues en el chat de AURIA.
// Lo lees tú desde tu propia sesión: no es un robot. Cuantos más tuits cargues (haz scroll antes
// o inicia sesión), más historial captura.
//
// Instalación: crea un marcador nuevo en el navegador y pega como DIRECCIÓN la versión de una línea
// de abajo (empieza por "javascript:"). Luego abre la cuenta y pulsa el marcador.

(async () => {
  const EP = 1288834974657, TW = {};
  const grab = () => document.querySelectorAll('article').forEach(a => {
    const l = a.querySelector('a[href*="/status/"]'); if (!l) return;
    const m = l.getAttribute('href').match(/status\/(\d+)/); if (!m) return;
    const id = m[1];
    const ts = new Date(Number(BigInt(id) >> 22n) + EP).toISOString();
    const t = a.innerText; if (t && t.length > 20) TW[id] = { ts, t };
  });
  grab();
  for (let i = 0; i < 40; i++) { scrollBy(0, 2400); await new Promise(r => setTimeout(r, 700)); grab(); }
  scrollTo(0, 0);
  const txt = Object.entries(TW).map(([id, v]) => id + '\t' + v.ts + '\t' + v.t.replace(/\n+/g, '¶')).join('\n');
  const ta = document.createElement('textarea');
  ta.value = txt;
  Object.assign(ta.style, { position: 'fixed', top: '5%', left: '5%', width: '90%', height: '80%',
    zIndex: 99999, fontSize: '12px', background: '#111', color: '#0f0', padding: '10px' });
  document.body.appendChild(ta); ta.focus(); ta.select();
  alert('AURIA: ' + Object.keys(TW).length + ' actuaciones. Cópialas (Cmd/Ctrl+C) y pégalas en el chat. Luego pulsa fuera del recuadro para cerrarlo.');
  ta.addEventListener('blur', () => ta.remove());
})();
