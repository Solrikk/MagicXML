<div align="center">
  <img src="https://github.com/Solrikk/MagicXML/blob/main/assets/images/market.png" width="70%"/>
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

# ✨ MagicXML ✨

## Overview

**MagicXML** is a FastAPI application designed to transform and process XML data streams from URLs effortlessly. With a focus on efficiency and scalability, MagicXML parses large XML files in chunks, extracting valuable information and saving it into well-structured CSV files. This tool is perfect for anyone needing to handle substantial XML data sources, offering an intuitive web interface and robust API endpoints for seamless integration.

## Features

- 📦 **Chunked Data Fetching**: Fetch XML data in chunks to handle large files without overloading memory.
- 🔍 **XML Parsing**: Efficiently parse XML data and extract relevant details.
- 📄 **CSV Export**: Save parsed data into neatly organized CSV files.
- 📥 **File Download**: Provide easy access to the generated CSV files via a download endpoint.
- 🌐 **Web Interface**: Serve static files and templates for an intuitive user experience.

## Requirements

- Python 3.8+
- [FastAPI](https://fastapi.tiangolo.com/): A modern, fast (high-performance), web framework for building APIs with Python 3.6+.
- [aiohttp](https://docs.aiohttp.org/en/stable/): An asynchronous HTTP client/server framework.
- [aiofiles](https://github.com/Tinche/aiofiles): A library for handling local file operations asynchronously.
- [Jinja2](https://jinja.palletsprojects.com/): A templating engine for Python.

## API Usage Example

To use the API, you can send a `POST` request to the `/process_link` endpoint with the necessary parameters. Below is an example using `curl`:

```sh
curl -X 'POST' \
  'http://127.0.0.1:8000/process_link' \
  -H 'Content-Type: application/json' \
  -d '{"link_url": "YOUR_XML_URL", "preset_id": "id=1234"}' \
  -o process_response.json
```
Replace **YOUR_XML_URL** with the actual URL of the XML data you want to process. This request will save the response in a file named process_response.json.

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/Solrikk/MagicXML.git
    cd MagicXML
    ```

2. Create and activate a virtual environment:
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Usage

1. Run the FastAPI application:
    ```sh
    uvicorn main:app --reload
    ```

2. Open your browser and go to `http://127.0.0.1:8000` to access the web interface.

## API Endpoints

### `GET /`

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

