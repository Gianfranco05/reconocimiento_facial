import cv2
import os
import urllib.request
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class FaceDetector:
    def __init__(self, min_detection_confidence=0.5):
        """
        Inicializa el detector de rostros utilizando la moderna Tasks API de MediaPipe.
        """
        # 1. Ruta donde se guardará el modelo de IA
        self.model_path = 'blaze_face_short_range.tflite'
        self._download_model_if_needed()

        # 2. Configurar el detector con la Tasks API
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceDetectorOptions(
            base_options=base_options, 
            min_detection_confidence=min_detection_confidence
        )
        self.detector = vision.FaceDetector.create_from_options(options)

    def _download_model_if_needed(self):
        """Descarga el modelo de Google automáticamente si no existe en la carpeta."""
        if not os.path.exists(self.model_path):
            print("Descargando modelo de red neuronal de Google (solo la primera vez)...")
            url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
            try:
                urllib.request.urlretrieve(url, self.model_path)
                print("¡Modelo descargado con éxito!")
            except Exception as e:
                print(f"Error crítico al descargar el modelo: {e}")

    def run(self, camera_index=0):
        """
        Inicia el bucle de captura y detección de rostros.
        """
        # Iniciar la captura de video desde la cámara
        cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            print(f"Error: No se pudo inicializar la cámara con el índice {camera_index}.")
            print("Puede que esté desconectada o en uso por otra aplicación.")
            return

        print("Cámara iniciada. Presiona 'q' para salir.")

        try:
            while True:
                # Capturar frame por frame
                ret, frame = cap.read()

                # Manejo de error: verificar si se pudo leer el frame
                if not ret:
                    print("Error: No se pudo leer el frame de la cámara. Saliendo del bucle...")
                    break

                # Convertir el frame de BGR a RGB porque MediaPipe utiliza RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convertir la imagen al formato nativo de MediaPipe Tasks API
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

                # Procesar el frame para detectar los rostros
                detection_result = self.detector.detect(mp_image)

                # Dibujar los resultados en el frame original
                if detection_result.detections:
                    for detection in detection_result.detections:
                        bbox = detection.bounding_box
                        
                        # Coordenadas del rectángulo
                        start_point = int(bbox.origin_x), int(bbox.origin_y)
                        end_point = int(bbox.origin_x + bbox.width), int(bbox.origin_y + bbox.height)
                        
                        # Dibujar el rectángulo verde
                        cv2.rectangle(frame, start_point, end_point, (0, 255, 0), 2)

                # Mostrar el frame con los rostros detectados
                cv2.imshow("Deteccion de rostros con MediaPipe", frame)

                # Salir del bucle si se presiona la tecla 'q'
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            print("Apagando camara y cerrando ventanas...")
            cap.release()
            cv2.destroyAllWindows()

if __name__ == "__main__":
    # Crear una instancia del detector y ejecutar
    detector = FaceDetector(min_detection_confidence=0.6)
    detector.run()