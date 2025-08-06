const translations = {
    en: {
        "Data Конвертер": "Data Converter",
        "Конвертируйте между форматами XML, CSV и Excel. Введите URL XML-файла или загрузите XML/CSV/Excel файлы для преобразования.": "Convert between XML, CSV, and Excel formats. Enter an XML URL or upload XML/CSV/Excel files for conversion.",
        "Что умеет наша программа?": "What can our program do?",
        "XML и YML": "XML & YML",
        "Стандартные XML и YML форматы Яндекс.Маркета": "Standard XML and Yandex Market YML formats",
        "Многоформатная конвертация": "Multi-format Conversion",
        "Конвертируйте между форматами XML, CSV и Excel в любом направлении": "Convert between XML, CSV and Excel formats in any direction",
        "Выгрузки 1С": "1C Export",
        "Обработка XML выгрузок из 1С:Предприятие": "1C:Enterprise XML exports processing",
        "Готово для Excel": "Excel Ready",
        "Идеальный CSV вывод для Excel": "Perfect CSV output for Excel",
        "Умная очистка": "Smart Clean",
        "Автоматическая очистка и организация данных": "Auto data cleaning and organization",
        "Поддерживаемые форматы:": "Supported Formats:",
        "URL-адрес XML файла:": "XML file URL:",
        "Обработать XML": "Process XML",
        "Загрузить файл": "Upload File",
        "XML в CSV": "XML to CSV",
        "CSV в XML": "CSV to XML",
        "CSV в Excel": "CSV to Excel",
        "Excel в CSV": "Excel to CSV",
        "JPG в PNG": "JPG to PNG",
        "PNG в JPG": "PNG to JPG",
        "Формат XML:": "XML Format:",
        "Перетащите XML, CSV или Excel файл сюда или нажмите для выбора": "Drag & drop your XML, CSV or Excel file here or click to browse",
        "Поддерживаются: .xml, .yml, .yaml, .csv, .xlsx, .xls, .json, .jpg, .jpeg, .png": "Supported: .xml, .yml, .yaml, .csv, .xlsx, .xls, .json, .jpg, .jpeg, .png",
        "Обработать файл": "Process File",
        "Обработка вашего XML файла...": "Processing your XML file...",
        "Предварительный просмотр данных": "Data Preview",
        "Записей:": "Records:",
        "Колонок:": "Columns:",
        "Скачать CSV": "Download CSV",
        "Обработать другой файл": "Process another file",
        "Если у вас возникли проблемы, свяжитесь со мной: akyoning@yandex.ru": "If you have any problems, contact me: akyoning@yandex.ru",
        "© 2025 MagicXML - Конвертер XML в CSV": "© 2025 MagicXML - XML to CSV Converter"
    }
};

let currentLanguage = 'ru';

function updateLanguage(lang) {
    currentLanguage = lang;
    document.getElementById('currentLang').textContent = lang.toUpperCase();

    const elements = document.querySelectorAll('.translate');
    elements.forEach(element => {
        const key = element.textContent.trim();
        if (translations[lang] && translations[lang][key]) {
            element.textContent = translations[lang][key];
        }

        if (element.tagName === 'INPUT' && element.hasAttribute('placeholder')) {
            const placeholderKey = element.getAttribute('placeholder');
            if (translations[lang] && translations[lang][placeholderKey]) {
                element.setAttribute('placeholder', translations[lang][placeholderKey]);
            }
        }
    });
}

function createParticle() {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.left = Math.random() * 100 + '%';
    particle.style.animationDuration = (Math.random() * 8 + 4) + 's';
    particle.style.animationDelay = Math.random() * 2 + 's';
    particle.style.opacity = Math.random() * 0.8 + 0.2;

    // Vary particle sizes
    const size = Math.random() * 4 + 2;
    particle.style.width = size + 'px';
    particle.style.height = size + 'px';

    return particle;
}

function initParticles() {
    const particlesContainer = document.getElementById('particlesContainer');
    if (!particlesContainer) return;

    // Create initial particles
    for (let i = 0; i < 80; i++) {
        const particle = createParticle();
        particlesContainer.appendChild(particle);
    }

    // Continuously add new particles
    setInterval(() => {
        if (particlesContainer.children.length < 100) {
            const particle = createParticle();
            particlesContainer.appendChild(particle);

            // Remove old particles
            setTimeout(() => {
                if (particle.parentNode) {
                    particle.remove();
                }
            }, 8000);
        }
    }, 200);
}

function resetForm() {
    document.getElementById('linkUrl').value = '';
    document.getElementById('fileInput').value = '';
    document.getElementById('selectedFile').style.display = 'none';
    document.getElementById('fileDropZone').style.display = 'block';
    document.getElementById('fileSubmitButton').disabled = true;

    document.getElementById('processingDiv').style.display = 'none';
    document.getElementById('resultDiv').style.display = 'none';
    document.getElementById('previewDiv').style.display = 'none';
    document.querySelector('.actions').style.display = 'none';

    document.querySelector('input[name="sourceFormat"][value="xml"]').checked = true;
    document.querySelector('input[name="targetFormat"][value="csv"]').checked = true;
    updateTargetFormatOptions();
    updateFileInputAccept();
}

function updateTargetFormatOptions() {
    const sourceFormat = document.querySelector('input[name="sourceFormat"]:checked').value;
    const targetFormatOptions = document.querySelectorAll('input[name="targetFormat"]');
    const targetFormatLabels = document.querySelectorAll('.format-option:has(input[name="targetFormat"])');

    targetFormatLabels.forEach(label => {
        const input = label.querySelector('input[name="targetFormat"]');
        const targetFormat = input.value;

        if (targetFormat === sourceFormat) {
            label.classList.add('disabled');
            input.disabled = true;
            if (input.checked) {
                const firstAvailable = document.querySelector(`input[name="targetFormat"]:not([value="${sourceFormat}"])`);
                if (firstAvailable) {
                    firstAvailable.checked = true;
                }
            }
        } else {
            label.classList.remove('disabled');
            input.disabled = false;
        }
    });

    updateXmlFormatDisplay();
}

function updateXmlFormatDisplay() {
    const sourceFormat = document.querySelector('input[name="sourceFormat"]:checked').value;
    const targetFormat = document.querySelector('input[name="targetFormat"]:checked').value;
    const xmlFormatSelector = document.getElementById('xmlFormatSelector');

    if ((sourceFormat === 'csv' && targetFormat === 'xml') || 
        (sourceFormat === 'json' && targetFormat === 'xml')) {
        xmlFormatSelector.style.display = 'block';
    } else {
        xmlFormatSelector.style.display = 'none';
    }
}

function getConversionType() {
    const sourceFormat = document.querySelector('input[name="sourceFormat"]:checked').value;
    const targetFormat = document.querySelector('input[name="targetFormat"]:checked').value;
    return `${sourceFormat}-to-${targetFormat}`;
}

function updateFileInputAccept() {
    const sourceFormat = document.querySelector('input[name="sourceFormat"]:checked').value;
    let acceptTypes = '.xml,.yml,.yaml,.csv,.xlsx,.xls,.json,.jpg,.jpeg,.png';

    switch(sourceFormat) {
        case 'xml':
            acceptTypes = '.xml,.yml,.yaml';
            break;
        case 'csv':
            acceptTypes = '.csv';
            break;
        case 'excel':
            acceptTypes = '.xlsx,.xls';
            break;
        case 'json':
            acceptTypes = '.json';
            break;
        case 'jpg':
            acceptTypes = '.jpg,.jpeg';
            break;
        case 'png':
            acceptTypes = '.png';
            break;
    }

    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.setAttribute('accept', acceptTypes);
    }

    const fileDropZone = document.getElementById('fileDropZone');
    if (fileDropZone) {
        const fileTypes = fileDropZone.querySelector('.file-types');
        if (fileTypes) {
            const supportedText = fileTypes.getAttribute('data-ru') || 'Поддерживаются:';
            fileTypes.textContent = `${supportedText} ${acceptTypes}`;
        }
    }
}

function processUrl(url) {
    showProcessing();

    const data = {
        link_url: url,
        return_url: "",
        preset_id: ""
    };

    fetch('/process_link', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(async response => {
        console.log('URL processing response status:', response.status);
        const responseText = await response.text();
        console.log('URL processing raw response:', responseText);

        if (!responseText.trim()) {
            throw new Error('Сервер вернул пустой ответ');
        }

        if (!responseText.trim().startsWith('{') && !responseText.trim().startsWith('[')) {
            throw new Error(`Сервер вернул не JSON: ${responseText.substring(0, 200)}`);
        }

        try {
            return JSON.parse(responseText);
        } catch (jsonError) {
            console.error('JSON parse error in URL processing:', jsonError);
            throw new Error(`Ошибка парсинга JSON: ${jsonError.message}. Ответ: ${responseText.substring(0, 200)}`);
        }
    })
    .then(data => {
        hideProcessing();
        console.log('Parsed URL processing data:', data);
        if (data.file_url) {
            showResult(data.file_url, 'CSV');
        } else {
            throw new Error(data.detail || 'Неизвестная ошибка');
        }
    })
    .catch(error => {
        hideProcessing();
        console.error('Full URL processing error:', error);
        showError(error.message || 'Произошла ошибка при обработке URL');
    });
}

function processFile(file) {
    showProcessing();

    const conversionType = getConversionType();
    let endpoint = '/process_file';
    let formData = new FormData();
    formData.append('file', file);

    if (conversionType === 'csv-to-xml') {
        endpoint = '/convert_csv_to_xml';
        const xmlFormat = document.getElementById('xmlFormat').value;
        formData.append('xml_format', xmlFormat);
    } else if (conversionType === 'csv-to-excel') {
        endpoint = '/convert_csv_to_excel';
    } else if (conversionType === 'excel-to-csv') {
        endpoint = '/convert_excel_to_csv';
    } else if (conversionType === 'json-to-csv') {
        endpoint = '/convert_json_to_csv';
    } else if (conversionType === 'csv-to-json') {
        endpoint = '/convert_csv_to_json';
        formData.append('json_format', 'array');
    } else if (conversionType === 'xml-to-json') {
        endpoint = '/convert_xml_to_json';
    } else if (conversionType === 'jpg-to-png') {
        endpoint = '/convert_jpg_to_png';
    } else if (conversionType === 'png-to-jpg') {
        endpoint = '/convert_png_to_jpg';
    }

    fetch(endpoint, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideProcessing();
        if (data.file_url) {
            const fileType = getFileTypeFromConversion(conversionType);
            showResult(data.file_url, fileType);
        } else {
            throw new Error(data.detail || 'Неизвестная ошибка');
        }
    })
    .catch(error => {
        hideProcessing();
        console.error('Error:', error);
        showError(error.message || 'Произошла ошибка при обработке файла');
    });
}

function getFileTypeFromConversion(conversionType) {
    switch(conversionType) {
        case 'xml-to-csv': return 'CSV';
        case 'csv-to-xml': return 'XML';
        case 'csv-to-excel': return 'Excel';
        case 'excel-to-csv': return 'CSV';
        case 'jpg-to-png': return 'PNG';
        case 'png-to-jpg': return 'JPG';
        default: return 'File';
    }
}

function showProcessing() {
    const processingDiv = document.getElementById('processingDiv');
    processingDiv.style.display = 'block';
    document.getElementById('resultDiv').style.display = 'none';
    document.querySelector('.actions').style.display = 'none';

    setTimeout(() => {
        processingDiv.classList.add('show');
    }, 10);

    processingDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideProcessing() {
    const processingDiv = document.getElementById('processingDiv');
    processingDiv.classList.remove('show');

    setTimeout(() => {
        processingDiv.style.display = 'none';
    }, 300);
}

function showResult(fileUrl, fileType) {
    const downloadLink = document.getElementById('downloadLink');
    const downloadText = downloadLink.querySelector('span');
    const actionsDiv = document.querySelector('.actions');

    downloadLink.href = fileUrl;
    downloadText.textContent = `Скачать ${fileType}`;

    document.getElementById('resultDiv').innerHTML = `
        <div class="success-message">
            <i class="fas fa-check-circle"></i>
            Файл успешно обработан!
        </div>
    `;
    document.getElementById('resultDiv').style.display = 'block';
    if (actionsDiv) {
        actionsDiv.style.display = 'flex';
    }
}

function showError(message) {
    const actionsDiv = document.querySelector('.actions');

    document.getElementById('resultDiv').innerHTML = `
        <div class="error-message">
            <i class="fas fa-exclamation-circle"></i>
            ${message}
        </div>
    `;
    document.getElementById('resultDiv').style.display = 'block';
    if (actionsDiv) {
        actionsDiv.style.display = 'flex';
    }
}

async function detectUserLanguage() {
    const savedLang = localStorage.getItem('preferred-language');
    if (savedLang) {
        setLanguage(savedLang);
        document.getElementById('currentLang').textContent = savedLang.toUpperCase();
        currentLanguage = savedLang;
        return savedLang;
    }

    await detectCountryAndSetLanguage();
}

async function detectCountryAndSetLanguage() {
    try {
        const response = await fetch('https://ipapi.co/json/');
        const data = await response.json();

        let detectedLang = 'ru';

        const countryLanguageMap = {
            'US': 'en',
            'GB': 'en',
            'CA': 'en',
            'AU': 'en',
            'FR': 'fr',
            'BE': 'fr',
            'CH': 'fr',
            'DE': 'de',
            'AT': 'de',
            'ES': 'es',
            'MX': 'es',
            'AR': 'es',
            'CO': 'es',
            'RU': 'ru',
            'BY': 'ru',
            'KZ': 'ru',
            'UA': 'ru',
            'JP': 'ja',
            'KR': 'ko',
            'CN': 'zh',
            'TW': 'zh',
            'HK': 'zh',
            'SG': 'zh',
            'SA': 'ar',
            'AE': 'ar',
            'EG': 'ar',
            'JO': 'ar',
            'LB': 'ar',
            'SY': 'ar',
            'IQ': 'ar',
            'KW': 'ar',
            'QA': 'ar',
            'BH': 'ar',
            'OM': 'ar',
            'YE': 'ar'
        };

        if (data.country_code && countryLanguageMap[data.country_code]) {
            detectedLang = countryLanguageMap[data.country_code];
        }

        console.log(`Detected country: ${data.country_code}, setting language: ${detectedLang}`);
        currentLanguage = detectedLang;
        setLanguage(detectedLang);
        localStorage.setItem('preferred-language', detectedLang);
        document.getElementById('currentLang').textContent = detectedLang.toUpperCase();

    } catch (error) {
        console.log('Could not detect country, using English as default for international users');
        currentLanguage = 'en';
        setLanguage('en');
        localStorage.setItem('preferred-language', 'en');
        document.getElementById('currentLang').textContent = 'EN';
    }
}

function setLanguage(lang) {
    currentLanguage = lang;

    document.querySelectorAll('.translate').forEach(element => {
        const text = element.getAttribute(`data-${lang}`);
        if (text) {
            element.textContent = text;
        } else {
            const fallbackText = element.getAttribute(`data-en`) || element.getAttribute(`data-ru`);
            if (fallbackText) element.textContent = fallbackText;
        }
    });

    document.querySelectorAll('.nav-text').forEach(element => {
        const text = element.getAttribute(`data-${lang}`);
        if (text) {
            element.textContent = text;
        } else {
            const fallbackText = element.getAttribute(`data-en`) || element.getAttribute(`data-ru`);
            if (fallbackText) element.textContent = fallbackText;
        }
    });

    document.querySelectorAll('input[placeholder]').forEach(input => {
        const placeholderText = input.getAttribute(`data-${lang}`);
        if (placeholderText) {
            input.placeholder = placeholderText;
        } else {
            const fallbackPlaceholder = input.getAttribute(`data-en`) || input.getAttribute(`data-ru`);
            if (fallbackPlaceholder) input.placeholder = fallbackPlaceholder;
        }
    });

    const titles = {
        'en': 'Magic XML - XML to CSV Converter',
        'ru': 'Magic XML - Конвертер XML в CSV',
        'es': 'Magic XML - Convertidor XML a CSV',
        'fr': 'Magic XML - Convertisseur XML en CSV',
        'de': 'Magic XML - XML zu CSV Konverter',
        'ja': 'Magic XML - XML から CSV コンバーター',
        'ko': 'Magic XML - XML에서 CSV 변환기',
        'zh': 'Magic XML - XML 转 CSV 转换器',
        'ar': 'Magic XML - محول XML إلى CSV'
    };

    document.title = titles[lang] || titles['ru'];
    document.documentElement.lang = lang;
}

async function loadUserInfo() {
    try {
        const response = await fetch('/api/user-info');
        const userInfo = await response.json();

        const userIdElement = document.getElementById('userId');
        if (userIdElement) {
            userIdElement.textContent = userInfo.user_id;
        }

        console.log('User info loaded:', userInfo);
    } catch (error) {
        console.error('Error loading user info:', error);
        const userIdElement = document.getElementById('userId');
        if (userIdElement) {
            userIdElement.textContent = 'ERROR';
        }
    }
}

function updateActiveUsersCounter() {
    const activeCountElement = document.getElementById('activeCount');
    if (!activeCountElement) return;

    const currentCount = Math.floor(Math.random() * 8) + 5;

    activeCountElement.style.transform = 'scale(1.2)';
    activeCountElement.style.color = '#60a5fa';

    setTimeout(() => {
        activeCountElement.textContent = currentCount;
        activeCountElement.style.transform = 'scale(1)';
        activeCountElement.style.color = '#fbbf24';
    }, 200);
}

function startActiveUsersSimulation() {
    updateActiveUsersCounter();

    function scheduleNextUpdate() {
        const nextUpdate = Math.floor(Math.random() * 7000) + 8000;
        setTimeout(() => {
            updateActiveUsersCounter();
            scheduleNextUpdate();
        }, nextUpdate);
    }

    scheduleNextUpdate();
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'check-circle'}"></i>
        <span>${message}</span>
    `;

    if (!document.getElementById('toast-styles')) {
        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            .toast {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 16px;
                border-radius: 8px;
                color: white;
                font-weight: 500;
                z-index: 10000;
                display: flex;
                align-items: center;
                gap: 8px;
                min-width: 300px;
                animation: slideIn 0.3s ease-out;
            }
            .toast-success { background: #10b981; }
            .toast-error { background: #ef4444; }
            .toast-warning { background: #f59e0b; }
            @keyframes slideIn {
                from { transform: translateX(100%); }
                to { transform: translateX(0); }
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, 300);
}

document.addEventListener('DOMContentLoaded', function() {
    initParticles();
    loadUserInfo();
    startActiveUsersSimulation();

    const langToggle = document.getElementById('langToggle');
    const langDropdown = document.querySelector('.language-dropdown');

    if (langToggle && langDropdown) {
        langToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            langDropdown.style.display = langDropdown.style.display === 'block' ? 'none' : 'block';
        });

        document.addEventListener('click', function() {
            langDropdown.style.display = 'none';
        });

        langDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
            if (e.target.tagName === 'A') {
                const lang = e.target.getAttribute('data-lang');
                updateLanguage(lang);
                langDropdown.style.display = 'none';
            }
        });
    }

    const sourceFormatInputs = document.querySelectorAll('input[name="sourceFormat"]');
    const targetFormatInputs = document.querySelectorAll('input[name="targetFormat"]');

    sourceFormatInputs.forEach(input => {
        input.addEventListener('change', () => {
            updateTargetFormatOptions();
            updateFileInputAccept();
        });
    });

    targetFormatInputs.forEach(input => {
        input.addEventListener('change', updateXmlFormatDisplay);
    });

    updateTargetFormatOptions();
    updateFileInputAccept();

    const fileInput = document.getElementById('fileInput');
    const fileDropZone = document.getElementById('fileDropZone');
    const selectedFile = document.getElementById('selectedFile');
    const removeFile = document.getElementById('removeFile');
    const fileSubmitButton = document.getElementById('fileSubmitButton');

    if (fileInput && fileDropZone) {
        fileDropZone.addEventListener('click', () => fileInput.click());

        fileDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            fileDropZone.classList.add('dragover');
        });

        fileDropZone.addEventListener('dragleave', () => {
            fileDropZone.classList.remove('dragover');
        });

        fileDropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            fileDropZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelect(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileSelect(e.target.files[0]);
            }
        });
    }

    if (removeFile) {
        removeFile.addEventListener('click', () => {
            fileInput.value = '';
            selectedFile.style.display = 'none';
            fileDropZone.style.display = 'block';
            fileSubmitButton.disabled = true;
        });
    }

    function handleFileSelect(file) {
        const fileName = selectedFile.querySelector('.file-name');
        if (fileName) {
            fileName.textContent = file.name;
            selectedFile.style.display = 'flex';
            fileDropZone.style.display = 'none';
            fileSubmitButton.disabled = false;
        }
    }

    const processUrlButton = document.getElementById('processUrlButton');

    if (processUrlButton) {
        processUrlButton.addEventListener('click', function(e) {
            e.preventDefault();
            const linkUrl = document.getElementById('linkUrl').value.trim();

            if (!linkUrl) {
                alert('Пожалуйста, введите URL');
                return;
            }

            processUrl(linkUrl);
        });
    }

    if (fileSubmitButton) {
        fileSubmitButton.addEventListener('click', function(e) {
            e.preventDefault();
            const fileInput = document.getElementById('fileInput');

            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Пожалуйста, выберите файл');
                return;
            }

            processFile(fileInput.files[0]);
        });
    }
});
