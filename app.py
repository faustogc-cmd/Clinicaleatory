import os
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)

# Habilitar CORS para permitir que tu página web se comunique con este servidor
CORS(app)

# ==========================================
# 1. INICIALIZACIÓN DE FIREBASE
# ==========================================
# En Render, la ruta apuntará a la variable de entorno que configuramos en "Secret Files".
# En local, buscará el archivo 'firebase-key.json' en la misma carpeta.
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
        
        # Validaciones iniciales
        if not token_investigador or not proyecto_id:
            return jsonify({"error": "Petición denegada: Faltan credenciales o no se especificó el proyecto"}), 400

        # Limpiar el token de la cabecera HTTP estándar "Bearer"
        token = token_investigador.replace('Bearer ', '')

        # B. Validación de Identidad (Authentication)
        try:
            usuario_decodificado = auth.verify_id_token(token)
            uid = usuario_decodificado['uid']
        except Exception:
            return jsonify({"error": "Seguridad: Token inválido, expirado o manipulado."}), 401

        # C. Verificación de Permisos RBAC (Authorization)
        ref_usuario = db.collection('usuarios').document(uid).get()
        if not ref_usuario.exists:
            return jsonify({"error": "Perfil de investigador no encontrado en el sistema."}), 403
            
        proyectos_permitidos = ref_usuario.to_dict().get('proyectos_permitidos', [])
        
        if proyecto_id not in proyectos_permitidos:
            return jsonify({"error": "Acceso denegado: No tienes autorización para ingresar datos en este ensayo clínico."}), 403

        # D. Construcción del Estrato Clínico
        edad = datos.get('edad')
        sexo = datos.get('sexo')
        diabetes = datos.get('diabetes')
        hta = datos.get('hipertension')
        
        # La clave es la intersección de las 4 variables
        clave_estrato = f"{sexo} | {edad} | {diabetes} | {hta}"

        # Establecer la referencia dinámica hacia el proyecto específico
        ref_proyecto = db.collection('proyectos').document(proyecto_id)

        # E. Generación Atómica del Consecutivo (ID)
        ref_contador = ref_proyecto.collection('configuracion').document('contador_global')
        
        # Si es el primer paciente del proyecto, inicializamos el contador
        if not ref_contador.get().exists:
            ref_contador.set({'ultimo_id': 1000})
            
        # Incremento seguro y atómico en la nube para evitar colisiones entre usuarios
        ref_contador.update({'ultimo_id': firestore.Increment(1)})
        nuevo_id_num = ref_contador.get().to_dict().get('ultimo_id')
        
        # Formato del ID: Primeras 4 letras del proyecto + Número (ej. CARD-1001)
        nuevo_id = f"{proyecto_id[:4].upper()}-{nuevo_id_num}"

        # F. Aleatorización por Bloques Estratificada
        ref_estrato = ref_proyecto.collection('estratos').document(clave_estrato)
        doc_estrato = ref_estrato.get()

        # Extraer el bloque existente o crear una lista vacía
        bloque_actual = doc_estrato.to_dict().get('bloque', []) if doc_estrato.exists else []

        # Si la lista está vacía, se agotó el bloque anterior; generamos uno nuevo cerrado
        if len(bloque_actual) == 0:
            bloque_actual = generar_bloque_permutado()

        # Extraemos (y eliminamos) el primer elemento del bloque
        grupo_asignado = bloque_actual.pop(0)
        
        # Guardamos el bloque restante en la base de datos para el siguiente paciente
        ref_estrato.set({'bloque': bloque_actual})

        # G. Rastro de Auditoría y Guardado Inmutable
        nuevo_registro = {
            "id_paciente": nuevo_id,
            "estrato_clinico": clave_estrato,
            "grupo_asignado": grupo_asignado,
            "ingresado_por_uid": uid, # Rastro del investigador
            "timestamp": firestore.SERVER_TIMESTAMP # Sello de tiempo del servidor (imposible de falsificar)
        }
        
        ref_proyecto.collection('pacientes_registrados').document(nuevo_id).set(nuevo_registro)

        # H. Respuesta de éxito a la página web
        return jsonify({
            "id": nuevo_id,
            "grupo": grupo_asignado,
            "mensaje": "Aleatorización completada y registrada exitosamente."
        }), 200

    except Exception as e:
        # Captura de errores inesperados
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

# ==========================================
# 4. EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    # Usado solo para pruebas locales. Render usará Gunicorn.
    app.run(debug=True, port=5000)
