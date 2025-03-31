
<div align="center">
  <h1>MagicXML 🧙‍♂️</h1>
  <p><strong>Advanced XML to CSV Conversion Tool</strong></p>
  
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.95.0-009688.svg)](https://fastapi.tiangolo.com/)
</div>

<div align="center"> 
  <h3>
    <a href="https://github.com/Solrikk/MagicXML/blob/main/README.md">⭐English⭐</a> | 
    <a href="https://github.com/Solrikk/MagicXML/blob/main/README_RU.md">Russian</a> | 
    <a href="https://github.com/Solrikk/MagicXML/blob/main/README_GE.md">German</a> | 
    <a href="https://github.com/Solrikk/MagicXML/blob/main/README_JP.md">Japanese</a> | 
    <a href="README_KR.md">Korean</a> | 
    <a href="README_CN.md">Chinese</a> 
  </h3> 
</div>

-----------------

## 🚀 Overview

**MagicXML** is a high-performance web application built with FastAPI that transforms XML data into structured CSV format. Designed for data analysts, developers, and e-commerce professionals, MagicXML handles complex XML structures with advanced parsing capabilities, asyncio-powered processing, and intelligent data classification.

🔗 **Live Demo**: [https://magic-xml.replit.app](https://magic-xml.replit.app)

## ✨ Key Features

- **High-Performance Processing**: Asynchronous architecture for efficient handling of large XML files
- **Intelligent Data Extraction**: Contextual parsing of complex nested XML structures
- **Data Cleaning & Sanitization**: Automatic cleaning of HTML tags and special characters
- **Multilingual Support**: Interface available in English, Russian, and more languages
- **RESTful API**: Programmatic access for seamless integration with your systems
- **Callback Support**: Optional webhook notifications when processing is complete
- **Robust Error Handling**: Comprehensive error management with detailed reporting

## 🛠️ Technical Architecture

MagicXML leverages several advanced technologies to deliver exceptional performance:

- **FastAPI Backend**: High-performance asynchronous API framework
- **Asyncio & Aiohttp**: Non-blocking I/O operations for concurrent processing
- **XML ElementTree**: Efficient XML parsing and traversal
- **BeautifulSoup**: Intelligent HTML content cleaning
- **Modern Frontend**: Responsive design with custom CSS and JavaScript

## 📊 Use Cases

- **E-commerce Data Processing**: Convert product feeds from XML to CSV
- **Data Analysis**: Transform XML datasets into analysis-ready CSV format
- **System Integration**: Bridge XML-based systems with CSV-compatible tools
- **Catalog Management**: Process large product catalogs efficiently
- **Automated Workflows**: Integrate with data pipelines via API

## 🔧 Installation & Setup

### Prerequisites

- Python 3.8+
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/Solrikk/MagicXML.git
cd MagicXML

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## 🔌 API Reference

### Convert XML to CSV

```bash
curl -X 'POST' \
  'https://magic-xml.replit.app/process_link' \
  -H 'Content-Type: application/json' \
  -d '{
    "link_url": "https://example.com/data.xml",
    "preset_id": "optional-tracking-id",
    "return_url": "https://your-callback-url.com/webhook"
  }'
```

#### Response

```json
{
  "file_url": "https://magic-xml.replit.app/download/data_files/example_com.csv",
  "preset_id": "optional-tracking-id",
  "status": "completed"
}
```

### Check Processing Status

```bash
curl -X 'GET' 'https://magic-xml.replit.app/status/{preset_id}'
```

### Download Generated CSV

```bash
curl -X 'GET' 'https://magic-xml.replit.app/download/data_files/{filename}'
```

## 📝 Implementation Details

### Asynchronous Processing

MagicXML processes XML files asynchronously using Python's `asyncio` and `aiohttp`:

```python
async def process_offers_chunk(offers_chunk, build_category_path, format_type):
    offers = []
    for offer_elem in offers_chunk:
        offer_data = await process_offer(offer_elem, build_category_path, format_type)
        offers.append(offer_data)
    return {"offers": offers}
```

This approach enables efficient concurrent processing, drastically reducing conversion time for large XML files.

### Text Processing & Data Cleaning

The application implements sophisticated text processing to ensure data quality:

```python
def clean_description(description):
    if not description:
        return ''
    soup = BeautifulSoup(description, 'html5lib')
    allowed_tags = ['p', 'br']
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
    # Additional cleaning logic...
    return str(soup)
```

<div align="center">
  <p>© 2025 MagicXML - Advanced XML to CSV Converter</p>
  <p>
    <a href="https://github.com/Solrikk/MagicXML">GitHub</a> •
    <a href="https://magic-xml.replit.app">Live Demo</a>
  </p>
</div>
