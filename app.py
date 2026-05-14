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

    # Inicializar la base de datos al arrancar (funciona con gunicorn y desarrollo)
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
                return jsonify({"error": "Nombre y teléfono son requeridos"}), 400

    if len(telefono) < 8:
                return jsonify({"error": "Teléfono inválido"}), 400

    numero = get_siguiente_turno()

    with get_db() as db:
                db.execute(
                                "INSERT INTO turnos (nombre, telefono, numero_turno) VALUES (?, ?, ?)",
                                (nombre, telefono, numero)
                )
                db.commit()

    esperando = get_count_esperando()
    msg = (
                f"✅ Hola {nombre}! Tu turno es el N° {numero}.\n"
                f"Hay {esperando - 1} persona(s) antes que tú.\n"
                f"Te avisaremos cuando sea tu turno. 🎟️"
    )
    send_whatsapp(telefono, msg)

    return jsonify({
                "ok": True,
                "turno": numero,
                "mensaje": f"Turno N° {numero} registrado. Se enviará aviso por WhatsApp."
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
                f"🔔 {siguiente['nombre']}, ¡ES TU TURNO! N° {siguiente['numero_turno']}.\n"
                f"Por favor acércate al mostrador ahora."
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
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #1a202c; }
header { background: #2b6cb0; color: white; padding: 20px 30px; display: flex; align-items: center; gap: 12px; }
header h1 { font-size: 1.5rem; }
.tabs { display: flex; gap: 0; background: white; border-bottom: 2px solid #e2e8f0; padding: 0 30px; }
.tab { padding: 14px 24px; cursor: pointer; font-weight: 600; color: #718096; border-bottom: 3px solid transparent; transition: all .2s; }
.tab.active { color: #2b6cb0; border-bottom-color: #2b6cb0; }
.content { padding: 30px; max-width: 900px; margin: 0 auto; }
.panel { display: none; }
.panel.active { display: block; }
.card { background: white; border-radius: 12px; padding: 28px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 20px; }
.form-group { margin-bottom: 18px; }
label { display: block; font-weight: 600; margin-bottom: 6px; color: #4a5568; }
input { width: 100%; padding: 10px 14px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1rem; transition: border .2s; }
input:focus { outline: none; border-color: #2b6cb0; }
.btn { padding: 12px 28px; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all .2s; }
.btn-primary { background: #2b6cb0; color: white; width: 100%; }
.btn-primary:hover { background: #2c5282; }
.btn-success { background: #38a169; color: white; }
.btn-success:hover { background: #276749; }
.btn-sm { padding: 6px 14px; font-size: .85rem; }
.alert { padding: 14px 18px; border-radius: 8px; margin-bottom: 16px; font-weight: 500; }
.alert-success { background: #c6f6d5; color: #276749; }
.alert-error { background: #fed7d7; color: #9b2335; }
.turno-badge { display: inline-block; background: #ebf8ff; color: #2b6cb0; font-size: 2rem; font-weight: 800; padding: 8px 24px; border-radius: 12px; border: 2px solid #bee3f8; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 14px; background: #f7fafc; color: #718096; font-size: .85rem; text-transform: uppercase; letter-spacing: .05em; }
td { padding: 12px 14px; border-top: 1px solid #e2e8f0; vertical-align: middle; }
tr:hover td { background: #f7fafc; }
.estado { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: .8rem; font-weight: 600; }
.estado-esperando { background: #fefcbf; color: #744210; }
.estado-llamado { background: #bee3f8; color: #2c5282; }
.estado-completado { background: #c6f6d5; color: #276749; }
.stat { text-align: center; }
.stat-num { font-size: 2.5rem; font-weight: 800; color: #2b6cb0; }
.stat-label { color: #718096; font-size: .9rem; margin-top: 4px; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }
.empty { text-align: center; padding: 40px; color: #a0aec0; }
.refresh-note { font-size: .8rem; color: #a0aec0; margin-top: 8px; }
</style>
</head>
<body>
<header>
<span style="font-size:1.8rem">🎟️</span>
<h1>Sistema de Turnos con WhatsApp</h1>
</header>
<div class="tabs">
<div class="tab active" onclick="showTab('registro')">Registrarse</div>
<div class="tab" onclick="showTab('fila')">Fila de Espera</div>
<div class="tab" onclick="showTab('admin')">Panel Admin</div>
<div class="tab" onclick="showTab('historial')">Historial</div>
</div>
<div class="content">

<!-- REGISTRO -->
<div id="tab-registro" class="panel active">
<div class="card">
<h2 style="margin-bottom:20px;color:#2b6cb0">Sacar turno</h2>
<div id="msg-registro"></div>
<div class="form-group">
<label>Nombre completo</label>
<input type="text" id="nombre" placeholder="Ej: Juan García" />
</div>
<div class="form-group">
<label>Celular (con código de país, sin +)</label>
<input type="tel" id="telefono" placeholder="Ej: 5491155554444" />
</div>
<button class="btn btn-primary" onclick="registrar()">Obtener turno 🎟️</button>
<p class="refresh-note" style="margin-top:12px">Recibirás una notificación por WhatsApp con tu número de turno y cuando te llamen.</p>
</div>
</div>

<!-- FILA -->
<div id="tab-fila" class="panel">
<div class="card">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
<h2 style="color:#2b6cb0">Fila de espera</h2>
<button class="btn btn-sm" style="background:#e2e8f0;color:#4a5568" onclick="cargarFila()">↻ Actualizar</button>
</div>
<div id="tabla-fila"><div class="empty">Cargando...</div></div>
</div>
</div>

<!-- ADMIN -->
<div id="tab-admin" class="panel">
<div id="stats-container" class="stats-grid"></div>
<div class="card">
<h2 style="margin-bottom:16px;color:#2b6cb0">Panel de control</h2>
<div id="msg-admin"></div>
<button class="btn btn-success" onclick="llamarSiguiente()" style="margin-bottom:16px">
📢 Llamar siguiente turno
</button>
<div id="turno-llamado"></div>
</div>
</div>

<!-- HISTORIAL -->
<div id="tab-historial" class="panel">
<div class="card">
<h2 style="margin-bottom:16px;color:#2b6cb0">Historial reciente</h2>
<div id="tabla-historial"><div class="empty">Cargando...</div></div>
</div>
</div>

</div>
<script>
function showTab(name) {
document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['registro','fila','admin','historial'][i]===name));
document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
document.getElementById('tab-'+name).classList.add('active');
if (name==='fila') cargarFila();
if (name==='admin') { cargarFila(); cargarStats(); }
if (name==='historial') cargarHistorial();
}

async function registrar() {
const nombre = document.getElementById('nombre').value.trim();
const telefono = document.getElementById('telefono').value.trim();
const el = document.getElementById('msg-registro');
if (!nombre || !telefono) { el.innerHTML='<div class="alert alert-error">Completá ambos campos.</div>'; return; }
const res = await fetch('/api/registrar', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({nombre, telefono})});
const data = await res.json();
if (data.ok) {
el.innerHTML = `<div class="alert alert-success">✅ Turno N° <strong>${data.turno}</strong> asignado. Recibirás WhatsApp de confirmación.</div>`;
document.getElementById('nombre').value='';
document.getElementById('telefono').value='';
} else {
el.innerHTML = `<div class="alert alert-error">❌ ${data.error}</div>`;
}
}

async function cargarFila() {
const res = await fetch('/api/fila');
const filas = await res.json();
const el = document.getElementById('tabla-fila');
if (!filas.length) { el.innerHTML='<div class="empty">🎉 No hay turnos en espera</div>'; return; }
el.innerHTML = `<table><thead><tr><th>N° Turno</th><th>Nombre</th><th>Teléfono</th><th>Estado</th></tr></thead><tbody>
${filas.map(f=>`<tr><td><strong>#${f.numero_turno}</strong></td><td>${f.nombre}</td><td>${f.telefono}</td><td><span class="estado estado-esperando">Esperando</span></td></tr>`).join('')}
</tbody></table>`;
}

async function cargarStats() {
const [fila, hist] = await Promise.all([fetch('/api/fila').then(r=>r.json()), fetch('/api/historial').then(r=>r.json())]);
const completados = hist.filter(h=>h.estado==='completado').length;
const llamados = hist.filter(h=>h.estado==='llamado').length;
document.getElementById('stats-container').innerHTML = `
<div class="card stat"><div class="stat-num">${fila.length}</div><div class="stat-label">En espera</div></div>
<div class="card stat"><div class="stat-num">${llamados}</div><div class="stat-label">Llamados</div></div>
<div class="card stat"><div class="stat-num">${completados}</div><div class="stat-label">Completados</div></div>`;
}

async function llamarSiguiente() {
const el = document.getElementById('msg-admin');
const res = await fetch('/api/llamar', {method:'POST'});
const data = await res.json();
if (data.ok) {
const t = data.turno;
document.getElementById('turno-llamado').innerHTML = `
<div class="alert alert-success">
🔔 Llamando turno: <span class="turno-badge">#${t.numero_turno}</span>
<strong style="margin-left:12px">${t.nombre}</strong>
<span style="color:#718096;margin-left:8px">${t.telefono}</span>
<button class="btn btn-sm" style="background:#38a169;color:white;margin-left:12px" onclick="completar(${t.id})">✓ Completar</button>
</div>`;
cargarStats();
} else {
el.innerHTML = `<div class="alert alert-error">⚠️ ${data.error}</div>`;
setTimeout(()=>el.innerHTML='', 3000);
}
}

async function completar(id) {
await fetch('/api/completar/'+id, {method:'POST'});
document.getElementById('turno-llamado').innerHTML = '<div class="alert alert-success">✅ Turno completado.</div>';
setTimeout(()=>document.getElementById('turno-llamado').innerHTML='', 2000);
cargarStats();
}

async function cargarHistorial() {
const res = await fetch('/api/historial');
const rows = await res.json();
const el = document.getElementById('tabla-historial');
if (!rows.length) { el.innerHTML='<div class="empty">Sin registros aún</div>'; return; }
el.innerHTML = `<table><thead><tr><th>N°</th><th>Nombre</th><th>Teléfono</th><th>Estado</th><th>Registrado</th></tr></thead><tbody>
${rows.map(r=>`<tr>
<td><strong>#${r.numero_turno}</strong></td>
<td>${r.nombre}</td><td>${r.telefono}</td>
<td><span class="estado estado-${r.estado}">${r.estado}</span></td>
<td style="font-size:.85rem;color:#718096">${new Date(r.creado_en+'Z').toLocaleString('es')}</td>
</tr>`).join('')}
</tbody></table>`;
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
