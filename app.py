from flask import Flask, render_template, request, redirect, session, send_file, url_for, session, Request, Response, make_response
from collections import Counter
from datetime import datetime
from datetime import timedelta
from io import BytesIO
import re
import os
from collections import defaultdict
from config import SECRET_KEY
import io, sqlite3, csv
import pandas as pd
import base64
from proyecto import (
    crear_base_de_datos,
    agregar_plaza,
    obtener_arreglos_pendientes,
    dias_desde_ultimo_corte,
    registrar_corte,
    plazas_sin_corte,
    registrar_usuario,
    verificar_usuario,
    conectar_db,
    buscar_arreglos_realizados_por_plaza,
    obtener_plazas,
    obtener_nombres_plaza,
    obtener_usuario_id,
    historial_cortes_por_plaza,
    buscar_plazas_por_nombre,
    exportar_cortes_a_excel,
    obtener_cortes_por_plaza,
    buscar_arreglos_por_plaza,
    cortes_vencidos,
    ignorar_alerta,
    eliminar_plaza,
    eliminar_corte,
    eliminar_arreglo,
    actualizar_tabla_plazas_agregar_fecha_creacion,
    registrar_solicitud_arreglo,
    marcar_tarea_realizada,
    obtener_arreglos_realizados,
    solo_servicios,
    migrar_tabla_arreglos_a_tareas_individuales,
    obtener_arreglos_con_alerta,
    omitir_alerta_arreglo,
    obtener_fechas_por_plaza
    
)

def migrar_alertas_ignoradas_agregar_nombre():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(alertas_ignoradas)")
    columnas = [col[1] for col in cursor.fetchall()]
    if "nombre" not in columnas:
        print("🛠 Agregando columna 'nombre' a alertas_ignoradas...")
        cursor.execute("ALTER TABLE alertas_ignoradas ADD COLUMN nombre TEXT")
        conn.commit()
    else:
        print("✅ La columna 'nombre' ya existe en alertas_ignoradas.")

    conn.close()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_super_segura_municipalidad')

crear_base_de_datos()
actualizar_tabla_plazas_agregar_fecha_creacion()
migrar_tabla_arreglos_a_tareas_individuales()
migrar_alertas_ignoradas_agregar_nombre()


# -------------------- PLAZAS --------------------

@app.route('/nueva-plaza', methods=['GET', 'POST'])
@solo_servicios
def nueva_plaza():
    mensaje = None

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        ubicacion = request.form.get('ubicacion', '').strip()
        usuario_id = session.get('usuario_id')

        print("📥 Intentando registrar plaza:")
        print("🔹 Nombre:", nombre)
        print("🔹 Ubicación:", ubicacion)
        print("🔹 Usuario ID:", usuario_id)

        try:
            if not nombre or not ubicacion or not usuario_id:
                raise ValueError("Campos incompletos o sesión inválida")

            conn = conectar_db()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO plazas (nombre, ubicacion, usuario_id, activa)
                VALUES (?, ?, ?, 1)
            ''', (nombre, ubicacion, usuario_id))

            conn.commit()
            conn.close()

            print("✅ Plaza registrada correctamente.")
            return redirect('/nueva-plaza?registrado=1')

        except Exception as e:
            print("⚠️ Error al registrar plaza:", e)
            mensaje = "❌ Error interno al registrar la plaza. Verificá los datos o la sesión."

    if request.args.get('registrado') == '1':
        mensaje = "✅ Plaza registrada correctamente."

    return render_template('nueva_plaza.html', mensaje=mensaje)


@app.route('/posponer-alerta', methods=['POST'])
def posponer_alerta():
    from datetime import datetime, timedelta
    try:
        nombre = request.form['nombre']
        tipo_alerta = request.form['tipo_alerta']
        usuario_id = session.get('usuario_id')
        ignorar_hasta = (datetime.today() + timedelta(days=3)).strftime('%Y-%m-%d')

        conn = conectar_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Buscar plaza_id por nombre
        cursor.execute("SELECT id FROM plazas WHERE LOWER(nombre) = ?", (nombre.lower(),))
        resultado = cursor.fetchone()

        if resultado:
            plaza_id = resultado['id']
            cursor.execute('''
                INSERT INTO alertas_ignoradas (usuario_id, plaza_id, tipo_alerta, ignorar_hasta)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(usuario_id, tipo_alerta, plaza_id, nombre_plaza)
                DO UPDATE SET ignorar_hasta = excluded.ignorar_hasta
            ''', (usuario_id, plaza_id, tipo_alerta, ignorar_hasta))
        else:
            # Si no hay plaza registrada, ignorar por nombre
            cursor.execute('''
                INSERT INTO alertas_ignoradas (usuario_id, plaza_id, nombre_plaza, tipo_alerta, ignorar_hasta)
                VALUES (?, NULL, ?, ?, ?)
                ON CONFLICT(usuario_id, tipo_alerta, plaza_id, nombre_plaza)
                DO UPDATE SET ignorar_hasta = excluded.ignorar_hasta
            ''', (usuario_id, nombre, tipo_alerta, ignorar_hasta))

        conn.commit()
        conn.close()
        return redirect('/')
    except Exception as e:
        print(f"⚠️ Error al posponer alerta: {e}")
        return "Error interno", 500


# -------------------- CORTES --------------------

@app.route('/registrar-corte', methods=['GET', 'POST'])
@solo_servicios
def registrar_corte_view():
    mensaje = None

    if request.method == 'POST':
        try:
            nombre = request.form['nombre'].strip()
            ubicacion = request.form['ubicacion'].strip()
            tipo = request.form['tipo'].strip()
            fecha = request.form['fecha'].strip()

            if not nombre or not tipo or not fecha:
                mensaje = "❌ Todos los campos son obligatorios."
                raise ValueError("Campos incompletos")

            conn = conectar_db()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO cortes (nombre, ubicacion, tipo, fecha_corte)
                VALUES (?, ?, ?, ?)
            ''', (nombre, ubicacion, tipo, fecha))

            conn.commit()
            conn.close()
            return redirect('/registrar-corte?registrado=1')

        except Exception as e:
            print("⚠️ Error al registrar corte:", e)
            mensaje = "❌ Error interno al registrar el corte."

    if request.args.get('registrado') == '1':
        mensaje = "✅ Corte registrado correctamente."

    return render_template('registrar_corte.html', mensaje=mensaje)

# -------------------- ARREGLOS --------------------

@app.route('/registrar-arreglo', methods=['GET', 'POST'])
def registrar_arreglo_view():
    if 'usuario_id' not in session:
        return redirect('/login')

    mensaje = None

    if request.method == 'POST':
        nombre = request.form['nombre']
        tareas = request.form['tareas']
        fecha_ingreso = request.form['fecha_ingreso']
        relevadores = request.form['relevadores']
        registrar_solicitud_arreglo(nombre, tareas, fecha_ingreso, relevadores)
        return redirect('/registrar-arreglo?registrado=1')

    if request.args.get('registrado') == '1':
        mensaje = "✅ Arreglo registrado correctamente."

    return render_template('registrar_arreglo.html', mensaje=mensaje)

def formatear_fecha(fecha_str):
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
    meses = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    return f"{fecha.day} de {meses[fecha.month]} de {fecha.year}"

@app.route('/plazas-cortadas')
def plazas_cortadas_view():
    conn = conectar_db()
    cursor = conn.cursor()

    mes = request.args.get('mes')  # formato '2025-09'
    query = '''
        SELECT nombre, ubicacion, fecha_corte
        FROM cortes
        WHERE tipo = 'plaza'
    '''
    params = []

    if mes:
        query += " AND strftime('%Y-%m', fecha_corte) = ?"
        params.append(mes)

    query += " ORDER BY nombre, fecha_corte DESC"

    cursor.execute(query, params)
    cortes_raw = cursor.fetchall()
    conn.close()

    # Agrupar por nombre
    agrupados = defaultdict(list)
    for nombre, ubicacion, fecha in cortes_raw:
        agrupados[nombre].append({
            'ubicacion': ubicacion,
            'fecha_corte': fecha_corta(fecha)
        })

    return render_template('plazas_cortadas.html', cortes_agrupados=agrupados, mes=mes)



def fecha_corta(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
        return fecha.strftime("%d/%m/%Y")
    except Exception:
        return fecha_str


@app.route('/descargar-cortes')
def descargar_cortes():
    mes = request.args.get('mes')  # formato '2025-09'
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT nombre, ubicacion, fecha_corte
        FROM cortes
        WHERE tipo = 'plaza'
    '''
    params = []

    if mes:
        query += " AND strftime('%Y-%m', fecha_corte) = ?"
        params.append(mes)

    query += " ORDER BY nombre, fecha_corte DESC"

    cursor.execute(query, params)
    cortes_raw = cursor.fetchall()
    conn.close()

    # Agrupar por nombre
    from collections import defaultdict
    agrupados = defaultdict(list)
    for nombre, ubicacion, fecha in cortes_raw:
        agrupados[nombre].append({
            'ubicacion': ubicacion,
            'fecha': fecha_corta(fecha)
        })

    # Preparar datos para Excel
    filas = []
    for nombre, lista in agrupados.items():
        fechas = ', '.join([c['fecha'] for c in lista])
        ubicacion = lista[0]['ubicacion']
        filas.append({
            'Plaza': nombre,
            'Ubicación': ubicacion,
            'Fechas de corte': fechas
        })

    df = pd.DataFrame(filas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Cortes')
    output.seek(0)

    nombre_archivo = f'cortes_plaza_{mes or "completo"}.xlsx'
    return send_file(output, download_name=nombre_archivo, as_attachment=True)




@app.route('/arreglos-pendientes')
def arreglos_pendientes():
    mes_anio = request.args.get('mes_anio', '')
    plaza = request.args.get('plaza', '')

    if mes_anio and '-' in mes_anio:
        anio, mes = mes_anio.split('-')
    else:
        hoy = datetime.today()
        anio, mes = str(hoy.year), f"{hoy.month:02d}"
        mes_anio = f"{anio}-{mes}"

    arreglos = obtener_arreglos_pendientes(anio, mes, plaza)

    return render_template('arreglos_pendientes.html',
                           arreglos=arreglos,
                           mes_anio=mes_anio,
                           plaza=plaza)


# -------------------- ARREGLOS (actualización de tareas) --------------------

@app.route('/registrar-realizacion', methods=['POST'])
def registrar_realizacion():
    id_arreglo = request.form.get('id_arreglo')
    fecha = request.form.get('fecha_realizacion')
    personas = request.form.get('personas_involucradas')

    # 🔄 nuevos filtros para redirigir luego
    plaza = request.form.get('plaza')
    mes_anio = request.form.get('mes_anio')

    if not id_arreglo or not fecha or not personas:
        return redirect(url_for('arreglos_pendientes', plaza=plaza, mes_anio=mes_anio))

    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE arreglos
            SET realizada = 1,
                fecha_realizacion = ?,
                personas_involucradas = ?
            WHERE id = ?
        ''', (fecha, personas, id_arreglo))
        conn.commit()

    # ✅ Redirige de nuevo con mensaje de éxito
    return redirect(url_for('arreglos_pendientes', plaza=plaza, mes_anio=mes_anio, hecho='1'))

@app.route('/eliminar-arreglo/<int:arreglo_id>', methods=['POST'])
def eliminar_arreglo(arreglo_id):
    if 'usuario_id' not in session:
        return redirect('/login')

    # Podés agregar verificación adicional acá si querés asegurarte de que el usuario tenga permisos

    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM arreglos WHERE id = ?', (arreglo_id,))
        conn.commit()

    # Redirige de nuevo a arreglos pendientes con mensaje
    mes_anio = request.form.get('mes_anio')
    plaza = request.form.get('plaza')
    return redirect(url_for('arreglos_pendientes', mes_anio=mes_anio, plaza=plaza, eliminado='1'))

# -------------------- AUTENTICACIÓN --------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            return render_template('login.html', error="Completa todos los campos.")

        user = verificar_usuario(username, password)

        if user:
            session['usuario'] = user['username']
            session['rol'] = user['rol']
            session['usuario_id'] = obtener_usuario_id(user['username'])  # 🧠 ¡Esta línea es clave!

            if user['rol'] == 'servicios':
                return redirect(url_for('inicio'))
            elif user['rol'] == 'secretaria':
                return redirect(url_for('registrar_arreglo_view'))

        return render_template('login.html', error="Credenciales incorrectas.")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rol = request.form.get('rol')

        # Validar longitud mínima
        if len(username) < 6 or len(password) < 6:
            return render_template('register.html', error="El nombre de usuario y la contraseña deben tener al menos 6 caracteres")

        # Validar formato de email
        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, username):
            return render_template('register.html', error="Ingresá un correo electrónico válido")

        # Validar rol
        if rol not in ['servicios', 'secretaria']:
            return render_template('register.html', error="Seleccioná un rol válido")

        # Intentar registrar usuario
        if registrar_usuario(username, password, rol):
            return render_template('register.html', success="✅ Cuenta creada correctamente. Ya podés iniciar sesión.")
        else:
            return render_template('register.html', error="Ese correo ya está registrado")
        
    return render_template('register.html')




@app.route('/logout')
def logout():
    session.pop('usuario', None)
    session.pop('usuario_id', None)
    session.pop('rol', None)  
    return redirect('/login')

# -------------------- CONSULTA DE PLAZAS --------------------

@app.route('/mis-plazas', methods=['GET', 'POST'])
@solo_servicios
def mis_plazas():
    if 'usuario_id' not in session:
        return redirect('/login')

    texto = request.form.get('busqueda', '').strip() if request.method == 'POST' else ''
    usuario_id = session['usuario_id']

    conn = conectar_db()
    cursor = conn.cursor()
    if texto:
        cursor.execute('''
            SELECT id, nombre, ubicacion
            FROM plazas
            WHERE usuario_id = ? AND activa = 1 AND nombre LIKE ?
        ''', (usuario_id, f'%{texto}%'))
    else:
        cursor.execute('''
            SELECT id, nombre, ubicacion
            FROM plazas
            WHERE usuario_id = ? AND activa = 1
        ''', (usuario_id,))
    plazas = cursor.fetchall()
    conn.close()

    return render_template('mis_plazas.html', plazas=plazas, texto=texto)


# -------------------- EXPORTACIÓN DE DATOS --------------------

@app.route('/exportar_cortes')
@solo_servicios
def exportar_cortes():
    mes_anio  = request.args.get('mes_anio', '').strip()
    plaza_id  = request.args.get('plaza_id', None)

    # --- Armo filtros SQL ---
    filtros, params = [], []
    if mes_anio:
        filtros.append("strftime('%Y-%m', fecha_corte) = ?")
        params.append(mes_anio)
    if plaza_id:
        filtros.append("plaza = ?")
        params.append(plaza_id)
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ''

    # --- Traigo datos individuales ---
    sql = f"""
      SELECT p.nombre AS Plaza,
             c.fecha_corte AS Fecha
      FROM cortes c
      JOIN plazas p ON c.plaza = p.id
      {where}
      ORDER BY p.nombre, c.fecha_corte
    """
    conn = sqlite3.connect('database.db')
    df   = pd.read_sql_query(sql, conn, params=params)
    conn.close()

    if df.empty:
        return "No hay cortes para exportar.", 204

    # --- Parseo la fecha y agrupo por plaza ---
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%Y-%m-%d')
    resumen = (
        df
        .groupby('Plaza')
        .agg(
          Cantidad=('Fecha', 'count'),
          Fechas=('Fecha', lambda x: ', '.join(x.dt.strftime('%d-%m-%Y')))
        )
        .reset_index()
    )

    # --- Genero el Excel en memoria ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        resumen.to_excel(writer,
                         sheet_name='Cortes',
                         index=False,
                         startrow=1)  # dejamos la fila 0 para header formateado

        wb = writer.book
        ws = writer.sheets['Cortes']

        # Formatos
        header_fmt = wb.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1,
            'align': 'center'
        })
        text_fmt = wb.add_format({'border': 1})

        # Escribo header en la fila 0
        for col_num, value in enumerate(resumen.columns):
            ws.write(0, col_num, value.replace('_', ' '), header_fmt)

        # Ajusto anchos: Plaza | Cantidad | Fechas
        ws.set_column(0, 0, 25, text_fmt)
        ws.set_column(1, 1, 12, text_fmt)
        ws.set_column(2, 2, 50, text_fmt)

        # Fijo la fila del header
        ws.freeze_panes(1, 0)

    output.seek(0)

    # Nombre dinámico de archivo
    nombre = 'cortes'
    if mes_anio:
        nombre += f"_{mes_anio.replace('-', '')}"
    if plaza_id:
        nombre += f"_plaza{plaza_id}"
    nombre += '.xlsx'

    return send_file(
        output,
        download_name=nombre,
        as_attachment=True,
        mimetype=(
          'application/'
          'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    )



# -------------------- GRÁFICO ESTADÍSTICO --------------------

@app.route('/grafico', methods=['GET'])
@solo_servicios
def ver_grafico():
    if 'usuario_id' not in session:
        return redirect('/login')

    # Capturo mes/año opcional
    mes_anio = request.args.get('mes_anio', '')
    mes = anio = None
    if mes_anio:
        try:
            anio, mes = map(int, mes_anio.split('-'))
        except ValueError:
            mes = anio = None

    # Traigo todos los cortes de ese mes/año agrupados por nombre
    conn = conectar_db()
    cursor = conn.cursor()

    query = '''
        SELECT nombre, COUNT(*) as cantidad
        FROM cortes
    '''
    params = []

    if mes and anio:
        query += ' WHERE strftime("%m", fecha_corte) = ? AND strftime("%Y", fecha_corte) = ?'
        params = [f"{mes:02d}", str(anio)]

    query += ' GROUP BY nombre ORDER BY cantidad DESC'

    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()

    # Genero lista combinada [(nombre, cantidad), ...]
    combinado = [(fila[0], fila[1]) for fila in resultados]

    return render_template(
        'grafico.html',
        combinado=combinado,
        mes_anio=mes_anio
    )

# -------------------- ALERTAS --------------------

@app.route('/ignorar-alerta', methods=['POST'])
def ignorar_alerta_route():
    if 'usuario_id' not in session:
        return redirect('/login')
    usuario_id = session['usuario_id']
    plaza_id = int(request.form['plaza_id'])
    tipo_alerta = request.form['tipo_alerta']
    ignorar_alerta(usuario_id, plaza_id, tipo_alerta)
    return redirect('/')

@app.route('/omitir-alerta-arreglo', methods=['POST'])
def omitir_alerta_arreglo_route():
    if 'usuario_id' not in session:
        return redirect('/login')
    arreglo_id = int(request.form['arreglo_id'])
    omitir_alerta_arreglo(arreglo_id, session['usuario_id'])
    return redirect('/')

# -------------------- ELIMINACIONES --------------------

@app.route('/eliminar-plaza', methods=['POST'])
@solo_servicios
def eliminar_plaza_route():
    if 'usuario_id' not in session:
        return redirect('/login')
    plaza_id = int(request.form['plaza_id'])
    eliminar_plaza(plaza_id)
    return redirect('/mis-plazas')

@app.route('/eliminar-corte', methods=['POST'])
@solo_servicios
def eliminar_corte_route():
    if 'usuario_id' not in session:
        return redirect('/login')
    corte_id = int(request.form['corte_id'])
    eliminar_corte(corte_id)
    return redirect('/mis-plazas')

@app.route('/eliminar-arreglo', methods=['POST'])
def eliminar_arreglo_route():
    if 'usuario_id' not in session:
        return redirect('/login')
    arreglo_id = int(request.form['arreglo_id'])
    eliminar_arreglo(arreglo_id)
    return redirect('/arreglos-pendientes')
# --------------------------------------------------------------------------------------
# RUTAS MODIFICADAS PARA 'VER ARREGLOS REALIZADOS'
# --------------------------------------------------------------------------------------

@app.route('/arreglos-realizados')
def ver_arreglos_realizados():
    if 'usuario_id' not in session:
        return redirect('/login')

    plaza = request.args.get("plaza", "").strip()
    mes_anio = request.args.get("mes_anio", "").strip()

    anio = mes = None
    if mes_anio:
        try:
            anio, mes = mes_anio.split("-")
        except ValueError:
            pass

    # ⬇️ Acá va la línea clave
    arreglos = buscar_arreglos_realizados_por_plaza(nombre_plaza=plaza, anio=anio, mes=mes)

    return render_template("arreglos_realizados.html",
                           arreglos=arreglos,
                           mes_anio=mes_anio,
                           plaza=plaza)

@app.route('/descargar-arreglos')
def descargar_arreglos_excel():
    plaza = request.args.get('plaza', '').strip()
    mes = request.args.get('mes', '').strip()

    conn = conectar_db()
    cursor = conn.cursor()

    # JOIN con plazas para obtener el nombre real de la plaza
    query = '''
        SELECT plazas.nombre AS nombre_plaza,
               arreglos.tarea,
               arreglos.relevadores,
               arreglos.fecha_ingreso,
               arreglos.fecha_realizacion,
               arreglos.personas_involucradas
        FROM arreglos
        JOIN plazas ON arreglos.plaza_id = plazas.id
        WHERE arreglos.realizada = 1
    '''
    params = []

    if plaza:
        query += ' AND LOWER(plazas.nombre) LIKE ?'
        params.append(f'%{plaza.lower()}%')

    if mes:
        query += ' AND strftime("%Y-%m", arreglos.fecha_realizacion) = ?'
        params.append(mes)

    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()

    if not resultados:
        return "No hay datos para descargar en Excel con los filtros aplicados.", 204

    columnas = ['Plaza', 'Tarea', 'Relevadores', 'Fecha de Pedido', 'Fecha de Realización', 'Personas Involucradas']
    df = pd.DataFrame(resultados, columns=columnas)

    if 'Fecha de Pedido' in df.columns:
        df['Fecha de Pedido'] = pd.to_datetime(df['Fecha de Pedido']).dt.strftime('%d-%m-%Y')
    if 'Fecha de Realización' in df.columns:
        df['Fecha de Realización'] = pd.to_datetime(df['Fecha de Realización']).dt.strftime('%d-%m-%Y')

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Arreglos Realizados')

    output.seek(0)
    return send_file(
        output,
        download_name='arreglos_realizados.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )



@app.route('/')
@solo_servicios
def inicio():
    usuario_id = session.get('usuario_id')
    rol = session.get('rol')

    # Si no hay sesión o el rol no es servicios, redirigir al login
    if not usuario_id or rol != 'servicios':
        return redirect('/login')

    # Detectar cortes vencidos (15 días)
    alertas_cortes = cortes_vencidos(usuario_id)

    # Detectar arreglos pendientes (más de 13 días)
    alertas_arreglos = obtener_arreglos_con_alerta(usuario_id)

    # Días desde el último corte por plaza
    plazas_sin_corte = dias_desde_ultimo_corte()

    return render_template(
        'index.html',
        alertas_cortes=alertas_cortes,
        alertas_arreglos=alertas_arreglos,
        plazas_sin_corte=plazas_sin_corte
    )





if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

