<div align="center">
  <img src="https://github.com/Solrikk/MagicXML/blob/main/assets/images/20b06e172642ddf80aae910c422db7dd.png" width="70%"/>
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

# MagicXML 🧙‍♂️📜

## Overview

**MagicXML** is a web application built with FastAPI that allows users to submit URLs pointing to XML files, processes the content, and converts the data into CSV format. The application supports asynchronous processing, ensuring high performance when handling large volumes of data.

## 🚀 Features

- **Asynchronous Processing**: Efficiently fetches and processes XML data in chunks using `asyncio` and `aiohttp`, ensuring scalability and high performance.
- **Customizable XML Parsing**: Tailored to handle specific XML structures, extracting and cleaning data as required.
- **Data Cleaning and Sanitization**: Removes unwanted HTML tags and special characters from descriptions and names to ensure data integrity.
- **CSV Export**: Converts processed XML data into well-structured CSV files, supporting various encoding standards.
- **REST API Interface**: Provides simple API endpoints to trigger processing and retrieve files programmatically.
- **Error Handling**: Implements robust error management to capture and report issues during XML processing.
- **CORS Support**: Allows requests from any origin, facilitating integration with other services and applications.
- **Processing Status Tracking**: Enables users to check the status of their processing tasks using a `preset_id`.

## 🛠️ Installation

- Python 3.8+
- [FastAPI](https://fastapi.tiangolo.com/): A modern, fast (high-performance), web framework for building APIs with Python 3.6+.
- [aiohttp](https://docs.aiohttp.org/en/stable/): An asynchronous HTTP client/server framework.
- [aiofiles](https://github.com/Tinche/aiofiles): A library for handling local file operations asynchronously.
- [Jinja2](https://jinja.palletsprojects.com/): A templating engine for Python.

## API Usage Example 

To use the API, you can send a `POST` request to the `/process_link` endpoint with the necessary parameters. Below is an example using `curl`:

```sh
curl -X 'POST' \
  'https://solarxml.replit.app//process_link' \
  -H 'Content-Type: application/json' \
  -d '{"link_url": "YOUR_XML_URL", "preset_id": "id=1234"}' \
  -o process_response.json
```
Replace **YOUR_XML_URL** with the actual URL of the XML data you want to process. This request will save the response in a file named process_response.json.

![image](https://github.com/user-attachments/assets/d9a32e6e-55c8-4ad7-8ade-b77d4a0d6f45)


## Clone the Repository

```python
git clone https://github.com/Solrikk/MagicXML.git
cd MagicXML
```

## Install Dependencies
You can install the required dependencies using pip:
```pip install -r requirements.txt```
