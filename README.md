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

-  **Asynchronous processing:** Efficiently fetches and processes XML data in chunks using asyncio and aiohttp.
-  **Customizable XML Parsing:** Handles specific XML structures, extracting and cleaning data as required.
-  **CSV Export**: Converts XML data into well-structured CSV files, accommodating various encoding standards.
-  **REST API Interface**: Simple API endpoints to trigger the processing and retrieval of files.
-  **Error Handling**: Robust error management ensures that issues during XML processing are captured and reported.

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

## 📄 API Endpoints

### `GET /`

Renders the index page with instructions or UI for interacting with the service.

- **Description**: Renders the index page.
- **Response**: HTML page.

### `POST /process_link`

- **Description**: Processes the given link to fetch, parse, and save XML data into a CSV file.
- **Request Body**:
    - `link_url` (str): The URL to fetch the XML data from.
    - `preset_id` (str, optional): An optional preset ID.
- **Response**: JSON containing the URL of the generated CSV file and the preset ID.

### `GET /download/data_files/{filename}`

- **Description**: Downloads the specified CSV file.
- **Path Parameter**:
    - `filename` (str): The name of the CSV file to download.
- **Response**: The requested CSV file.

## Directory Structure

- `main.py`: The main application file.
- `templates/`: Directory containing HTML templates.
- `static/`: Directory containing static files (CSS, JS, images).
- `data_files/`: Directory where the generated CSV files are saved.

## Code Explanation

### `main.py`

- **Imports**: Various libraries and modules for HTTP handling, asynchronous operations, file handling, and XML parsing.
- **FastAPI Setup**: Initializes the FastAPI app, sets up Jinja2 templates, and mounts the static files directory.
- **Data Models**: Defines the `LinkData` model using Pydantic for request validation.
- **Utility Functions**: Includes functions for removing unwanted HTML tags from descriptions and fetching URL data in chunks.
- **Processing Functions**: Contains asynchronous functions to process XML data, parse it, and save it into CSV files.
- **API Endpoints**: Defines endpoints for the root page, processing links, and downloading CSV files.

### Utility Functions

- `remove_unwanted_tags(description)`: Removes HTML tags from a given description string.
- `fetch_url_in_chunks(link_url, chunk_size=1024)`: Fetches data from a URL in chunks and yields the data.
- `process_offer(offer_elem, build_category_path)`: Processes individual XML elements to extract offer data.
- `process_link_stream(link_url, chunk_size=1024)`: Processes the XML data stream from the URL, parses it, and writes it to a CSV file.

# 🛡️ Security
- CORS is enabled for all origins (). This can be restricted as needed.*
- Ensure to handle any sensitive data appropriately and restrict access to certain endpoints if necessary.

# 🧙‍♂️ About
MagicXML is maintained by Solrikk. If you have any questions or need further assistance, please feel free to reach out.
