let currentFileId = null;
let currentFilename = null;

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const files = fileInput.files;
    
    // Validar que se hayan seleccionado archivos
    if (files.length === 0) {
        alert("¡Debes seleccionar al menos un archivo!");
        return;
    }

    const formData = new FormData();
    
    // Agregar todos los archivos al FormData
    for (const file of files) {
        formData.append('files', file);  // Usar 'files' como clave
    }

    try {
        const response = await fetch('/upload/', {
            method: 'POST',
            body: formData  // No se necesita header 'Content-Type' para FormData
        });
        
        const data = await response.json();
        console.log("Respuesta del servidor:", data);
        
        // Actualizar variables globales
        currentFileId = data.file_id;
        currentFilename = data.filename;

        document.getElementById('preview').classList.remove('disabled')

    } catch (error) {
        alert('Error subiendo archivos: ' + error.message);
    }
}


async function processFile() {
    try {
        const response = await fetch('/process/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_id: currentFileId,
                filename: currentFilename
            })
        });
        
        const data = await response.json();

        // Mostrar mensaje con CRS
        alert(data.message);

        const downloadLink = document.getElementById('downloadLink');
        downloadLink.href = `/download/${currentFileId}`;
        downloadLink.style.display = 'inline';

        document.getElementById('download').classList.remove('disabled')

    } catch (error) {
        alert('Error procesando archivo: ' + error.message);
    }
}

async function previewMap() {
    try {
        const response = await fetch(`/preview/${currentFileId}?filename=${currentFilename}`);
        const mapUrl = URL.createObjectURL(await response.blob());
        
        const mapContainer = document.getElementById('mapContainer');
        mapContainer.innerHTML = `<iframe src="${mapUrl}" style="width:100%; height:100%; border:none"></iframe>`;

        document.getElementById('procces').classList.remove('disabled')
    } catch (error) {
        alert('Error generando vista previa: ' + error.message);
    }
}