from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import xml.etree.ElementTree as ET
import csv
import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re

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


def clean_description(description):
    if not description:
        return ''
    soup = BeautifulSoup(description, 'html5lib')
    allowed_tags = ['p', 'br']
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
    for content in list(soup.contents):
        if isinstance(content, str):
            if content.strip():
                new_p = soup.new_tag('p')
                new_p.string = content.strip()
                content.replace_with(new_p)
    return str(soup)


def sanitize_name(name):
    if not name:
        return ''
    sanitized = name.replace('⌀', '')
    sanitized = re.sub(r'[^\w\s.,-]', '', sanitized)
    return sanitized


async def fetch_url(link_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(link_url) as response:
            response.raise_for_status()
            raw_data = await response.read()
            return raw_data.decode('utf-8')


async def split_offers(xml_data, chunk_size, format_type):
    root = ET.fromstring(xml_data)
    if format_type == 'offer':
        offers = root.findall('.//offer')
    elif format_type == 'product':
        offers = root.findall('.//product')
    else:
        offers = []
    for i in range(0, len(offers), chunk_size):
        yield offers[i:i + chunk_size]


async def process_offer(offer_elem, build_category_path, format_type):
    offer_data = {}
    
    # Get all attributes of the root element
    for key, value in offer_elem.attrib.items():
        offer_data[f"attr_{key}"] = value
    
    # Process all child elements
    for elem in offer_elem.iter():
        # Skip the root element
        if elem == offer_elem:
            continue
            
        # Get element attributes
        for key, value in elem.attrib.items():
            column_name = f"{elem.tag}_{key}"
            if column_name in offer_data:
                offer_data[column_name] += f"///{value}"
            else:
                offer_data[column_name] = value
                
        # Get element text
        if elem.text and elem.text.strip():
            if elem.tag in offer_data:
                offer_data[elem.tag] += f"///{elem.text.strip()}"
            else:
                offer_data[elem.tag] = elem.text.strip()

    if format_type == 'offer':
        category_id_elem = offer_elem.find('.//categoryId')
        category_id = category_id_elem.text if category_id_elem is not None else 'Undefined'
        category_path = build_category_path(category_id)
        offer_data['category_path'] = category_path
    elif format_type == 'product':
        offer_data['category_path'] = 'Undefined'

    for category_elem in offer_elem:
        if format_type == 'offer':
            excluded_tags = ['picture', 'param', 'description']
        elif format_type == 'product':
            excluded_tags = ['photos', 'fabric', 'features', 'options']
        else:
            excluded_tags = []

        if category_elem.tag not in excluded_tags:
            category_name = category_elem.tag
            category_value = category_elem.text
            if category_value and category_value.replace('.', '', 1).isdigit():
                category_value = category_value.replace('.', ',')
            if category_name == 'name':
                category_value = sanitize_name(category_value)
            offer_data[category_name] = category_value or ""

    if format_type == 'offer':
        picture_elems = offer_elem.findall('.//picture')
    elif format_type == 'product':
        picture_elems = offer_elem.findall('.//photo')
    pictures = "///".join([
        picture_elem.text if picture_elem.text is not None else ""
        for picture_elem in picture_elems
    ]) if picture_elems else ""
    if pictures:
        offer_data['pictures'] = pictures

    if format_type == 'offer':
        param_elems = offer_elem.findall('.//param')
        params = {}
        for param_elem in param_elems:
            key = param_elem.get('name')
            value = param_elem.text or ""
            if key in params:
                params[key] += f", {value}"
            else:
                params[key] = value
    elif format_type == 'product':
        fabric_elem = offer_elem.find('.//fabric')
        param_elems_fabric = fabric_elem.findall(
            './/feature') if fabric_elem is not None else []
        features_elem = offer_elem.find('.//features')
        param_elems_features = features_elem.findall(
            './/feature') if features_elem is not None else []
        params = {}
        for param_elem in param_elems_fabric:
            key = f"fabric_{param_elem.get('name')}"
            value = param_elem.text or ""
            if key in params:
                params[key] += f", {value}"
            else:
                params[key] = value
        for param_elem in param_elems_features:
            key = f"feature_{param_elem.get('name')}"
            value = param_elem.text or ""
            if key in params:
                params[key] += f", {value}"
            else:
                params[key] = value
    offer_data.update(params)

    if format_type == 'offer':
        description_elem = offer_elem.find('.//description')
    elif format_type == 'product':
        description_elem = offer_elem.find('.//name')
    if description_elem is not None and description_elem.text:
        cleaned_description = clean_description(description_elem.text)
        offer_data['description'] = cleaned_description

    return offer_data


async def process_offers_chunk(offers_chunk, build_category_path, format_type):
    offers = []
    for offer_elem in offers_chunk:
        offer_data = await process_offer(offer_elem, build_category_path,
                                         format_type)
        offers.append(offer_data)
    return {"offers": offers}


async def process_link(link_url, base_url):
    try:
        xml_data = await fetch_url(link_url)
        root = ET.fromstring(xml_data)

        if root.findall('.//offer'):
            format_type = 'offer'
        elif root.findall('.//product'):
            format_type = 'product'
        else:
            raise ValueError("Unsupported XML format")

        categories = {}
        category_parents = {}
        if format_type == 'offer':
            for category in root.findall('.//category'):
                category_id = category.get('id')
                parent_id = category.get('parentId')
                categories[
                    category_id] = category.text if category.text else 'Undefined'
                if parent_id:
                    category_parents[category_id] = parent_id

            def build_category_path(category_id):
                path = []
                while category_id:
                    path.append(categories.get(category_id, 'Undefined'))
                    category_id = category_parents.get(category_id)
                return '///'.join(reversed(path))
        elif format_type == 'product':

            def build_category_path(category_id):
                return 'Undefined'

        offers_generator = split_offers(xml_data, 100, format_type)
        tasks = []
        async for offers_chunk in offers_generator:
            task = asyncio.create_task(
                process_offers_chunk(offers_chunk, build_category_path,
                                     format_type))
            tasks.append(task)
        results = await asyncio.gather(*tasks)
        combined_data = {
            "offers": [],
            "categories": categories,
            "category_parents": category_parents
        }
        for result in results:
            if result:
                combined_data["offers"].extend(result["offers"])
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
                        offer[key] = value.replace('"', '""').replace(
                            '\n', ' ').replace('\r', ' ')
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
                    async with session.post(
                            return_url,
                            json=response_data) as callback_response:
                        callback_response.raise_for_status()
            except Exception as e:
                print(f"An error occurred during the callback: {str(e)}")
        print(f"File created and available at URL: {file_url}")
        return response_data
    else:
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the link")


@app.get("/status/{preset_id}")
async def check_processing_status(preset_id: str):
    return {
        "status": "completed",
        "file_url": "http://localhost:8000/download/data_files/your_file.csv"
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
