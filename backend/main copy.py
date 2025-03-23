import os
import uuid
import geopandas as gpd
import pandas as pd
import zipfile
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import folium
import tempfile
import fiona
from fastapi import Body  # <-- Añade esta importación

app = FastAPI()

# Directorios temporales
TEMP_DIR = Path(r"backend/temp_files")
TEMP_DIR.mkdir(exist_ok=True)

# Servir el index.html en la raíz
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("frontend/index.html")

# Montar archivos estáticos (CSS, JS, imágenes)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Generar ID único
        file_id = str(uuid.uuid4())
        file_path = TEMP_DIR / f"{file_id}_{file.filename}"
        
        # Guardar archivo
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        return {"file_id": file_id, "filename": file.filename}
    
    except Exception as e:
        raise HTTPException(500, f"Error subiendo archivo: {str(e)}")

@app.post("/process/")
async def process_file(file_id: str = Body(...), filename: str = Body(...)):

    # Configuración de Fiona
    fiona.drvsupport.supported_drivers['kml'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['KML'] = 'rw' 
    fiona.drvsupport.supported_drivers['kmz'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['KMZ'] = 'rw'
    fiona.drvsupport.supported_drivers['libkml'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

    try:
        input_path = TEMP_DIR / f"{file_id}_{filename}"
        output_dir = TEMP_DIR / file_id
        output_dir.mkdir(exist_ok=True)
        
        # Leer archivo
        if filename.lower().endswith((".kml", ".kmz")):
            gdf = gpd.read_file(input_path, engine='fiona')
        else:
            gdf = gpd.read_file(input_path, engine='pyogrio')
            
        # Validar geometrías
        for index, row in gdf.iterrows():
            geom = row.geometry
            geom_type = geom.geom_type
            multi_geoms = ["MultiPoint", "MultiLineString", "MultiPolygon"]
            
            if geom_type in multi_geoms and len(geom.geoms) > 1:
                raise HTTPException(400, f"Geometría {geom_type} con múltiples partes encontrada")
        
        # Procesar CRS
        gdf = gdf.to_crs(4686)
        
        # Guardar resultados
        output_path = output_dir / "Procesado.shp"
        datetime_cols = gdf.select_dtypes(include=['datetime']).columns
        
        for col in datetime_cols:
            gdf[col] = pd.to_datetime(gdf[col]).dt.date.astype('object')
            
        gdf.to_file(output_path, engine='fiona')
        
        # Crear ZIP
        zip_path = TEMP_DIR / f"{file_id}.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in output_dir.iterdir():
                zipf.write(file, arcname=file.name)
                
        return {"zip_path": str(zip_path)}
    
    except Exception as e:
        raise HTTPException(500, f"Error procesando archivo: {str(e)}")

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    zip_path = TEMP_DIR / f"{file_id}.zip"
    if not zip_path.exists():
        raise HTTPException(404, "Archivo no encontrado")
    
    return FileResponse(zip_path, filename="resultado.zip")

@app.get("/preview/{file_id}")
async def preview_map(file_id: str, filename: str):

    fiona.drvsupport.supported_drivers['kml'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['KML'] = 'rw' 
    fiona.drvsupport.supported_drivers['kmz'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['KMZ'] = 'rw'
    fiona.drvsupport.supported_drivers['libkml'] = 'rw' # enable KML support which is disabled by default
    fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

    try:
        input_path = TEMP_DIR / f"{file_id}_{filename}"
        
        # Leer archivo
        if filename.lower().endswith((".kml", ".kmz")):
            gdf = gpd.read_file(input_path, engine='fiona')
        else:
            gdf = gpd.read_file(input_path, engine='pyogrio')

        gdf = gdf.to_crs(4686)
        
        # Crear mapa
        m = folium.Map(location=[gdf.geometry.centroid.y.mean(), 
                               gdf.geometry.centroid.x.mean()], 
                     zoom_start=16  )
        
        # Añadir capa
        folium.GeoJson(gdf, style_function=lambda x: {
            'fillColor': 'red',
            'color': 'red',
            'weight': 2,
            'fillOpacity': 0.5
        }).add_to(m)
        
        # Guardar temporalmente
        temp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        m.save(temp_html.name)
        
        return FileResponse(temp_html.name)
        
    except Exception as e:
        raise HTTPException(500, f"Error generando mapa: {str(e)}")

# Montar archivos estáticos para el frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")