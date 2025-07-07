import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict
import pandas as pd
from functools import wraps
from flask import session, redirect
import base64
import smtplib
from email.mime.text import MIMEText
import os

# -------------------- CONEXIÓN --------------------

def conectar_db():
    db_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if db_path:
        # Railway montó un volumen persistente: usamos ese path
        db_path = os.path.join(db_path, "database.db")
    else:
        # Desarrollo local o entorno sin volumen
        db_path = "database.db"
    return sqlite3.connect(db_path)


# -------------------- CREACIÓN Y MIGRACIONES --------------------

def crear_base_de_datos():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol TEXT NOT NULL,
            verificado INTEGER DEFAULT 0
        )
    ''')



    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plazas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ubicacion TEXT,
            usuario_id INTEGER NOT NULL,
            fecha_creacion DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cortes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaza INTEGER NOT NULL,
            fecha_corte DATE NOT NULL,
            FOREIGN KEY (plaza) REFERENCES plazas(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arreglos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaza_id INTEGER NOT NULL,
            tarea TEXT NOT NULL,
            fecha_ingreso DATE NOT NULL,
            relevadores TEXT,
            realizada INTEGER DEFAULT 0,
            fecha_realizacion DATE,
            personas_involucradas TEXT,
            FOREIGN KEY (plaza_id) REFERENCES plazas(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alertas_ignoradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            plaza_id INTEGER NOT NULL,
            tipo_alerta TEXT NOT NULL,
            ignorar_hasta DATE NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (plaza_id) REFERENCES plazas(id),
            UNIQUE(usuario_id, plaza_id, tipo_alerta)
        )
    ''')

    conn.commit()
    conn.close()

def actualizar_tabla_plazas_agregar_fecha_creacion():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(plazas)")
    columnas = [col[1] for col in cursor.fetchall()]
    if "fecha_creacion" not in columnas:
        cursor.execute("ALTER TABLE plazas ADD COLUMN fecha_creacion DATE")
        hoy = datetime.today().strftime("%Y-%m-%d")
        cursor.execute("UPDATE plazas SET fecha_creacion = ?", (hoy,))
        conn.commit()
    conn.close()

def migrar_tabla_arreglos_a_tareas_individuales():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='arreglos'")
    if not cursor.fetchone():
        conn.close()
        return
    conn.close()

# -------------------- USUARIOS --------------------

def registrar_usuario(username, password, rol):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
            (username, password, rol)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


# -------------------- USUARIOS --------------------

def verificar_usuario(username, password):
    conn = conectar_db()
    conn.row_factory = sqlite3.Row  # 👈 Esto es lo que transforma las filas en objetos tipo diccionario
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user



def obtener_usuario_id(username: str) -> int:
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else None

def solo_servicios(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if session.get('rol') != 'servicios':
            return "⛔ Acceso no autorizado", 403
        return f(*args, **kwargs)
    return decorador

def decodificar_token(token):
    try:
        return int(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception:
        return None

def enviar_correo_verificacion(destinatario, enlace):
    remitente = "obitluciano4@gmail.com"          
    clave_app = "fuar ipxg kumy klsj"       

    mensaje = MIMEText(f"""
Hola 👋

Gracias por registrarte en el sistema de Servicios Urbanos.

Para activar tu cuenta, hacé clic en este enlace:

{enlace}

Si no solicitaste este registro, podés ignorar este mensaje.
    """)
    mensaje['Subject'] = "Activación de cuenta – Municipalidad"
    mensaje['From'] = remitente
    mensaje['To'] = destinatario

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as servidor:
            servidor.login(remitente, clave_app)
            servidor.send_message(mensaje)
        print(f"📩 Correo enviado a {destinatario}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")
        return False

# -------------------- PLAZAS --------------------

def agregar_plaza(nombre, ubicacion, usuario_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO plazas (nombre, ubicacion, usuario_id) VALUES (?, ?, ?)",
        (nombre, ubicacion, usuario_id)
    )
    conn.commit()
    conn.close()

def obtener_plazas():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, ubicacion FROM plazas")
    plazas = cursor.fetchall()
    conn.close()
    return plazas

def buscar_plazas_por_nombre(texto: str) -> List[Dict]:
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, ubicacion FROM plazas WHERE nombre LIKE ?",
        (f"%{texto}%",)
    )
    resultados = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'nombre': r[1], 'ubicacion': r[2]} for r in resultados]

def eliminar_plaza(plaza_id: int):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM arreglos WHERE plaza_id = ?", (plaza_id,))
    cursor.execute("DELETE FROM cortes WHERE plaza = ?", (plaza_id,))
    cursor.execute("DELETE FROM plazas WHERE id = ?", (plaza_id,))
    conn.commit()
    conn.close()

def obtener_nombres_plaza():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM plazas ORDER BY nombre ASC")
    nombres = [fila[0] for fila in cursor.fetchall()]
    conn.close()
    return nombres

def buscar_arreglos_por_plaza(nombre):
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.id, p.nombre, a.tarea, a.fecha_ingreso
            FROM arreglos a
            JOIN plazas p ON a.plaza_id = p.id
            WHERE p.nombre LIKE ?
            ORDER BY a.fecha_ingreso DESC
        ''', (f'%{nombre}%',))
        return cursor.fetchall()

# -------------------- CORTES --------------------

def registrar_corte(nombre_plaza, fecha):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM plazas WHERE nombre = ?", (nombre_plaza,))
    resultado = cursor.fetchone()
    if resultado:
        plaza = resultado[0]
        cursor.execute("INSERT INTO cortes (plaza, fecha_corte) VALUES (?, ?)", (plaza, fecha))
        conn.commit()
    conn.close()

def exportar_cortes_a_excel(nombre_archivo='cortes_exportados.xlsx') -> str:
    conn = conectar_db()
    df = pd.read_sql_query('''
        SELECT p.nombre AS plaza, c.fecha_corte
        FROM cortes c
        JOIN plazas p ON c.plaza = p.id
        ORDER BY c.fecha_corte DESC
    ''', conn)
    df.to_excel(nombre_archivo, index=False)
    conn.close()
    return nombre_archivo

def obtener_cortes_por_plaza(anio: int, mes: int = None) -> Dict[str, int]:
    conn = conectar_db()
    cursor = conn.cursor()
    if mes:
        cursor.execute('''
            SELECT p.nombre, COUNT(*)
            FROM cortes c
            JOIN plazas p ON c.plaza = p.id
            WHERE strftime('%Y', c.fecha_corte) = ? AND strftime('%m', c.fecha_corte) = ?
            GROUP BY p.nombre
        ''', (str(anio), f"{mes:02}"))
    else:
        cursor.execute('''
            SELECT p.nombre, COUNT(*)
            FROM cortes c
            JOIN plazas p ON c.plaza = p.id
            WHERE strftime('%Y', c.fecha_corte) = ?
            GROUP BY p.nombre
        ''', (str(anio),))
    resultados = cursor.fetchall()
    conn.close()
    return {nombre: cantidad for nombre, cantidad in resultados}

# -------------------- CORTES (continuación) --------------------

def historial_cortes_por_plaza() -> Dict[str, List[str]]:
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.nombre, c.fecha_corte
        FROM cortes c
        JOIN plazas p ON c.plaza = p.id
        ORDER BY p.nombre, c.fecha_corte
    ''')
    datos = cursor.fetchall()
    conn.close()
    historial = defaultdict(list)
    for nombre, fecha in datos:
        historial[nombre].append(fecha)
    return historial

def eliminar_corte(corte_id: int):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cortes WHERE id = ?", (corte_id,))
    conn.commit()
    conn.close()

# -------------------- ARREGLOS --------------------

def registrar_solicitud_arreglo(nombre_plaza: str, tareas_texto: str, fecha_ingreso: str, relevadores: str):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM plazas WHERE nombre = ?", (nombre_plaza,))
    resultado = cursor.fetchone()
    if resultado:
        plaza_id = resultado[0]
        tareas = [t.strip() for t in tareas_texto.splitlines() if t.strip()]
        for tarea in tareas:
            cursor.execute('''
                INSERT INTO arreglos (plaza_id, tarea, fecha_ingreso, relevadores, realizada)
                VALUES (?, ?, ?, ?, 0)
            ''', (plaza_id, tarea, fecha_ingreso, relevadores))
        conn.commit()
    conn.close()

def obtener_arreglos_pendientes(anio=None, mes=None, plaza=None):
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT a.id, p.nombre, a.tarea, a.fecha_ingreso, a.relevadores
        FROM arreglos a
        JOIN plazas p ON a.plaza_id = p.id
        WHERE a.realizada = 0
    '''
    parametros = []

    if anio and mes:
        query += ' AND strftime("%Y", a.fecha_ingreso) = ? AND strftime("%m", a.fecha_ingreso) = ?'
        parametros.extend([str(anio), f"{mes:02}"])

    if plaza:
        query += ' AND p.nombre LIKE ?'
        parametros.append(f"%{plaza}%")

    query += ' ORDER BY a.fecha_ingreso DESC'

    cursor.execute(query, parametros)
    resultados = cursor.fetchall()
    conn.close()

    # Formatear y estructurar resultados para el HTML
    def formatear_fecha(fecha_str):
        from datetime import datetime
        try:
            return datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return fecha_str or "—"

    return [{
        'id': r[0],
        'nombre': r[1],
        'tareas': r[2],
        'fecha_ingreso': formatear_fecha(r[3]),
        'relevadores': r[4],
    } for r in resultados]

def marcar_tarea_realizada(arreglo_id: int, fecha_realizacion: str, personas: str):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE arreglos
        SET realizada = 1, fecha_realizacion = ?, personas_involucradas = ?
        WHERE id = ?
    """, (fecha_realizacion, personas, arreglo_id))
    conn.commit()
    conn.close()

def obtener_arreglos_realizados(anio=None, mes=None, plaza_filtrada=None):
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT a.id, p.nombre, a.plaza_id, a.tarea, a.fecha_realizacion, a.personas_involucradas
        FROM arreglos a
        JOIN plazas p ON a.plaza_id = p.id
        WHERE a.realizada = 1
    '''
    params = []

    if anio and mes:
        query += ' AND strftime("%Y", a.fecha_realizacion) = ? AND strftime("%m", a.fecha_realizacion) = ?'
        params.extend([str(anio), f"{int(mes):02d}"])

    if plaza_filtrada:
        query += ' AND p.nombre LIKE ?'
        params.append(f"%{plaza_filtrada}%")

    cursor.execute(query, params)
    resultados = cursor.fetchall()

    arreglos = []
    for fila in resultados:
        arreglos.append({
            'id': fila[0],
            'nombre': fila[1],
            'plaza_id': fila[2],
            'tareas': fila[3], 
            'fecha_realizacion': fila[4],
            'personas': fila[5]
        })


def eliminar_arreglo(arreglo_id: int):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM arreglos WHERE id = ?", (arreglo_id,))
    conn.commit()
    conn.close()

# -------------------- ALERTAS --------------------

def plazas_sin_corte(usuario_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, fecha_creacion FROM plazas")
    plazas = cursor.fetchall()
    hoy = datetime.today()
    alertas = []

    for plaza_id, nombre, fecha_creacion_str in plazas:
        cursor.execute('''
            SELECT ignorar_hasta FROM alertas_ignoradas
            WHERE usuario_id = ? AND plaza_id = ? AND tipo_alerta = 'corte'
        ''', (usuario_id, plaza_id))
        ignorada = cursor.fetchone()
        if ignorada:
            ignorar_hasta = datetime.strptime(ignorada[0], '%Y-%m-%d')
            if ignorar_hasta >= hoy:
                continue

        cursor.execute('''
            SELECT fecha_corte FROM cortes
            WHERE plaza = ?
            ORDER BY fecha_corte DESC LIMIT 1
        ''', (plaza_id,))
        resultado = cursor.fetchone()

        if resultado:
            ultima_fecha = datetime.strptime(resultado[0], "%Y-%m-%d")
            dias = (hoy - ultima_fecha).days
            if dias >= 13:
                alertas.append({
                    'mensaje': f"⚠️ '{nombre}' fue cortada hace {dias} días.",
                    'plaza_id': plaza_id
                })
        else:
            fecha_creacion = datetime.strptime(fecha_creacion_str, "%Y-%m-%d")
            dias_sin_cortes = (hoy - fecha_creacion).days
            if dias_sin_cortes >= 13:
                alertas.append({
                    'mensaje': f"⚠️ '{nombre}' no tiene cortes desde su creación.",
                    'plaza_id': plaza_id
                })

    conn.close()
    return alertas

def ignorar_alerta(usuario_id: int, plaza_id: int, tipo_alerta: str):
    conn = conectar_db()
    cursor = conn.cursor()
    ignorar_hasta = (datetime.today() + timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute('''
        INSERT INTO alertas_ignoradas (usuario_id, plaza_id, tipo_alerta, ignorar_hasta)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(usuario_id, plaza_id, tipo_alerta)
        DO UPDATE SET ignorar_hasta = excluded.ignorar_hasta
    ''', (usuario_id, plaza_id, tipo_alerta, ignorar_hasta))
    conn.commit()
    conn.close()

def obtener_arreglos_con_alerta(usuario_id):
    conn = conectar_db()
    cursor = conn.cursor()
    hoy = datetime.today().date()

    cursor.execute('''
        SELECT a.id, p.nombre, a.plaza_id, a.tarea, a.fecha_ingreso
        FROM arreglos a
        JOIN plazas p ON a.plaza_id = p.id
        WHERE a.realizada = 0
    ''')
    resultados = cursor.fetchall()

    alertas = []
    for id_, nombre_plaza, plaza_id, tarea, fecha_ing in resultados:
        cursor.execute('''
            SELECT ignorar_hasta FROM alertas_ignoradas
            WHERE usuario_id = ? AND plaza_id = ? AND tipo_alerta = 'arreglo'
        ''', (usuario_id, plaza_id))
        ignorada = cursor.fetchone()
        if ignorada:
            ignorar_hasta = datetime.strptime(ignorada[0], '%Y-%m-%d').date()
            if ignorar_hasta >= hoy:
                continue

        fecha_ingreso = datetime.strptime(fecha_ing, '%Y-%m-%d').date()
        dias = (hoy - fecha_ingreso).days
        if dias >= 13:
            alertas.append({
                'id': id_,
                'plaza_id': plaza_id,
                'tarea': tarea,
                'dias': dias,
                'nombre': nombre_plaza
            })

    conn.close()
    return alertas

def omitir_alerta_arreglo(arreglo_id: int, usuario_id: int):
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("SELECT plaza_id FROM arreglos WHERE id = ?", (arreglo_id,))
    resultado = cursor.fetchone()

    if resultado:
        plaza_id = resultado[0]
        ignorar_hasta = (datetime.today() + timedelta(days=7)).strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT INTO alertas_ignoradas (usuario_id, plaza_id, tipo, ignorar_hasta)
            VALUES (?, ?, 'arreglo', ?)
            ON CONFLICT(usuario_id, plaza_id, tipo)
            DO UPDATE SET ignorar_hasta = excluded.ignorar_hasta
        ''', (usuario_id, plaza_id, ignorar_hasta))
        conn.commit()

    conn.close()

# -------------------- CORTES (por mes/año) --------------------

def historial_cortes_por_plaza(mes=None, anio=None):
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT plazas.id, plazas.nombre, cortes.fecha_corte, cortes.id
        FROM cortes
        JOIN plazas ON cortes.plaza = plazas.id
    '''
    params = []

    if mes and anio:
        query += " WHERE strftime('%m', cortes.fecha_corte) = ? AND strftime('%Y', cortes.fecha_corte) = ?"
        params.extend([f'{int(mes):02d}', str(anio)])

    cursor.execute(query, params)
    datos = cursor.fetchall()
    conn.close()

    historial = {}
    for plaza_id, nombre, fecha, corte_id in datos:
        fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d-%m-%Y")
        if plaza_id not in historial:
            historial[plaza_id] = {'plaza': nombre, 'fechas': []}
        historial[plaza_id]['fechas'].append({'fecha': fecha_formateada, 'id': corte_id})

    return historial

def obtener_cortes_por_plaza(anio, mes=None):
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT plazas.nombre, COUNT(*) as cantidad
        FROM cortes
        JOIN plazas ON cortes.plaza = plazas.id
        WHERE strftime('%Y', fecha_corte) = ?
    '''
    params = [str(anio)]

    if mes:
        query += ' AND strftime(\'%m\', fecha_corte) = ?'
        params.append(f'{int(mes):02d}')

    query += ' GROUP BY plazas.nombre ORDER BY cantidad DESC'

    cursor.execute(query, params)
    resultados = [{'nombre': row[0], 'cantidad': row[1]} for row in cursor.fetchall()]
    conn.close()
    return resultados

def obtener_fechas_por_plaza(anio, mes=None):
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT plazas.nombre, cortes.fecha_corte
        FROM cortes
        JOIN plazas ON cortes.plaza = plazas.id
        WHERE strftime('%Y', fecha_corte) = ?
    '''
    params = [str(anio)]

    if mes is not None:
        query += ' AND strftime(\'%m\', fecha_corte) = ?'
        params.append(f'{int(mes):02d}')

    query += ' ORDER BY plazas.nombre, fecha_corte'

    cursor.execute(query, params)
    datos = cursor.fetchall()
    conn.close()

    plazas = {}
    for nombre, fecha in datos:
        fecha_str = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d-%m-%Y")
        plazas.setdefault(nombre, []).append(fecha_str)

    ordenado = sorted(plazas.items(), key=lambda x: len(x[1]), reverse=True)
    return [{"nombre": nombre, "fechas": fechas} for nombre, fechas in ordenado]


def formatear_fecha(fecha_str):
    try:
        return datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return fecha_str or "—"

def buscar_arreglos_realizados_por_plaza(nombre_plaza=None, anio=None, mes=None):
    with conectar_db() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT a.id, p.nombre, a.tarea, a.fecha_ingreso, a.fecha_realizacion, a.personas_involucradas, a.relevadores
            FROM arreglos a
            JOIN plazas p ON a.plaza_id = p.id
            WHERE a.realizada = 1
        '''
        params = []

        if nombre_plaza:
            query += ' AND p.nombre LIKE ?'
            params.append(f'%{nombre_plaza}%')

        if anio and mes:
            query += ' AND strftime("%Y", a.fecha_realizacion) = ? AND strftime("%m", a.fecha_realizacion) = ?'
            params.extend([str(anio), f'{int(mes):02d}'])

        cursor.execute(query, params)
        resultados = cursor.fetchall()

        return [{
            'id': r[0],
            'nombre': r[1],
            'tareas': r[2],
            'fecha_ingreso': formatear_fecha(r[3]),
            'fecha_realizacion': formatear_fecha(r[4]),
            'personas': r[5],
            'relevadores': r[6]
        } for r in resultados]

def generar_token(usuario_id):
    return base64.urlsafe_b64encode(str(usuario_id).encode()).decode()

def decodificar_token(token):
    try:
        return int(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception:
        return None
