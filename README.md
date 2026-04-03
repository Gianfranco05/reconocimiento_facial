# 👁️ Sistema de Detección Facial en Tiempo Real

Este proyecto es una aplicación de visión artificial diseñada para detectar rostros humanos en tiempo real utilizando la cámara web. Ha sido desarrollado con un enfoque en la robustez, el código limpio y la precisión, sirviendo como una excelente base para sistemas más complejos de biometría, control de asistencia o monitoreo de seguridad.

### Gianfranco Canciani

## 🚀 Características Principales

El proyecto ha evolucionado de un script procedural básico a una herramienta robusta con las siguientes características:

* **Detección de Alta Precisión:** Sustitución de las clásicas cascadas de Haar por modelos modernos de redes neuronales (MediaPipe / OpenCV DNN), lo que garantiza una detección rápida y estable incluso con variaciones de luz, oclusión parcial o rostros de perfil.
* **Arquitectura Orientada a Objetos (POO):** El código central está encapsulado en una clase `FaceDetector`. Esto facilita la lectura, el mantenimiento y permite instanciar múltiples detectores si se trabajara con varias cámaras simultáneamente.
* **Manejo Seguro de Hardware:** Incorpora validaciones estrictas para el manejo del hardware de video. El sistema verifica proactivamente la disponibilidad de la cámara y la integridad de cada fotograma (frame) antes de procesarlo, evitando caídas inesperadas (crashes) si la cámara se desconecta o está en uso por otro programa.

## 📂 ¿Qué contiene este proyecto?

La arquitectura del proyecto está pensada para ser modular:

* `main.py` *(o el nombre de tu archivo principal)*: Es el punto de entrada de la aplicación. Se encarga de inicializar la cámara, instanciar la clase detectora y manejar el bucle principal de renderizado y salida.
* `FaceDetector` (Clase central):
    * **Estado:** Mantiene en memoria el modelo de red neuronal cargado, evitando recargas innecesarias.
    * **Método de procesamiento:** Recibe un fotograma en bruto, realiza las conversiones de color necesarias, lo pasa por el modelo predictivo y devuelve las coordenadas de los rostros encontrados.
    * **Método de dibujo:** Aísla la lógica de interfaz (dibujar rectángulos y métricas en pantalla) de la lógica matemática de detección.

## 🛠️ Tecnologías y Requisitos

Para ejecutar este proyecto, necesitas tener instalado Python 3.8 o superior y las siguientes bibliotecas:

```bash
pip install opencv-python mediapipe
