import os
import sqlite3
from flask import Flask, request, jsonify, render_template_string
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", "turnos.db")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS turnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT NOT NULL,
                numero_turno INTEGER NOT NULL,
                estado TEXT DEFAULT 'esperando',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        db.execute("INSERT OR IGNORE INTO config VALUES ('ultimo_turno', '0')")
        db.commit()

init_db()

def send_whatsapp(to_number, message):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        print(f"[WhatsApp simulado] -> {to_number}: {message}")
        return True
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        to = f"whatsapp:+{to_number.strip().lstrip('+')}"
        client.messages.create(body=message, from_=TWILIO_WHATSAPP_FROM, to=to)
        return True
    except Exception as e:
        print(f"Error WhatsApp: {e}")
        return False

def get_siguiente_turno():
    with get_db() as db:
        row = db.execute("SELECT valor FROM config WHERE clave='ultimo_turno'").fetchone()
        siguiente = int(row["valor"]) + 1
        db.execute("UPDATE config SET valor=? WHERE clave='ultimo_turno'", (siguiente,))
        db.commit()
        return siguiente

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/registrar", methods=["POST"])
def registrar():
    data = request.get_json()
    nombre = data.get("nombre", "").strip()
    telefono = data.get("telefono", "").strip()

    if not nombre or not telefono:
        return jsonify({"error": "Nombre y telefono son requeridos"}), 400

    if len(telefono) < 8:
        return jsonify({"error": "Telefono invalido"}), 400

    numero = get_siguiente_turno()

    with get_db() as db:
        db.execute(
            "INSERT INTO turnos (nombre, telefono, numero_turno) VALUES (?, ?, ?)",
            (nombre, telefono, numero)
        )
        db.commit()

    esperando = get_count_esperando()
    msg = (
        f"Hola {nombre}! Tu turno es el N {numero}.\n"
        f"Hay {esperando - 1} persona(s) antes que tu.\n"
        f"Te avisaremos cuando sea tu turno."
    )
    send_whatsapp(telefono, msg)

    return jsonify({
        "ok": True,
        "turno": numero,
        "mensaje": f"Turno N {numero} registrado. Se enviara aviso por WhatsApp."
    })

@app.route("/api/fila", methods=["GET"])
def ver_fila():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM turnos WHERE estado='esperando' ORDER BY numero_turno ASC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/llamar", methods=["POST"])
def llamar_siguiente():
    with get_db() as db:
        siguiente = db.execute(
            "SELECT * FROM turnos WHERE estado='esperando' ORDER BY numero_turno ASC LIMIT 1"
        ).fetchone()

        if not siguiente:
            return jsonify({"error": "No hay turnos en espera"}), 404

        siguiente = dict(siguiente)
        db.execute("UPDATE turnos SET estado='llamado' WHERE id=?", (siguiente["id"],))
        db.commit()

    msg = (
        f"{siguiente['nombre']}, ES TU TURNO! N {siguiente['numero_turno']}.\n"
        f"Por favor acercate al mostrador ahora."
    )
    send_whatsapp(siguiente["telefono"], msg)

    return jsonify({"ok": True, "turno": siguiente})

@app.route("/api/completar/<int:turno_id>", methods=["POST"])
def completar(turno_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM turnos WHERE id=?", (turno_id,)).fetchone()
        if not row:
            return jsonify({"error": "Turno no encontrado"}), 404
        db.execute("UPDATE turnos SET estado='completado' WHERE id=?", (turno_id,))
        db.commit()
    return jsonify({"ok": True})

@app.route("/api/historial", methods=["GET"])
def historial():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM turnos ORDER BY numero_turno DESC LIMIT 50"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

def get_count_esperando():
    with get_db() as db:
        r = db.execute("SELECT COUNT(*) as c FROM turnos WHERE estado='esperando'").fetchone()
        return r["c"]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Sistema de Turnos</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    color: #1a202c;
  }

  header {
    background: rgba(255,255,255,0.12);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.2);
    color: white;
    padding: 18px 32px;
    display: flex;
    align-items: center;
    gap: 14px;
  }

  header .logo {
    width: 42px; height: 42px;
    background: rgba(255,255,255,0.25);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem;
  }

  header h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.3px; }
  header p { font-size: 0.8rem; opacity: 0.8; margin-top: 2px; }

  .tabs {
    display: flex; gap: 4px;
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(10px);
    padding: 8px 24px;
    border-bottom: 1px solid rgba(255,255,255,0.15);
  }

  .tab {
    padding: 8px 20px; cursor: pointer;
    font-weight: 600; font-size: 0.88rem;
    color: rgba(255,255,255,0.7);
    border-radius: 8px;
    transition: all .2s;
    border: 1px solid transparent;
  }

  .tab:hover { color: white; background: rgba(255,255,255,0.12); }
  .tab.active { color: #6c5ce7; background: white; box-shadow: 0 2px 12px rgba(0,0,0,0.15); }

  .content { padding: 28px 24px; max-width: 860px; margin: 0 auto; }
  .panel { display: none; }
  .panel.active { display: block; animation: fadeIn .25s ease; }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

  .card { background: white; border-radius: 16px; padding: 28px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); margin-bottom: 20px; }
  .card-title { font-size: 1.1rem; font-weight: 700; color: #2d3748; margin-bottom: 6px; }
  .card-subtitle { font-size: 0.83rem; color: #a0aec0; margin-bottom: 24px; }

  .form-group { margin-bottom: 20px; }
  label { display: block; font-weight: 600; font-size: 0.88rem; margin-bottom: 8px; color: #4a5568; }

  input[type="text"], input[type="tel"] {
    width: 100%; padding: 12px 16px;
    border: 2px solid #e8ecf0; border-radius: 10px;
    font-size: 0.95rem; font-family: inherit;
    transition: all .2s; background: #fafbfc; color: #2d3748;
  }

  input:focus { outline: none; border-color: #6c5ce7; background: white; box-shadow: 0 0 0 3px rgba(108,92,231,0.1); }

  .phone-row { display: flex; gap: 10px; }

  .country-select {
    padding: 12px 12px; border: 2px solid #e8ecf0; border-radius: 10px;
    font-size: 0.88rem; font-family: inherit; background: #fafbfc; color: #2d3748;
    cursor: pointer; transition: all .2s; min-width: 140px;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23718096' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; padding-right: 28px;
  }

  .country-select:focus { outline: none; border-color: #6c5ce7; box-shadow: 0 0 0 3px rgba(108,92,231,0.1); }
  .phone-input-wrap { flex: 1; }

  .btn { padding: 13px 28px; border: none; border-radius: 10px; font-size: 0.95rem; font-weight: 700; font-family: inherit; cursor: pointer; transition: all .2s; display: inline-flex; align-items: center; gap: 8px; }

  .btn-primary { background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; width: 100%; justify-content: center; box-shadow: 0 4px 15px rgba(108,92,231,0.35); }
  .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(108,92,231,0.45); }

  .btn-success { background: linear-gradient(135deg, #00b894, #00cec9); color: white; box-shadow: 0 4px 15px rgba(0,184,148,0.3); }
  .btn-success:hover { transform: translateY(-1px); }

  .btn-outline { background: white; color: #6c5ce7; border: 2px solid #e8ecf0; }
  .btn-outline:hover { border-color: #6c5ce7; background: #f8f7ff; }
  .btn-sm { padding: 7px 14px; font-size: 0.82rem; border-radius: 8px; }

  .btn-complete { background: #f0fdf4; color: #15803d; border: 1.5px solid #bbf7d0; font-size: 0.82rem; padding: 6px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all .2s; }
  .btn-complete:hover { background: #dcfce7; }

  .alert { padding: 14px 18px; border-radius: 12px; margin-bottom: 20px; font-weight: 500; font-size: 0.9rem; display: flex; align-items: flex-start; gap: 10px; }
  .alert-success { background: linear-gradient(135deg, #f0fdf4, #dcfce7); color: #166534; border: 1px solid #bbf7d0; }
  .alert-error { background: linear-gradient(135deg, #fef2f2, #fee2e2); color: #991b1b; border: 1px solid #fecaca; }

  .turno-highlight { background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; border-radius: 14px; padding: 20px 24px; text-align: center; margin-bottom: 20px; box-shadow: 0 8px 25px rgba(108,92,231,0.35); }
  .turno-highlight .turno-num { font-size: 3.5rem; font-weight: 800; line-height: 1; }
  .turno-highlight .turno-label { font-size: 0.85rem; opacity: 0.85; margin-top: 4px; }

  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 10px 16px; background: #f8f9fb; color: #718096; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; border-bottom: 2px solid #f0f0f0; }
  td { padding: 13px 16px; border-bottom: 1px solid #f5f5f5; vertical-align: middle; font-size: 0.9rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #fafbff; }

  .badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; }
  .badge-waiting { background: #fef3c7; color: #92400e; }
  .badge-called { background: #dbeafe; color: #1e40af; }
  .badge-done { background: #d1fae5; color: #065f46; }

  .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
  .stat-card { background: white; border-radius: 16px; padding: 22px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); border-top: 4px solid transparent; transition: transform .2s; }
  .stat-card:hover { transform: translateY(-2px); }
  .stat-card:nth-child(1) { border-color: #6c5ce7; }
  .stat-card:nth-child(2) { border-color: #0984e3; }
  .stat-card:nth-child(3) { border-color: #00b894; }
  .stat-num { font-size: 2.6rem; font-weight: 800; color: #2d3748; line-height: 1; }
  .stat-card:nth-child(1) .stat-num { color: #6c5ce7; }
  .stat-card:nth-child(2) .stat-num { color: #0984e3; }
  .stat-card:nth-child(3) .stat-num { color: #00b894; }
  .stat-label { color: #a0aec0; font-size: 0.82rem; font-weight: 600; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.05em; }

  .empty { text-align: center; padding: 48px 20px; color: #cbd5e0; }
  .empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
  .empty-text { font-size: 0.95rem; }

  .called-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border: 1.5px solid #bbf7d0; border-radius: 14px; padding: 20px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .called-num { background: linear-gradient(135deg, #00b894, #00cec9); color: white; border-radius: 12px; width: 56px; height: 56px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 800; flex-shrink: 0; box-shadow: 0 4px 12px rgba(0,184,148,0.35); }
  .called-info { flex: 1; }
  .called-info .called-name { font-weight: 700; font-size: 1rem; color: #2d3748; }
  .called-info .called-phone { font-size: 0.85rem; color: #718096; margin-top: 2px; }

  .turno-row-num { background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; border-radius: 8px; padding: 4px 10px; font-weight: 700; font-size: 0.9rem; display: inline-block; }
  .helper-text { font-size: 0.8rem; color: #a0aec0; margin-top: 10px; }
  .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .admin-actions { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }

  @media (max-width: 600px) {
    .stats-grid { grid-template-columns: 1fr; }
    .phone-row { flex-direction: column; }
    header h1 { font-size: 1.1rem; }
    .content { padding: 16px 14px; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">&#127903;</div>
  <div>
    <h1>Sistema de Turnos</h1>
    <p>Notificaciones por WhatsApp</p>
  </div>
</header>

<div class="tabs">
  <div class="tab active" onclick="showTab('registro')">&#9654; Registrarse</div>
  <div class="tab" onclick="showTab('fila')">&#128203; Fila de Espera</div>
  <div class="tab" onclick="showTab('admin')">&#9881; Panel Admin</div>
  <div class="tab" onclick="showTab('historial')">&#128202; Historial</div>
</div>

<div class="content">

  <div id="tab-registro" class="panel active">
    <div class="card">
      <div class="card-title">&#127919; Sacar turno</div>
      <div class="card-subtitle">Completa tus datos y recibe notificaciones por WhatsApp</div>
      <div id="msg-registro"></div>
      <div class="form-group">
        <label>Nombre completo</label>
        <input type="text" id="nombre" placeholder="Ej: Juan Garcia" autocomplete="off"/>
      </div>
      <div class="form-group">
        <label>Numero de celular</label>
        <div class="phone-row">
          <select class="country-select" id="pais">
            <option value="52" selected>MX +52</option>
            <option value="1">US +1</option>
            <option value="1">CA +1</option>
            <option value="54">AR +54</option>
            <option value="57">CO +57</option>
            <option value="56">CL +56</option>
            <option value="51">PE +51</option>
            <option value="58">VE +58</option>
            <option value="34">ES +34</option>
          </select>
          <div class="phone-input-wrap">
            <input type="tel" id="telefono" placeholder="Ej: 5512345678" inputmode="numeric"/>
          </div>
        </div>
        <div class="helper-text">Ingresa tu numero sin el codigo de pais</div>
      </div>
      <button class="btn btn-primary" onclick="registrar()">
        &#128247; Obtener mi turno
      </button>
      <div class="helper-text" style="text-align:center;margin-top:14px">
        Recibiras un WhatsApp cuando sea tu turno
      </div>
    </div>
  </div>

  <div id="tab-fila" class="panel">
    <div class="card">
      <div class="section-header">
        <div class="card-title">&#128203; Fila de espera</div>
        <button class="btn btn-outline btn-sm" onclick="cargarFila()">&#8635; Actualizar</button>
      </div>
      <div id="tabla-fila"><div class="empty"><div class="empty-icon">&#9203;</div><div class="empty-text">Cargando...</div></div></div>
    </div>
  </div>

  <div id="tab-admin" class="panel">
    <div id="stats-container" class="stats-grid"></div>
    <div class="card">
      <div class="card-title" style="margin-bottom:16px">&#9881; Panel de control</div>
      <div id="msg-admin"></div>
      <div class="admin-actions">
        <button class="btn btn-success" onclick="llamarSiguiente()">&#128266; Llamar siguiente</button>
        <button class="btn btn-outline btn-sm" onclick="cargarStats()">&#8635; Actualizar</button>
      </div>
      <div id="turno-llamado"></div>
    </div>
  </div>

  <div id="tab-historial" class="panel">
    <div class="card">
      <div class="section-header">
        <div class="card-title">&#128202; Historial reciente</div>
        <button class="btn btn-outline btn-sm" onclick="cargarHistorial()">&#8635; Actualizar</button>
      </div>
      <div id="tabla-historial"><div class="empty"><div class="empty-icon">&#128202;</div><div class="empty-text">Cargando...</div></div></div>
    </div>
  </div>

</div>

<script>
function showTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    t.classList.toggle('active', ['registro','fila','admin','historial'][i]===name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if (name==='fila') cargarFila();
  if (name==='admin') { cargarFila(); cargarStats(); }
  if (name==='historial') cargarHistorial();
}

async function registrar() {
  const nombre = document.getElementById('nombre').value.trim();
  const telefonoLocal = document.getElementById('telefono').value.trim().replace(/\D/g,'');
  const pais = document.getElementById('pais').value;
  const telefono = pais + telefonoLocal;
  const el = document.getElementById('msg-registro');

  if (!nombre || !telefonoLocal) {
    el.innerHTML='<div class="alert alert-error">Completa tu nombre y numero de celular.</div>';
    return;
  }

  const btn = document.querySelector('#tab-registro .btn-primary');
  btn.disabled = true;
  btn.textContent = 'Registrando...';

  const res = await fetch('/api/registrar', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({nombre, telefono})
  });
  const data = await res.json();
  btn.disabled = false;
  btn.innerHTML = '&#128247; Obtener mi turno';

  if (data.ok) {
    el.innerHTML = '<div class="turno-highlight"><div class="turno-num">#' + data.turno + '</div><div class="turno-label">Tu numero de turno &bull; ' + nombre + '</div></div><div class="alert alert-success">Turno asignado. Recibiras un WhatsApp de confirmacion en breve.</div>';
    document.getElementById('nombre').value='';
    document.getElementById('telefono').value='';
  } else {
    el.innerHTML = '<div class="alert alert-error">' + data.error + '</div>';
  }
}

async function cargarFila() {
  const res = await fetch('/api/fila');
  const filas = await res.json();
  const el = document.getElementById('tabla-fila');
  if (!filas.length) {
    el.innerHTML='<div class="empty"><div class="empty-icon">&#9989;</div><div class="empty-text">No hay turnos en espera</div></div>';
    return;
  }
  el.innerHTML = '<table><thead><tr><th>Turno</th><th>Nombre</th><th>Telefono</th><th>Estado</th></tr></thead><tbody>' +
    filas.map(f=>'<tr><td><span class="turno-row-num">#'+f.numero_turno+'</span></td><td><strong>'+f.nombre+'</strong></td><td>'+f.telefono+'</td><td><span class="badge badge-waiting">Esperando</span></td></tr>').join('') +
    '</tbody></table>';
}

async function cargarStats() {
  const [fila, hist] = await Promise.all([
    fetch('/api/fila').then(r=>r.json()),
    fetch('/api/historial').then(r=>r.json())
  ]);
  const completados = hist.filter(h=>h.estado==='completado').length;
  const llamados = hist.filter(h=>h.estado==='llamado').length;
  document.getElementById('stats-container').innerHTML =
    '<div class="stat-card"><div class="stat-num">'+fila.length+'</div><div class="stat-label">En espera</div></div>' +
    '<div class="stat-card"><div class="stat-num">'+llamados+'</div><div class="stat-label">Llamados</div></div>' +
    '<div class="stat-card"><div class="stat-num">'+completados+'</div><div class="stat-label">Completados</div></div>';
}

async function llamarSiguiente() {
  const el = document.getElementById('msg-admin');
  const res = await fetch('/api/llamar', {method:'POST'});
  const data = await res.json();
  if (data.ok) {
    const t = data.turno;
    document.getElementById('turno-llamado').innerHTML =
      '<div class="called-card">' +
        '<div class="called-num">#'+t.numero_turno+'</div>' +
        '<div class="called-info"><div class="called-name">'+t.nombre+'</div><div class="called-phone">'+t.telefono+'</div></div>' +
        '<button class="btn-complete" onclick="completar('+t.id+')">Completar</button>' +
      '</div>';
    cargarStats();
  } else {
    el.innerHTML = '<div class="alert alert-error">'+data.error+'</div>';
    setTimeout(()=>el.innerHTML='', 3000);
  }
}

async function completar(id) {
  await fetch('/api/completar/'+id, {method:'POST'});
  document.getElementById('turno-llamado').innerHTML = '<div class="alert alert-success">Turno completado.</div>';
  setTimeout(()=>document.getElementById('turno-llamado').innerHTML='', 2500);
  cargarStats();
}

async function cargarHistorial() {
  const res = await fetch('/api/historial');
  const rows = await res.json();
  const el = document.getElementById('tabla-historial');
  if (!rows.length) {
    el.innerHTML='<div class="empty"><div class="empty-icon">&#128202;</div><div class="empty-text">Sin registros aun</div></div>';
    return;
  }
  const eClass = { esperando:'badge-waiting', llamado:'badge-called', completado:'badge-done' };
  el.innerHTML = '<table><thead><tr><th>Turno</th><th>Nombre</th><th>Telefono</th><th>Estado</th><th>Registrado</th></tr></thead><tbody>' +
    rows.map(r=>'<tr><td><span class="turno-row-num">#'+r.numero_turno+'</span></td><td><strong>'+r.nombre+'</strong></td><td>'+r.telefono+'</td><td><span class="badge '+eClass[r.estado]+'">'+r.estado+'</span></td><td style="font-size:.82rem;color:#a0aec0">'+new Date(r.creado_en+'Z').toLocaleString('es-MX')+'</td></tr>').join('') +
    '</tbody></table>';
}

document.getElementById('nombre').addEventListener('keydown', e => { if(e.key==='Enter') document.getElementById('telefono').focus(); });
document.getElementById('telefono').addEventListener('keydown', e => { if(e.key==='Enter') registrar(); });
</script>
</body>
</html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
