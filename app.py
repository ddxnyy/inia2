from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
from datetime import datetime, date
import calendar
import os
import logging
import traceback
from urllib.parse import urlparse

# Crear la aplicación Flask
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "3ee532f0a23be47d206fdcc690baf9b3")

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Función de conexión a base de datos
def get_db_connection():
   try:
       return mysql.connector.connect(
           host=os.environ.get('DB_HOST', 'sql211.infinityfree.com'),
            user=os.environ.get('DB_USER', 'if0_39708091'),
           password=os.environ.get('DB_PASSWORD', 'danydaniel1928'),
           database=os.environ.get('DB_NAME', 'if0_39708091_control_pagos'),
           port=int(os.environ.get('DB_PORT', 3306))
        )
   except mysql.connector.Error as err:
        if not os.environ.get('DEBUG', 'False').lower() in ['true', '1']:
           print("Error de conexión a la base de datos.")
        else:
            print(f"Error de conexión: {err}")
        return None

# Manejador de errores global
@app.errorhandler(Exception)
def handle_exception(e):
    # Loguear el error completo
    logger.error(f"Unhandled Exception: {str(e)}")
    logger.error(traceback.format_exc())
    
    # Respuesta de error detallada
    return jsonify({
        "error": "Internal Server Error",
        "message": str(e),
        "trace": traceback.format_exc()
    }), 500

# =========================
# AUTENTICACIÓN BÁSICA
# =========================
@app.before_request
def require_login():
    allowed = {"login", "static"}
    endpoint = request.endpoint or ""
    if endpoint in allowed:
        return
    if not session.get("admin_user"):
        return redirect(url_for("login"))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '')
        conn = get_db_connection()
        if conn is None:  # Verifica si la conexión es None
            return render_template('login.html', title='Login', login_error=True, error_message="No se pudo conectar a la base de datos.")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, usuario FROM admin WHERE usuario=%s AND contrasena=%s",
            (usuario, contrasena)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            session['admin_user'] = row['usuario']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', title='Login', login_error=True)
    return render_template('login.html', title='Login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# =========================
# FUNCIONES AUXILIARES
# =========================
def _as_date(value):
    if isinstance(value, date):
        return value
    if hasattr(value, 'date'):
        return value.date()
    return None

def _add_months(orig_date: date, months: int = 1) -> date:
    year = orig_date.year + ((orig_date.month - 1 + months) // 12)
    month = ((orig_date.month - 1 + months) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(orig_date.day, last_day)
    return date(year, month, day)

def obtener_contadores():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT fecha_pago FROM inquilinos")
    registros = cursor.fetchall()
    cursor.close()
    conn.close()

    hoy = datetime.now().date()
    verde = naranja = rojo = 0

    for reg in registros:
        fecha = _as_date(reg.get('fecha_pago'))
        if not fecha:
            continue
        dias = (fecha - hoy).days
        if dias > 3:
            verde += 1
        elif dias == 2:
            naranja += 1
        else:
            rojo += 1

    return verde, naranja, rojo

# =========================
# DASHBOARD
# =========================
@app.route('/')
def dashboard():
    verde, naranja, rojo = obtener_contadores()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT i.id_inquilino, i.fecha_pago, i.id_departamento,
               u.id_usuario, u.nombres, u.apellidos, u.telefono, u.dni,
               d.nombre AS nombre_departamento
        FROM inquilinos i
        JOIN departamentos d ON i.id_departamento = d.id_departamento
        JOIN usuarios u ON u.id_usuario = i.id_usuario
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    hoy = datetime.now().date()
    inquilinos = []
    for row in rows:
        fecha = _as_date(row.get('fecha_pago'))
        dias_restantes = (fecha - hoy).days if fecha else 0
        color = '#198754' if dias_restantes > 3 else ('#fd7e14' if dias_restantes == 2 else '#dc3545')
        inquilino = {**row, 'dias_restantes': dias_restantes, 'color': color}
        inquilinos.append(inquilino)

    inquilinos.sort(key=lambda x: x['dias_restantes'])

    return render_template(
        "dashboard.html",
        title="Dashboard",
        inquilinos=inquilinos,
        count_verde=verde,
        count_naranja=naranja,
        count_rojo=rojo
    )

# =========================
# CRUD INQUILINOS
# =========================
@app.route('/inquilinos')
def lista_inquilinos():
    verde, naranja, rojo = obtener_contadores()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT i.id_inquilino, i.fecha_pago, i.id_departamento,
               u.id_usuario, u.nombres, u.apellidos, u.telefono, u.dni,
               d.nombre AS nombre_departamento
        FROM inquilinos i
        JOIN departamentos d ON i.id_departamento = d.id_departamento
        JOIN usuarios u ON u.id_usuario = i.id_usuario
        """
    )
    inquilinos = cursor.fetchall()

    cursor.execute("SELECT * FROM departamentos")
    departamentos = cursor.fetchall()

    cursor.execute("SELECT * FROM usuarios ORDER BY apellidos, nombres")
    usuarios = cursor.fetchall()

    cursor.close()
    conn.close()

    hay_disponibles = any(d.get('estado') == 'Disponible' for d in departamentos)

    return render_template(
        "inquilinos.html",
        title="Inquilinos",
        inquilinos=inquilinos,
        departamentos=departamentos,
        usuarios=usuarios,
        hay_disponibles=hay_disponibles,
        count_verde=verde,
        count_naranja=naranja,
        count_rojo=rojo,
    )

@app.route('/inquilinos/agregar', methods=['POST'])
def agregar_inquilino():
    modo_usuario = request.form.get('modo_usuario', 'existente')

    conn = get_db_connection()
    cursor = conn.cursor()

    if modo_usuario == 'nuevo':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        telefono = request.form['telefono']
        dni = request.form['dni']
        cursor.execute(
            "INSERT INTO usuarios (nombres, apellidos, telefono, dni) VALUES (%s, %s, %s, %s)",
            (nombres, apellidos, telefono, dni)
        )
        id_usuario = cursor.lastrowid
    else:
        id_usuario = request.form['id_usuario']

    id_departamento = request.form['id_departamento']
    fecha_pago = request.form['fecha_pago']

    cursor.execute(
        """
        INSERT INTO inquilinos (id_usuario, id_departamento, fecha_pago)
        VALUES (%s, %s, %s)
        """,
        (id_usuario, id_departamento, fecha_pago)
    )
    # Marcar el departamento asignado como Ocupado
    cursor.execute(
        "UPDATE departamentos SET estado='Ocupado' WHERE id_departamento=%s",
        (id_departamento,)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_inquilinos'))

@app.route('/inquilinos/renovar/<int:id_inquilino>', methods=['POST'])
def renovar_inquilino(id_inquilino):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT fecha_pago FROM inquilinos WHERE id_inquilino=%s", (id_inquilino,))
    row = cursor.fetchone()
    hoy = datetime.now().date()
    fecha_actual = _as_date(row['fecha_pago']) if row and row.get('fecha_pago') else hoy
    nueva_fecha = _add_months(fecha_actual, 1)

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE inquilinos SET fecha_pago=%s WHERE id_inquilino=%s",
        (nueva_fecha, id_inquilino)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_inquilinos'))

@app.route('/inquilinos/editar/<int:id_inquilino>', methods=['POST'])
def editar_inquilino(id_inquilino):
    id_usuario = request.form['id_usuario']
    id_departamento_nuevo = request.form['id_departamento']
    fecha_pago = request.form['fecha_pago']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Obtener el departamento anterior
    cursor.execute("SELECT id_departamento FROM inquilinos WHERE id_inquilino=%s", (id_inquilino,))
    actual = cursor.fetchone()
    id_departamento_anterior = actual['id_departamento'] if actual else None

    # Actualizar inquilino
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE inquilinos
        SET id_usuario=%s, id_departamento=%s, fecha_pago=%s
        WHERE id_inquilino=%s
        """,
        (id_usuario, id_departamento_nuevo, fecha_pago, id_inquilino)
    )

    # Si cambió de departamento, liberar el anterior (si no tiene otro inquilino) y ocupar el nuevo
    if id_departamento_anterior and str(id_departamento_anterior) != str(id_departamento_nuevo):
        cursor.execute(
            """
            UPDATE departamentos d
            LEFT JOIN inquilinos i ON i.id_departamento = d.id_departamento
            SET d.estado = 'Disponible'
            WHERE d.id_departamento = %s AND i.id_inquilino IS NULL
            """,
            (id_departamento_anterior,)
        )
        cursor.execute(
            "UPDATE departamentos SET estado='Ocupado' WHERE id_departamento=%s",
            (id_departamento_nuevo,)
        )

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_inquilinos'))

@app.route('/inquilinos/eliminar/<int:id_inquilino>', methods=['POST'])
def eliminar_inquilino(id_inquilino):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Obtener el departamento antes de eliminar
    cursor.execute("SELECT id_departamento FROM inquilinos WHERE id_inquilino=%s", (id_inquilino,))
    row = cursor.fetchone()
    id_departamento = row['id_departamento'] if row else None

    # Eliminar inquilino
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inquilinos WHERE id_inquilino=%s", (id_inquilino,))

    # Liberar departamento si quedó sin inquilinos
    if id_departamento:
        cursor.execute(
            """
            UPDATE departamentos d
            LEFT JOIN inquilinos i ON i.id_departamento = d.id_departamento
            SET d.estado = 'Disponible'
            WHERE d.id_departamento = %s AND i.id_inquilino IS NULL
            """,
            (id_departamento,)
        )

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_inquilinos'))

# =========================
# CRUD USUARIOS
# =========================
@app.route('/usuarios')
def lista_usuarios():
    verde, naranja, rojo = obtener_contadores()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios ORDER BY apellidos, nombres")
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "usuarios.html",
        title="Usuarios",
        usuarios=usuarios,
        count_verde=verde,
        count_naranja=naranja,
        count_rojo=rojo,
    )

@app.route('/usuarios/agregar', methods=['POST'])
def agregar_usuario():
    nombres = request.form['nombres']
    apellidos = request.form['apellidos']
    telefono = request.form['telefono']
    dni = request.form['dni']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usuarios (nombres, apellidos, telefono, dni) VALUES (%s, %s, %s, %s)",
        (nombres, apellidos, telefono, dni)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_usuarios'))

@app.route('/usuarios/editar/<int:id_usuario>', methods=['POST'])
def editar_usuario(id_usuario):
    nombres = request.form['nombres']
    apellidos = request.form['apellidos']
    telefono = request.form['telefono']
    dni = request.form['dni']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET nombres=%s, apellidos=%s, telefono=%s, dni=%s
        WHERE id_usuario=%s
        """,
        (nombres, apellidos, telefono, dni, id_usuario)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_usuarios'))

@app.route('/usuarios/eliminar/<int:id_usuario>', methods=['POST'])
def eliminar_usuario(id_usuario):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Evitar borrar si está referenciado por un inquilino
    cursor.execute("SELECT COUNT(*) FROM inquilinos WHERE id_usuario=%s", (id_usuario,))
    (count_ref,) = cursor.fetchone()
    if count_ref and count_ref > 0:
        cursor.close()
        conn.close()
        return redirect(url_for('lista_usuarios'))

    cursor.execute("DELETE FROM usuarios WHERE id_usuario=%s", (id_usuario,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_usuarios'))

# =========================
# CRUD DEPARTAMENTOS
# =========================
@app.route('/departamentos')
def lista_departamentos():
    verde, naranja, rojo = obtener_contadores()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM departamentos")
    departamentos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "departamentos.html",
        title="Departamentos",
        departamentos=departamentos,
        count_verde=verde,
        count_naranja=naranja,
        count_rojo=rojo,
    )

@app.route('/departamentos/agregar', methods=['POST'])
def agregar_departamento():
    nombre = request.form['nombre']
    piso = request.form['piso']
    numero = request.form.get('numero')
    direccion = request.form['direccion']
    estado = request.form['estado']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO departamentos (nombre, piso, numero, direccion, estado) VALUES (%s, %s, %s, %s, %s)",
        (nombre, piso, numero, direccion, estado)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_departamentos'))

@app.route('/departamentos/editar/<int:id_departamento>', methods=['POST'])
def editar_departamento(id_departamento):
    nombre = request.form['nombre']
    piso = request.form['piso']
    numero = request.form.get('numero')
    direccion = request.form['direccion']
    estado = request.form['estado']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE departamentos
        SET nombre=%s, piso=%s, numero=%s, direccion=%s, estado=%s
        WHERE id_departamento=%s
        """,
        (nombre, piso, numero, direccion, estado, id_departamento)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_departamentos'))

@app.route('/departamentos/eliminar/<int:id_departamento>', methods=['POST'])
def eliminar_departamento(id_departamento):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM departamentos WHERE id_departamento=%s", (id_departamento,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('lista_departamentos'))

# =========================
# MAIN
# =========================
if __name__ == '__main__':
    app.run(
        host='0.0.0.0', 
        port=int(os.environ.get('PORT', 5000)), 
        debug=os.environ.get('DEBUG', 'false').lower() == 'true'
    )
