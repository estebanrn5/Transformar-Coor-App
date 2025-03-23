import asyncio
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
from typing import List
from fastapi import BackgroundTasks

app = FastAPI()

# Directorios temporales
TEMP_DIR = Path(r"backend/temp_files")
TEMP_DIR.mkdir(exist_ok=True)

# Montar archivos estáticos (CSS, JS, imágenes)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

async def cleanup_temp_files():
    # Esperar 5 segundos antes de limpiar
    await asyncio.sleep(20)

    # Eliminar todo el contenido de TEMP_DIR
    temp_dir = Path(TEMP_DIR)
    
    for item in temp_dir.glob('*'):
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

# Servir el index.html en la raíz
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("frontend/index.html")


@app.post("/upload/")
async def upload_geofile(files: List[UploadFile] = File(...)):
    try:
        # Buscar el archivo .shp (si existe)
        shp_file = next((f for f in files if f.filename.lower().endswith(".shp")), None)

        # Generar file_id único
        file_id = str(uuid.uuid4())
        base_filename = None
        is_shapefile = False

        # ===========================================================================
        # 1. Validación para Shapefiles (múltiples archivos)
        # ===========================================================================
        if shp_file:
            is_shapefile = True
            base_filename = Path(shp_file.filename).stem  # Nombre sin extensión

            # Validar archivos requeridos
            required_exts = {".shp", ".shx", ".prj"}
            uploaded_exts = {Path(f.filename).suffix.lower() for f in files}

            # Verificar archivos faltantes
            missing = required_exts - uploaded_exts
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Archivos requeridos faltantes: {', '.join(missing)}"
                )

        # ===========================================================================
        # 2. Guardar archivos
        # ===========================================================================
        saved_files = []
        for file in files:
            if is_shapefile:
                # Para Shapefile: {file_id}_{base_name}.ext
                ext = Path(file.filename).suffix
                filename = f"{file_id}_{base_filename}{ext}"
            else:
                # Para otros formatos: {file_id}_{filename}
                filename = f"{file_id}_{file.filename}"

            file_path = TEMP_DIR / filename

            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
                saved_files.append(filename)

        # ===========================================================================
        # 3. Respuesta
        # ===========================================================================
        return {
            "file_id": file_id,
            "filename": f"{base_filename}.shp" if is_shapefile else files[0].filename,
            "uploaded_files": saved_files
        }

    except Exception as e:
        # Limpiar archivos en caso de error
        for f in saved_files:
            (TEMP_DIR / f).unlink(missing_ok=True)
        raise HTTPException(500, f"Error subiendo archivos: {str(e)}")


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
        
        crs_inicio = gdf.crs
        
        # Procesar CRS
        gdf = gdf.to_crs(4686)

        crs_fin = gdf.crs
        
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
                
        return {
            "zip_path": str(zip_path),
            "crs_inicio": f"{crs_inicio} - {crs_inicio.name}",
            "crs_fin": f"{crs_fin} - {crs_fin.name}",
            "message": f"Reproyección/Transformación Sistema de Referencia de Coordenadas (CRS):\n CRS archivo inicial: {crs_inicio} - {crs_inicio.name} \n CRS archivo final: {crs_fin} - {crs_fin.name}"
            }
    
    except Exception as e:
        raise HTTPException(500, f"Error procesando archivo: {str(e)}")

@app.get("/download/{file_id}")
async def download_file(file_id: str, background_tasks: BackgroundTasks):
    zip_path = TEMP_DIR / f"{file_id}.zip"
    if not zip_path.exists():
        raise HTTPException(404, "Archivo no encontrado")
    
    # Agregar tarea en segundo plano para limpiar
    background_tasks.add_task(cleanup_temp_files)
    
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
                     zoom_start=16, tiles= False)
        
        # Añadir capa
        folium.GeoJson(gdf, style_function=lambda x: {
            'fillColor': 'red',
            'color': 'red',
            'weight': 2,
            'fillOpacity': 0.5
        },name="Capa Geográfica").add_to(m)

        #Mapas Base
        base_maps = {
            'CartoDB positron': 'CartoDB positron',
            'CartoDB dark_matter': 'CartoDB dark_matter',
            'OpenStreetMap': 'OpenStreetMap',
        }

        #Agregando Mapas Base
        for name, tile in base_maps.items():
            folium.TileLayer(tiles=tile, name=name, attr=name).add_to(m)
        
        # Control de Layers
        folium.LayerControl(collapsed=False).add_to(m)
        
        # Guardar temporalmente
        temp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        m.save(temp_html.name)
        
        return FileResponse(temp_html.name)
        
    except Exception as e:
        raise HTTPException(500, f"Error generando mapa: {str(e)}")

# Montar archivos estáticos para el frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")