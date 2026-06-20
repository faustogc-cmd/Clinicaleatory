import os
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)
CORS(app)

# ==========================================
# 1. INICIALIZACIÓN DE FIREBASE
# ==========================================
key_path = os.environ.get('FIREBASE_KEY_PATH', 'firebase-key.json')

try:
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Conexión exitosa a la base de datos centralizada de Firestore.")
except Exception as e:
    print(f"Error crítico al inicializar Firebase: {e}")

# ==========================================
# 2. LÓGICA MATEMÁTICA INTERNA
# ==========================================
def generar_bloque_permutado():
    """
    Genera un bloque balanceado (tamaño 4) cerrado y aleatorizado.
    """
    bloque = ['Grupo A (Control)', 'Grupo A (Control)', 'Grupo B (Intervenido)', 'Grupo B (Intervenido)']
    random.shuffle(bloque)
    return bloque

# ==========================================
# 3. RUTA PRINCIPAL (ENDPOINT) DE ALEATORIZACIÓN
# ==========================================
@app.route('/api/aleatorizar', methods=['POST'])
def aleatorizar_paciente():
    try:
        # A. Captura de datos y token desde la petición web
        datos = request.json
        token_investigador = request.headers.get('Authorization')
        proyecto_id = datos.get('proyecto_id')

        if not token_investigador or not proyecto_id:
            return jsonify({"error": "Petición denegada: Faltan credenciales o no se especificó el proyecto"}), 400

        token = token_investigador.replace('Bearer ', '')

        # B. Validación de Identidad (Authentication)
        try:
            usuario_decodificado = auth.verify_id_token(token)
            uid = usuario_decodificado['uid']
            # El token de Firebase ya trae el correo verificado, sin necesidad de otra consulta
            email_investigador = usuario_decodificado.get('email', 'correo no disponible')
        except Exception:
            return jsonify({"error": "Seguridad: Token inválido, expirado o manipulado."}), 401

        # C. Verificación de Permisos RBAC (Authorization)
        doc_usuario = db.collection('usuarios').document(uid).get()
        if not doc_usuario.exists:
            return jsonify({"error": "Perfil de investigador no encontrado en el sistema."}), 403

        perfil_usuario = doc_usuario.to_dict()
        proyectos_permitidos = perfil_usuario.get('proyectos_permitidos', [])
        nombre_investigador = perfil_usuario.get('nombre', email_investigador)

        if proyecto_id not in proyectos_permitidos:
            return jsonify({"error": "Acceso denegado: No tienes autorización para ingresar datos en este ensayo clínico."}), 403

        # D. Construcción del Estrato Clínico
        edad = datos.get('edad')
        sexo = datos.get('sexo')
        diabetes = datos.get('diabetes')
        hta = datos.get('hipertension')
        clave_estrato = f"{sexo} | {edad} | {diabetes} | {hta}"

        ref_proyecto = db.collection('proyectos').document(proyecto_id)

        # E. Generación Atómica del Consecutivo (ID)
        ref_contador = ref_proyecto.collection('configuracion').document('contador_global')

        if not ref_contador.get().exists:
            ref_contador.set({'ultimo_id': 1000})

        ref_contador.update({'ultimo_id': firestore.Increment(1)})
        nuevo_id_num = ref_contador.get().to_dict().get('ultimo_id')
        nuevo_id = f"{proyecto_id[:4].upper()}-{nuevo_id_num}"

        # F. Aleatorización por Bloques Estratificada
        ref_estrato = ref_proyecto.collection('estratos').document(clave_estrato)
        doc_estrato = ref_estrato.get()

        bloque_actual = doc_estrato.to_dict().get('bloque', []) if doc_estrato.exists else []

        if len(bloque_actual) == 0:
            bloque_actual = generar_bloque_permutado()

        grupo_asignado = bloque_actual.pop(0)
        ref_estrato.set({'bloque': bloque_actual})

        # G. Rastro de Auditoría y Guardado Inmutable
        # Se guarda el UID (identificador técnico inmutable), el correo y el nombre
        # del investigador, para que el panel de auditoría sea legible sin tener
        # que cruzar manualmente con la colección 'usuarios'.
        nuevo_registro = {
            "id_paciente": nuevo_id,
            "estrato_clinico": clave_estrato,
            "grupo_asignado": grupo_asignado,
            "ingresado_por_uid": uid,
            "ingresado_por_email": email_investigador,
            "ingresado_por_nombre": nombre_investigador,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        ref_proyecto.collection('pacientes_registrados').document(nuevo_id).set(nuevo_registro)

        # H. Respuesta de éxito a la página web
        # NOTA: A propósito no se devuelve el nombre/correo del investigador
        # en la respuesta — eso solo vive en la base de datos, no en el navegador.
        return jsonify({
            "id": nuevo_id,
            "grupo": grupo_asignado,
            "mensaje": "Aleatorización completada y registrada exitosamente."
        }), 200

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

# ==========================================
# 4. EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)
