from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import xml.etree.ElementTree as ET
import re
import csv
import os
import aiohttp
import asyncio
import chardet

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LinkData(BaseModel):
    link_url: str
    return_url: str = ""
    preset_id: str = ""

def remove_unwanted_tags(description):
    if description:
        description = re.sub(r'<[^>]+>', '', description)
    else:
        description = ''
    return description

async def fetch_url(link_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(link_url) as response:
            response.raise_for_status()
            raw_data = await response.read()
            detected_encoding = chardet.detect(raw_data)['encoding']
            return raw_data.decode(detected_encoding)

async def split_xml(xml_data, chunk_size):
    root = ET.fromstring(xml_data)
    offers = root.findall('.//offer')

    for i in range(0, len(offers), chunk_size):
        chunked_offers = offers[i:i + chunk_size]
        chunk_root = ET.Element(root.tag, root.attrib)
        shop = ET.SubElement(chunk_root, 'shop')
        for offer in chunked_offers:
            shop.append(offer)
        yield ET.tostring(chunk_root, encoding='unicode', method='xml')

async def process_offer(offer_elem, build_category_path):
    offer_id = offer_elem.get('id', '0')
    offer_data = {'id': offer_id}

    category_id_elem = offer_elem.find('.//categoryId')
    category_id = category_id_elem.text if category_id_elem is not None else 'Undefined'
    category_path = build_category_path(category_id)
    offer_data['category_path'] = category_path

    for category_elem in offer_elem:
        if category_elem.tag not in ['picture', 'param']:
            category_name = category_elem.tag
            category_value = category_elem.text
            if category_value and category_value.replace('.', '', 1).isdigit():
                category_value = category_value.replace('.', ',')
            offer_data[category_name] = category_value or ""

    picture_elems = offer_elem.findall('.//picture')
    pictures = "///".join([
        picture_elem.text if picture_elem.text is not None else ""
        for picture_elem in picture_elems
    ]) if picture_elems else ""

    if pictures:
        offer_data['pictures'] = pictures

    param_elems = offer_elem.findall('.//param')
    params = {
        param_elem.get('name'): param_elem.text or ""
        for param_elem in param_elems
    } if param_elems else {}
    offer_data.update(params)

    if 'description' in offer_data and offer_data['description']:
        offer_data['description'] = remove_unwanted_tags(offer_data['description'])

    return offer_data

async def process_chunk(xml_chunk):
    try:
        root = ET.fromstring(xml_chunk)

        categories = {}
        category_parents = {}
        for category in root.findall('.//category'):
            category_id = category.get('id')
            parent_id = category.get('parentId')
            categories[category_id] = category.text if category.text is not None else 'Undefined'
            if parent_id:
                category_parents[category_id] = parent_id

        def build_category_path(category_id):
            path = []
            while category_id:
                path.append(categories.get(category_id, 'Undefined'))
                category_id = category_parents.get(category_id)
            return '///'.join(reversed(path))

        offers = []
        for offer_elem in root.findall('.//offer'):
            offer_data = await process_offer(offer_elem, build_category_path)
            offers.append(offer_data)

        return {
            "offers": offers,
            "categories": categories,
            "category_parents": category_parents
        }
    except Exception as e:
        print(f"An error occurred while processing the fragment: {str(e)}")
        return None

async def process_link(link_url, base_url):
    try:
        xml_data = await fetch_url(link_url)

        chunk_size = 100
        tasks = []

        async for chunk in split_xml(xml_data, chunk_size):
            task = process_chunk(chunk)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        combined_data = {"offers": [], "categories": {}, "category_parents": {}}
        for result in results:
            if result:
                combined_data["offers"].extend(result["offers"])
                combined_data["categories"].update(result["categories"])
                combined_data["category_parents"].update(result["category_parents"])

        save_path = "data_files"
        os.makedirs(save_path, exist_ok=True)
        domain_name = urlparse(link_url).netloc.replace("www.", "")
        safe_filename = domain_name.replace(".", "_")
        unique_filename = f"{safe_filename}.csv"
        file_path = os.path.join(save_path, unique_filename)

        category_names = set()
        for row in combined_data["offers"]:
            category_names.update(row.keys())

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as file:
            writer = csv.DictWriter(file,
                                    fieldnames=sorted(category_names),
                                    delimiter=';')
            writer.writeheader()
            for offer in combined_data["offers"]:
                for key, value in offer.items():
                    if isinstance(value, str):
                        offer[key] = value.encode('utf-8',
                                                  errors='replace').decode('utf-8')
                writer.writerow(offer)

        print(f"File saved: {file_path}")
        file_url = f"{base_url}/download/data_files/{unique_filename}"
        return file_path, file_url
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None, None

@app.get("/")
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process_link")
async def process_link_post(link_data: LinkData, request: Request):
    link_url = link_data.link_url
    preset_id = link_data.preset_id
    return_url = link_data.return_url

    base_url = str(request.url).rstrip(request.url.path)

    result_path, file_url = await process_link(link_url, base_url)

    if result_path and file_url:
        response_data = {
            "file_url": file_url,
            "preset_id": preset_id,
            "status": "completed"
        }

        if return_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(return_url,
                                            json=response_data) as callback_response:
                        callback_response.raise_for_status()
            except Exception as e:
                print(f"An error occurred during the callback: {str(e)}")

        print(f"File created and available at URL: {file_url}")
        return response_data
    else:
        raise HTTPException(status_code=500,
                            detail="An error occurred while processing the link")

@app.get("/status/{preset_id}")
async def check_processing_status(preset_id: str):
    return {
        "status": "completed",
        "file_url":
        "http://localhost:8000/download/data_files/your_file.csv"
    }

@app.get("/download/data_files/{filename}")
async def download_csv(filename: str):
    file_path = os.path.join("data_files", filename)
    print(f"Attempting to download file: {file_path}")
    if os.path.isfile(file_path):
        print("File found, starting download.")
        return FileResponse(path=file_path,
                            filename=filename,
                            media_type='application/octet-stream')
    else:
        print("File not found.")
        raise HTTPException(status_code=404, detail="File not found.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
