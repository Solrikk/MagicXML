async function processForm(e) {
  e.preventDefault();
  const linkUrl = document.getElementById('linkUrl').value;
  const processingDiv = document.getElementById('processingDiv');
  const resultDiv = document.getElementById('resultDiv');
  const downloadLink = document.getElementById('downloadLink');
  const anotherProcessButton = document.getElementById('anotherProcessButton');
       
  processingDiv.style.display = 'block';
  resultDiv.innerHTML = '';
  downloadLink.style.display = 'none';
  anotherProcessButton.style.display = 'none';
       
  const response = await fetch('/process_link', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ link_url: linkUrl })
  });
       
  const data = await response.json();
  processingDiv.style.display = 'none';
       
  if (response.ok) {
    resultDiv.innerHTML = `<p>Успешно обработано!</p>`;
    if (data.file_url) {
      downloadLink.style.display = 'block';
      downloadLink.href = data.file_url;
    }
  } else {
    resultDiv.innerHTML = `<p>Ошибка: ${data.detail}</p>`;
  }
      
  anotherProcessButton.style.display = 'block';
}
    
function resetForm() {
  document.getElementById('linkForm').reset();
  const resultDiv = document.getElementById('resultDiv');
  const downloadLink = document.getElementById('downloadLink');
  const anotherProcessButton = document.getElementById('anotherProcessButton');
      
  resultDiv.innerHTML = '';
  downloadLink.style.display = 'none';
  anotherProcessButton.style.display = 'none';
}

document.getElementById('linkForm').addEventListener('submit', processForm);

