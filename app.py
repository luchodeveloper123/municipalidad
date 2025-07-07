from flask import Flask, render_template, request, redirect, session, send_file, url_for, session, Request, Response
from collections import Counter
from io import BytesIO
import re
import os
from config import SECRET_KEY
import io, sqlite3, csv
import pandas as pd
import base64
from datetime import datetime
from proyecto import (
    crear_base_de_datos,
    agregar_plaza,
    registrar_corte,
    plazas_sin_corte,
    registrar_usuario,
    verificar_usuario,
    conectar_db,
    decodificar_token,
    buscar_arreglos_realizados_por_plaza,
    obtener_plazas,
    obtener_nombres_plaza,
    obtener_usuario_id,
    historial_cortes_por_plaza,
    buscar_plazas_por_nombre,
    exportar_cortes_a_excel,
    obtener_cortes_por_plaza,
    buscar_arreglos_por_plaza,
    enviar_correo_verificacion,
    ignorar_alerta,
    eliminar_plaza,
    eliminar_corte,
    eliminar_arreglo,
    actualizar_tabla_plazas_agregar_fecha_creacion,
    obtener_arreglos_pendientes,
    registrar_solicitud_arreglo,
    marcar_tarea_realizada,
    obtener_arreglos_realizados,
    solo_servicios,
    migrar_tabla_arreglos_a_tareas_individuales,
    obtener_arreglos_con_alerta,
    omitir_alerta_arreglo,
    obtener_fechas_por_plaza
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

crear_base_de_datos()
actualizar_tabla_plazas_agregar_fecha_creacion()
migrar_tabla_arreglos_a_tareas_individuales()

# -------------------- PLAZAS --------------------

@app.route('/nueva-plaza', methods=['GET', 'POST'])
@solo_servicios
def nueva_plaza():
    if 'usuario_id' not in session:
        return redirect('/login')

    mensaje = None

    if request.method == 'POST':
        nombre = request.form['nombre']
        ubicacion = request.form['ubicacion']
        usuario_id = session['usuario_id']
        agregar_plaza(nombre, ubicacion, usuario_id)
        return redirect('/nueva-plaza?creada=1')

    if request.args.get('creada') == '1':
        mensaje = "✅ Plaza registrada con éxito."

    return render_template('nueva_plaza.html', mensaje=mensaje)


# -------------------- CORTES --------------------

@app.route('/registrar-corte', methods=['GET', 'POST'])
@solo_servicios
def registrar_corte_view():
    if 'usuario_id' not in session:
        return redirect('/login')

    mensaje = None

    if request.method == 'POST':
        nombre = request.form['nombre']
        fecha = request.form['fecha']
        registrar_corte(nombre, fecha)
        return redirect('/registrar-corte?registrado=1')

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


@app.route('/arreglos-pendientes', methods=['GET', 'POST'])
def arreglos_pendientes():
    # Obtener filtros del formulario o parámetros
    mes_anio = request.args.get('mes_anio', '').strip()
    plaza_filtro = request.args.get('plaza', '').strip().lower()

    # Verificar si se debe mostrar mensaje de éxito
    mensaje = None
    if request.args.get('hecho') == '1':
        mensaje = "✅ Arreglo marcado como finalizado."

    # Validar mes y año, o usar fecha actual
    if mes_anio and '-' in mes_anio:
        anio, mes = mes_anio.split('-')
    else:
        hoy = datetime.today()
        anio, mes = str(hoy.year), f"{hoy.month:02d}"
        mes_anio = f"{anio}-{mes}"

    # Conectar a la base
    conn = sqlite3.connect('database.db')  # Asegurate de usar el nombre real de tu base
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Consulta de arreglos pendientes filtrados
    query = '''
        SELECT a.id,
               a.tarea AS descripcion,
               a.relevadores,
               strftime('%d/%m/%Y', a.fecha_ingreso) AS fecha_ingreso,
               p.nombre AS plaza
        FROM arreglos a
        JOIN plazas p ON a.plaza_id = p.id
        WHERE a.realizada = 0
          AND strftime('%Y-%m', a.fecha_ingreso) = ?
          AND LOWER(p.nombre) LIKE ?
        ORDER BY a.fecha_ingreso DESC
    '''
    cursor.execute(query, (mes_anio, f'%{plaza_filtro}%'))
    arreglos = cursor.fetchall()

    # Lista de plazas (por si las usás en filtros)
    cursor.execute('SELECT id, nombre FROM plazas ORDER BY nombre')
    plazas = cursor.fetchall()

    conn.close()

    return render_template(
        'arreglos_pendientes.html',
        arreglos=arreglos,
        mes_anio=mes_anio,
        anio=anio,
        mes=mes,
        plazas=plazas,
        plaza=plaza_filtro,
        mensaje=mensaje
    )

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

@app.route('/verificar-email')
def verificar_email():
    token = request.args.get('token')
    user_id = decodificar_token(token)

    if user_id:
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET verificado = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return render_template('verificado.html')  # Página que veremos en el navegador
    else:
        return "Token inválido o expirado", 400


# -------------------- AUTENTICACIÓN --------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        usuario = verificar_usuario(username, password)

        if usuario:
            if usuario['verificado'] != 1:
                return render_template('login.html', error="📩 Primero tenés que verificar tu correo para poder iniciar sesión.")

            session['usuario'] = username
            session['usuario_id'] = usuario['id']
            session['rol'] = usuario['rol']
            return redirect('/')

        return render_template('login.html', error="Usuario o contraseña incorrectos")

    return render_template('login.html')

def generar_token(usuario_id):
    return base64.urlsafe_b64encode(str(usuario_id).encode()).decode()

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

        # Registrar usuario
        if registrar_usuario(username, password, rol):
            user_id = obtener_usuario_id(username)
            token = generar_token(user_id)
            link = f"http://localhost:5000/verificar-email?token={token}"

            if enviar_correo_verificacion(username, link):
                return render_template('register.html', error="✅ Cuenta creada. Revisá tu correo para activarla.")
            else:
                return render_template('register.html', error="⚠️ Cuenta creada pero no se pudo enviar el correo de activación.")
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

    texto = ''
    mes_anio = ''
    mes = anio = None

    # Captura de filtros
    if request.method == 'POST':
        texto = request.form.get('busqueda', '').strip()
        mes_anio = request.form.get('mes_anio')

    # Parsear mes y año
    if mes_anio:
        try:
            anio, mes = map(int, mes_anio.split('-'))
        except ValueError:
            mes = anio = None

    # Traer todas las plazas según búsqueda
    raw = buscar_plazas_por_nombre(texto)
    if raw and isinstance(raw[0], dict):
        resultados = [(r['id'], r['nombre'], r['ubicacion']) for r in raw]
    else:
        resultados = raw

    # Desduplicar por ID de plaza
    plazas = []
    vistos = set()
    for pid, nombre, ubicacion in resultados:
        if pid not in vistos:
            vistos.add(pid)
            plazas.append((pid, nombre, ubicacion))

    # Obtener cortes filtrados por mes/año
    historial = historial_cortes_por_plaza(mes=mes, anio=anio)
    plaza_ids = {pid for pid, _, _ in plazas}
    historial_filtrado = {
        pid: datos
        for pid, datos in historial.items()
        if pid in plaza_ids
    }

    # Exportar a Excel si se solicitó
    if request.method == 'POST' and request.form.get('descargar') == 'excel':
        filas = []
        for pid, nombre, ubicacion in plazas:
            fechas = historial_filtrado.get(pid, {}).get('fechas', [])
            dias = len(fechas)
            fechas_str = ', '.join(f['fecha'] for f in fechas)

            filas.append({
                'Plaza': nombre,
                'Ubicación': ubicacion,
                'Días de Corte': dias,
                'Fechas': fechas_str
            })

        df = pd.DataFrame(filas)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Cortes')
        output.seek(0)

        filename = f'cortes_{mes or "todos"}-{anio or "año"}.xlsx'
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    # Renderizar la plantilla con todas las plazas y los cortes del período
    return render_template(
        'mis_plazas.html',
        plazas=plazas,
        historial=historial_filtrado,
        texto=texto,
        mes_anio=mes_anio
    )

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

    # Traigo todos los cortes de ese mes/año
    historial = historial_cortes_por_plaza(mes=mes, anio=anio)
    # historial = { plaza_id: { 'plaza':nombre, 'fechas':[...], ... }, ... }

    # Construyo conteo de cortes por plaza
    cortes_por_plaza = {
        datos['plaza']: len(datos.get('fechas', []))
        for datos in historial.values()
    }
    # Elimino las que quedaron en 0 y ordeno de mayor a menor
    etiquetas, valores = zip(
        *sorted(
            ((plaza, cnt) for plaza, cnt in cortes_por_plaza.items() if cnt>0),
            key=lambda x: x[1],
            reverse=True
        )
    ) if cortes_por_plaza else ([],[])

    return render_template(
        'grafico.html',
        labels=list(etiquetas),
        data=list(valores),
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
def inicio():
    if 'usuario_id' not in session:
        return redirect('/login')

    alertas_cortes = plazas_sin_corte(session['usuario_id'])
    alertas_arreglos = obtener_arreglos_con_alerta(session['usuario_id'])

    return render_template(
        'index.html',
        alertas_cortes=alertas_cortes,
        alertas_arreglos=alertas_arreglos
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

