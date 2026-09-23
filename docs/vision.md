# Visión: reconocimiento, landmarks y liveness

Cómo decide FaceTrack quién es cada rostro, cómo mide parpadeo y orientación de la cabeza, y qué garantiza (y qué no) la prueba de vida.

## Pipeline de reconocimiento

```
Imagen/frame ─▶ Detección (YuNet) ─▶ Alineación (5 keypoints) ─▶ SFace ─▶ Embedding (128-D, norma 1)
                                                                              │
                          distancia coseno a la muestra más cercana de cada persona conocida
                                                   │
                         ┌─────────────────────────┴─────────────────────────┐
                 distancia <= threshold                               distancia > threshold
                         │                                                    │
                     CONOCIDO                                            DESCONOCIDO
```

| Componente | Módulo | Responsabilidad |
|---|---|---|
| `BaseFaceDetector` | `services/face_detector.py`, `services/detectors/` | Encontrar rostros: caja, score y keypoints. Dos implementaciones: **YuNet** (default) y **MediaPipe BlazeFace** |
| `FaceEmbedder` | `services/embedding_service.py` | Rostro alineado → vector. Hoy `SFaceEmbedder`; la interfaz permite cambiar de modelo |
| `FaceRecognizer` | `services/face_recognizer.py` | Vector vs. conocidos → conocido/desconocido. No sabe de imágenes, modelos ni base |
| `RecognitionPipeline` | `services/recognition_pipeline.py` | Une los tres; procesa cada rostro de un frame por separado |

Ningún componente de visión accede a la base de datos. Cada embedding guarda su `model_version` y el reconocedor rechaza mezclar versiones: cambiar de modelo obliga a re-registrar rostros, pero no a tocar la API ni el esquema.

### Por qué YuNet y SFace

- **YuNet** (OpenCV) detecta rostros chicos y a distancia y entrega los 5 keypoints (ojos, nariz, comisuras) que SFace necesita para alinear el rostro. **BlazeFace short-range** (MediaPipe) solo ve rostros que ocupan buena parte del encuadre: una cara al 16 % del ancho de la imagen dio score 0,33, por debajo del mínimo.
- **SFace** (OpenCV) genera embeddings de 128 dimensiones sin dependencias adicionales. Distancias medidas con las fotos de los tests: misma persona ≈ 0,19; personas distintas, 0,69 a 1,1.

### Threshold y confidence

- **Distancia**: coseno entre embeddings normalizados (0 = idénticos, 2 = opuestos). Con varias muestras por persona se usa la más cercana.
- **Threshold** (`FACE_RECOGNITION_THRESHOLD`, default `0.63`): equivale a la similitud coseno 0,363 recomendada por OpenCV para SFace. **El más parecido no se acepta automáticamente**: si supera el threshold, es desconocido. Bajarlo reduce falsos positivos a costa de más desconocidos. El valor por defecto no es una calibración propia: conviene ajustarlo con la cámara y la iluminación reales.
- **Confidence**: `1 - distancia / (2 × threshold)`. Vale 1 con distancia 0 y 0,5 justo en el threshold; un desconocido tiene 0. **Es una heurística, no una probabilidad calibrada.**
- Rostros menores a `MIN_FACE_SIZE` px no se evalúan (se informan sin identidad); el resto del frame se procesa igual.

## Registro facial

Cada foto pasa, en orden: formato (MIME y firma real del archivo) → tamaño y resolución → decodificación → **exactamente un rostro** → **calidad** → embedding válido → **coherencia**.

| Control de calidad | Umbral (configurable) | Por qué |
|---|---|---|
| Tamaño del rostro | ≥ 80 px (`ENROLLMENT_MIN_FACE_SIZE`) | Rostros chicos dan embeddings poco fiables |
| Score del detector | ≥ 0,8 | Rostros tapados o de perfil puntúan bajo |
| Nitidez (varianza del Laplaciano, rostro a 112×112) | ≥ 100 | Fotos nítidas: ≥ 889; desenfoque fuerte: ≤ 90 |
| Brillo medio | 50 a 210 | Fotos normales: 113–173; oscurecidas: 22–34; sobreexpuestas: ≥ 236 |

Los umbrales se calibraron con las fotos de `backend/tests/fixtures` y versiones degradadas de ellas.

**Coherencia**: una muestra se rechaza si no se parece a las que la persona ya tiene, o si se parece a otra persona registrada. Una foto cargada por error contaminaría el reconocimiento de ambas.

## Landmarks

`services/landmark_service.py` usa **MediaPipe Face Landmarker**: 478 puntos por rostro y una matriz de transformación 3D.

- **EAR** (*Eye Aspect Ratio*, Soukupová y Čech 2016): `(|p2-p6| + |p3-p5|) / (2·|p1-p4|)` sobre 6 puntos de cada ojo. Baja al cerrar el ojo.
- **Orientación de la cabeza**, en grados, sobre la imagen sin espejar:
  - `yaw > 0`: la persona gira hacia **su** derecha;
  - `pitch > 0`: mira hacia arriba;
  - `roll > 0`: la cabeza aparece rotada en sentido antihorario.

Las convenciones se verificaron con fotos reales, no se supusieron: la foto de Lena (cabeza girada) da −19° de yaw y +19° al espejarla; rotar una foto 20° cambia el roll en ~20°. Las fotos "de frente" dan unos −10° de pitch, por eso los movimientos se miden contra la pose inicial de cada persona.

Face Landmarker usa internamente el detector short-range de BlazeFace: en escenas amplias solo ve rostros cercanos. Alcanza para liveness (una persona frente a la cámara).

## Parpadeo

El EAR con ojos abiertos varía mucho entre personas (0,17 a 0,55 en las fotos de los tests): un umbral fijo fallaría. El detector es **adaptativo**:

- apertura normal = percentil 90 de los EAR de esa persona con ojos abiertos;
- ojo **cerrado** por debajo del 65 % de esa apertura (`LIVENESS_BLINK_CLOSE_RATIO`);
- ojo **abierto** de nuevo por encima del 85 % (`LIVENESS_BLINK_OPEN_RATIO`);
- un parpadeo es abierto → cerrado → abierto.

Probado con fotos reales a las que se les "cierran" los ojos pintándolos: el EAR cae al 24–55 % del valor abierto en las 5 fotos. No es una medición médica.

## Prueba de vida (liveness)

```
persona frente a la cámara → 3 frames de referencia (pose y apertura normales)
        → "Parpadeá" → parpadeo detectado
        → "Girá la cabeza hacia tu derecha / izquierda" o "Mirá hacia arriba"
          (≥ 20° de yaw o ≥ 12° de pitch respecto de la pose inicial)
        → LIVE → evento de reconocimiento (+ asistencia, si se pidió)
```

| Resultado | Cuándo |
|---|---|
| `LIVE` | Completó todos los desafíos, en orden, antes de `LIVENESS_TIMEOUT_SECONDS` |
| `SUSPICIOUS` | Hubo un rostro pero no completó los desafíos (típico de una foto impresa o en pantalla), o **el rostro cambió de identidad** a mitad de la prueba (se compara el embedding de uno de cada 5 frames con el del inicio) |
| `UNKNOWN` | No hubo un rostro visible el tiempo suficiente, o había varias personas |

El segundo desafío se elige al azar entre girar a la izquierda, a la derecha o mirar arriba, así que no sirve un vídeo grabado con un gesto fijo. El frontend envía 12 frames por segundo en este modo, porque un parpadeo dura entre 100 y 300 ms.

> ⚠️ **No es un mecanismo de seguridad biométrica de alta garantía.** Detecta fotos estáticas, pero un vídeo de la persona haciendo los gestos, o una máscara, pueden superarla. No hay análisis de profundidad, textura ni reflejos. Sirve como disuasión básica, no como control de acceso crítico.
