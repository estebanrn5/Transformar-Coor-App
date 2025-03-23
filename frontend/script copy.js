let currentFileId = null;
let currentFilename = null;

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    
    try {
        const response = await fetch('/upload/', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        currentFileId = data.file_id;
        currentFilename = data.filename;
        
        document.getElementById('processSection').style.display = 'block';
    } catch (error) {
        alert('Error subiendo archivo: ' + error.message);
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
        const downloadLink = document.getElementById('downloadLink');
        downloadLink.href = `/download/${currentFileId}`;
        downloadLink.style.display = 'inline';
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
    } catch (error) {
        alert('Error generando vista previa: ' + error.message);
    }
}