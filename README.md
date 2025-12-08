# Proyecto Calendario (PADEL)

Pequeña aplicación Flask que muestra un calendario en `localhost:5001` y permite agregar eventos.

Requisitos
- Python 3.8+

Instalación (PowerShell)
```powershell
python -m pip install -r requirements.txt
```

Ejecutar
```powershell
# opción 1: ejecutar directamente
python app.py

# opción 2: usar flask
$env:FLASK_APP = "app.py";
flask run --host=0.0.0.0 --port=5001
```

Acceder
- Abrir `http://localhost:5001` en el navegador.

Notas
- Los eventos se guardan en `events.db` en el mismo directorio.
- La interfaz usa FullCalendar desde CDN.