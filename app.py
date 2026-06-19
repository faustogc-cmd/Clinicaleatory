import os
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
CORS(app)

# 1. Inicialización de Firebase
# Busca el archivo local para pruebas, o usa la variable de entorno en Render
key_path = os.environ.get('FIREBASE_KEY_PATH', 'firebase-key.json')
try:
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Error al inicializar Firebase: {e}")

def generar_bloque_permutado():
    bloque = ['Grupo A (Control)', 'Grupo A (Control)', 'Grupo B (Intervenido)', 'Grupo B (Intervenido)']
    random.shuffle(bloque)
    return bloque

@app.route('/api/aleatorizar', methods=['POST'])
def aleatorizar_paciente():
    try:
        datos = request.json
        edad = datos.get('edad')
        sexo = datos.get('sexo')
        diabetes = datos.get('diabetes')
        hta = datos.get('hipertension')

        clave_estrato = f"{sexo} | {edad} | {diabetes} | {hta}"

        # 2. Generación atómica del ID consecutivo
        ref_contador = db.collection('configuracion').document('contador_global')
        
        # Si el documento no existe (primer uso), lo creamos
        if not ref_contador.get().exists:
            ref_contador.set({'ultimo_id': 1000})
            
        # Incremento seguro en la nube
        ref_contador.update({'ultimo_id': firestore.Increment(1)})
        nuevo_id_num = ref_contador.get().to_dict().get('ultimo_id')
        nuevo_id = f"PAC-{nuevo_id_num}"

        # 3. Lógica estricta de aleatorización por bloques en Firestore
        ref_estrato = db.collection('estratos').document(clave_estrato)
        doc_estrato = ref_estrato.get()

        if doc_estrato.exists:
            bloque_actual = doc_estrato.to_dict().get('bloque', [])
        else:
            bloque_actual = []

        # Si el bloque está vacío, generamos uno nuevo
        if len(bloque_actual) == 0:
            bloque_actual = generar_bloque_permutado()

        # Asignar tratamiento y actualizar el bloque remanente en la nube
        grupo_asignado = bloque_actual.pop(0)
        ref_estrato.set({'bloque': bloque_actual})

        # 4. Guardar el registro inmutable del paciente
        nuevo_registro = {
            "id_paciente": nuevo_id,
            "estrato": clave_estrato,
            "grupo_asignado": grupo_asignado,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        db.collection('pacientes_registrados').document(nuevo_id).set(nuevo_registro)

        return jsonify({
            "id": nuevo_id,
            "grupo": grupo_asignado
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)