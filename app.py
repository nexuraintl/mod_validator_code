from flask import Flask
import src.controllers.controller_archivos as archivo_controller

app= Flask(__name__)
app.register_blueprint(archivo_controller.upload_bp)
