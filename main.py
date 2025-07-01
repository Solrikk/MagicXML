
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
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

default_app = FastAPI()
app = default_app
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
        if isinstance(content, str) and content.strip():
            new_p = soup.new_tag('p')
            new_p.string = content.strip()
            content.replace_with(new_p)
    return str(soup)


def sanitize_name(name):
    if not name:
        return ""
    sanitized = re.sub(r'[^\w\s\-\(\)\[\]\/\\,\.;:!?\'"«»„""`~@#$%^&*+=<>|№°]', '', name)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = re.sub(r'\(\s*([^)]+)\s*\)', r'(\1)', sanitized)
    return sanitized.strip()


async def split_offers(xml_data, chunk_size, format_type):
    root = ET.fromstring(xml_data)
    offers = root.findall(
        './/offer') if format_type == 'offer' else root.findall('.//product')
    for i in range(0, len(offers), chunk_size):
        yield offers[i:i + chunk_size]


async def process_offer(offer_elem, build_category_path, format_type):
    offer_data = {}
    
    for key, value in offer_elem.attrib.items():
        offer_data[f"attr_{key}"] = value

    image_tags = {'picture', 'photo', 'optionalImages', 'image', 'img'}

    for child in offer_elem:
        if child.tag in image_tags:
            continue
            
        for key, value in child.attrib.items():
            column_name = f"{child.tag}_{key}"
            if column_name in offer_data:
                offer_data[column_name] += f"///{value}"
            else:
                offer_data[column_name] = value
        
        if child.text and child.text.strip():
            if child.tag in offer_data:
                offer_data[child.tag] += f"///{child.text.strip()}"
            else:
                offer_data[child.tag] = child.text.strip()
        
        if child.tag == 'stock':
            for stock_child in child:
                stock_key = stock_child.tag
                if stock_child.text and stock_child.text.strip():
                    offer_data[stock_key] = stock_child.text.strip()
                for attr_key, attr_value in stock_child.attrib.items():
                    offer_data[f"{stock_key}_{attr_key}"] = attr_value

    processed_elements = {offer_elem}
    
    for child in offer_elem:
        processed_elements.add(child)
    
    for elem in offer_elem.iter():
        if elem in processed_elements:
            continue

        if elem.tag in image_tags:
            continue

        for key, value in elem.attrib.items():
            column_name = f"{elem.tag}_{key}"
            if column_name not in offer_data:
                offer_data[column_name] = value
        
        if elem.text and elem.text.strip():
            if elem.tag not in offer_data:
                offer_data[elem.tag] = elem.text.strip()

    if format_type == 'offer':
        cid_elem = offer_elem.find('./categoryId')
        if cid_elem is not None and cid_elem.text:
            cid = cid_elem.text.strip()
        else:
            cid_elem = offer_elem.find('.//categoryId')
            cid = cid_elem.text.strip() if cid_elem is not None and cid_elem.text else 'Undefined'

        category_path = build_category_path(cid)
        offer_data['category_path'] = category_path

        offer_data['categoryId'] = cid
    else:
        offer_data['category_path'] = 'Undefined'
        offer_data['categoryId'] = 'Undefined'
    excluded = ['param'] if format_type == 'offer' else ['photos', 'fabric', 'features', 'options']
    image_tags = {'picture', 'photo', 'optionalImages', 'image', 'img'}

    for child in offer_elem:
        if child.tag not in excluded and child.tag not in image_tags:
            val = child.text or ''
            if child.tag.replace('.', '', 1).isdigit():
                val = val.replace('.', ',')
            if child.tag == 'name':
                val = sanitize_name(val)
            if child.tag == 'Size' and '?' in val:
                val = val.replace('?', '').strip()
            
            if child.tag not in offer_data or not offer_data[child.tag] or offer_data[child.tag] == 'Undefined':
                offer_data[child.tag] = val
    all_images = set()
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']

    for selector in ['.//photo', './/picture', './/image', './/img', './/optionalImages']:
        for img_elem in offer_elem.findall(selector):
            if img_elem.text and img_elem.text.strip():
                image_url = img_elem.text.strip()
                if (any(image_url.lower().endswith(ext) for ext in image_extensions) 
                    or 'img/' in image_url.lower() 
                    or image_url.startswith('http')):
                    all_images.add(image_url)

    for elem in offer_elem.iter():
        for attr_name, attr_value in elem.attrib.items():
            if ('image' in attr_name.lower() or 'photo' in attr_name.lower()) and attr_value:
                if (any(attr_value.lower().endswith(ext) for ext in image_extensions)
                    or attr_value.startswith('http')):
                    all_images.add(attr_value)

    all_images = list(all_images)

    if all_images:
        offer_data['pictures'] = "///".join(all_images)
        offer_data['debug_images_found'] = str(len(all_images))
    else:
        offer_data['pictures'] = ""
        offer_data['debug_images_found'] = "0"
    params = {}
    if format_type == 'offer':
        for param_elem in offer_elem.findall('.//param'):
            key = param_elem.get('name')
            if not key:
                continue
            val = param_elem.text or ''
            if ('размер' in key.lower() or 'size' in key.lower()) or (
                    '?' in val and
                (val.replace('?', '').strip().isdigit() or any(c.isdigit()
                                                               for c in val))):
                val = val.replace('?', '').strip()

            clean_key = key.strip()

            if clean_key.replace('.', '', 1).isdigit():
                continue

            if clean_key in params:
                params[clean_key] += f", {val}"
            else:
                params[clean_key] = val

        for elem in offer_elem.iter():
            if elem.tag.startswith('param_name_'):
                key = elem.tag
                val = elem.text or ''

                if ('размер' in key.lower() or 'size' in key.lower()) or (
                        '?' in val and
                    (val.replace('?', '').strip().isdigit() or any(c.isdigit()
                                                                   for c in val))):
                    val = val.replace('?', '').strip()

                if key in offer_data:
                    offer_data[key] += f", {val}"
                else:
                    offer_data[key] = val
    else:
        fab = offer_elem.find('.//fabric')
        if fab is not None:
            for elem in fab.findall('.//feature'):
                name = elem.get('name')
                if not name:
                    continue
                key = f"fabric_{name}"
                val = elem.text or ''
                if key in params:
                    params[key] += f", {val}"
                else:
                    params[key] = val
        feats = offer_elem.find('.//features')
        if feats is not None:
            for elem in feats.findall('.//feature'):
                name = elem.get('name')
                if not name:
                    continue
                key = f"feature_{name}"
                val = elem.text or ''
                if key in params:
                    params[key] += f", {val}"
                else:
                    params[key] = val
    offer_data.update(params)
    desc_elem = offer_elem.find('.//description') if format_type == 'offer' else offer_elem.find('.//name')
    if desc_elem is not None and desc_elem.text:
        offer_data['description'] = clean_description(desc_elem.text)
    else:
        alt_desc_tags = ['.//desc', './/descr', './/description_full', './/full_description']
        for tag in alt_desc_tags:
            desc_elem = offer_elem.find(tag)
            if desc_elem is not None and desc_elem.text:
                offer_data['description'] = clean_description(desc_elem.text)
                break
        else:
            offer_data['description'] = ""

    if 'available' not in offer_data:
        offer_data['available'] = '1'

    return offer_data


async def process_offers_chunk(offers_chunk, build_category_path, format_type):
    offers = []
    for elem in offers_chunk:
        offers.append(await process_offer(elem, build_category_path,
                                          format_type))
    return {"offers": offers}


async def process_xml_data(xml_data, source_name):
    print(f"Processing data from: {source_name}")
    print(f"Data length: {len(xml_data)} characters")
    
    # Debug: Show first 500 characters of the response
    print(f"First 500 characters of response: {xml_data[:500]}")

    data_lower = xml_data.strip().lower()
    if data_lower.startswith('<html') or data_lower.startswith('<!doctype html'):
        raise ValueError(f"Data contains HTML page instead of XML/YML file.")

    # Improved error detection - only trigger if it's clearly an error page
    if (('error' in data_lower or 'not found' in data_lower or '404' in data_lower) and 
        not xml_data.strip().startswith('<?xml') and 
        not any(tag in data_lower for tag in ['<yml_catalog', '<catalog', '<offers', '<products', '<shop'])):
        print(f"Error detected in response. Content preview: {xml_data[:200]}")
        raise ValueError(f"Data contains error page.")

    print("Processing as XML file")

    if not xml_data.strip().startswith('<'):
        raise ValueError(f"Received data is not an XML file. Make sure the URL leads to a valid XML or YML file.")

    if not any(tag in xml_data.lower() for tag in ['<yml_catalog', '<catalog', '<offers', '<products', '<shop']):
        raise ValueError(f"XML file does not contain expected elements (yml_catalog, catalog, offers, products, shop). This may not be a YML product catalog.")

    try:
        print("Starting XML parsing...")
        if xml_data.startswith('\ufeff'):
            xml_data = xml_data[1:]
            print("Removed BOM")

        import re
        original_length = len(xml_data)
        xml_data = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_data)
        if len(xml_data) != original_length:
            print(f"Removed {original_length - len(xml_data)} control characters")

        root = ET.fromstring(xml_data)
        print("XML parsed successfully")
    except ET.ParseError as e:
        print(f"Initial XML parsing failed: {str(e)}")
        try:
            print("Attempting to fix XML issues...")
            xml_data = re.sub(r'&(?![a-zA-Z0-9#]+;)', '&amp;', xml_data)

            xml_data = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]', '', xml_data)

            root = ET.fromstring(xml_data)
            print("XML parsing successful after cleanup")
        except ET.ParseError as e2:
            print(f"XML parsing failed even after cleanup: {str(e2)}")
            error_location = str(e2)
            if "line" in error_location and "column" in error_location:
                raise ValueError(f"XML file contains syntax errors. {error_location}. Make sure the file is properly formatted and contains valid XML.")
            else:
                raise ValueError(f"XML file is corrupted or contains invalid characters: {str(e2)}")
        except Exception as e3:
            print(f"Unexpected error during XML cleanup: {str(e3)}")
            raise ValueError(f"Error processing XML file: {str(e3)}")
    if root.findall('.//offer'):
        format_type = 'offer'
    elif root.findall('.//product'):
        format_type = 'product'
    else:
        raise ValueError("Unsupported XML format")
    categories = {}
    parents = {}
    if format_type == 'offer':
        for cat in root.findall('.//category'):
            cid = cat.get('id')
            pid = cat.get('parentId')
            categories[cid] = cat.text or 'Undefined'
            if pid:
                parents[cid] = pid

        def build_category_path(cid):
            if not cid or cid == 'Undefined':
                return 'Undefined'

            path = []
            current_cid = cid
            visited = set()
            
            while current_cid and current_cid in categories and current_cid not in visited:
                visited.add(current_cid)
                category_name = categories.get(current_cid, 'Undefined')
                if category_name and category_name != 'Undefined':
                    path.append(category_name)
                current_cid = parents.get(current_cid)

            if not path:
                if cid in categories:
                    return categories[cid]
                return 'Undefined'

            return '///'.join(reversed(path))
    else:

        def build_category_path(cid):
            return 'Undefined'

    tasks = []
    async for chunk in split_offers(xml_data, 100, format_type):
        tasks.append(
            asyncio.create_task(
                process_offers_chunk(chunk, build_category_path, format_type)))
    results = await asyncio.gather(*tasks)
    combined = {
        "offers": [],
        "categories": categories,
        "category_parents": parents
    }
    for res in results:
        combined["offers"].extend(res["offers"])
    os.makedirs("data_files", exist_ok=True)

    if source_name.startswith('http'):
        domain = urlparse(source_name).netloc.replace("www.", "")
        filename = f"{domain.replace('.','_')}.csv"
    else:
        base_name = os.path.splitext(source_name)[0]
        filename = f"{base_name.replace('.','_').replace(' ','_')}.csv"

    path = os.path.join("data_files", filename)
    category_names = set()
    for row in combined["offers"]:
        category_names.update(k for k in row.keys() if k is not None)
    excluded = [
        'param', 'param_name', 'param_unit', 'delivery-options',
        'delivery_options', 'delivery_options_xml', 'option_cost',
        'option_days', 'option_order-before'
    ]
    important = [
        'Размер', 'delivery_options@cost', 'delivery_options@days',
        'delivery_options@order-before'
    ]
    fields = [
        col for col in sorted(category_names)
        if (col not in excluded and not col.replace('.', '', 1).isdigit()) or col in important
    ]
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for offer in combined["offers"]:
            filtered = {k: v for k, v in offer.items() if k not in excluded}
            row_data = {}
            for field in fields:
                if field in filtered:
                    v = filtered[field]
                    if isinstance(v, str):
                        if ('размер' in field.lower() or 'size' in field.lower() or field == 'Размер'):
                            v = v.replace('?', '').strip()
                        if field == 'ROOM_TYPE' or field == 'PURPOSE':
                            v = v.replace(', ', '///')
                        v = v.replace('"', '""').replace('\n', ' ').replace('\r', ' ').strip()
                    row_data[field] = v
            writer.writerow(row_data)
    return path, filename

async def process_link(link_url, base_url):
    print(f"Fetching data from: {link_url}")

    async with aiohttp.ClientSession() as session:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/xml,text/xml,*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://nonton.ru/',
            'Origin': 'https://nonton.ru',
            'DNT': '1',
            'X-Requested-With': 'XMLHttpRequest'
        }

        async with session.get(link_url, headers=headers, allow_redirects=True) as initial_response:
            if initial_response.status == 200:
                sample_content = await initial_response.text()
                if sample_content.strip().startswith('<?xml') or sample_content.strip().startswith('<yml_catalog'):
                    print(f"Found valid XML content, proceeding with processing")
                    path, filename = await process_xml_data(sample_content, link_url)
                    return path, f"{base_url}/download/data_files/{filename}"

        async with session.head(link_url, headers=headers, allow_redirects=True) as response:
            content_type = response.headers.get('content-type', '').lower()
            print(f"Response status: {response.status}")
            print(f"Content-Type: {content_type}")
            print(f"Final URL after redirects: {response.url}")

            if response.status == 404:
                raise ValueError(f"File not found (404). URL: {link_url} is not available.")
            elif response.status == 403:
                raise ValueError(f"Access denied (403). Authorization may be required or file is protected.")
            elif response.status >= 400:
                raise ValueError(f"Server error ({response.status}). Check URL correctness.")

            if 'text/html' in content_type and 'xml' not in content_type:
                async with session.get(link_url, headers=headers, allow_redirects=True) as get_response:
                    sample_content = await get_response.text()
                    sample_preview = sample_content[:500].lower()

                    if '404' in sample_preview or 'not found' in sample_preview:
                        raise ValueError(f"File not found on server (404). URL: {link_url} is not available.")
                    elif 'access denied' in sample_preview or 'forbidden' in sample_preview or 'login' in sample_preview:
                        raise ValueError(f"File access is restricted. Authorization may be required or file is password protected.")
                    elif 'robots' in sample_preview and 'noindex' in sample_preview and not (sample_content.strip().startswith('<?xml') or sample_content.strip().startswith('<yml_catalog')):
                        strategies = [
                            {
                                'name': 'Chrome browser simulation',
                                'headers': {
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                                    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                                    'Accept-Encoding': 'gzip, deflate, br',
                                    'Referer': f'https://{urlparse(link_url).netloc}/',
                                    'Origin': f'https://{urlparse(link_url).netloc}',
                                    'Sec-Fetch-Dest': 'document',
                                    'Sec-Fetch-Mode': 'navigate',
                                    'Sec-Fetch-Site': 'same-origin',
                                    'Sec-Fetch-User': '?1',
                                    'Upgrade-Insecure-Requests': '1',
                                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                                    'sec-ch-ua-mobile': '?0',
                                    'sec-ch-ua-platform': '"Windows"',
                                    'Cache-Control': 'max-age=0'
                                }
                            },
                            {
                                'name': 'Firefox browser simulation',
                                'headers': {
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                                    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
                                    'Accept-Encoding': 'gzip, deflate, br',
                                    'Referer': f'https://{urlparse(link_url).netloc}/',
                                    'DNT': '1',
                                    'Connection': 'keep-alive',
                                    'Upgrade-Insecure-Requests': '1',
                                    'Sec-Fetch-Dest': 'document',
                                    'Sec-Fetch-Mode': 'navigate',
                                    'Sec-Fetch-Site': 'same-origin',
                                    'Sec-Fetch-User': '?1'
                                }
                            }
                        ]

                        for strategy in strategies:
                            try:
                                print(f"Trying {strategy['name']} to bypass robot blocking...")
                                await asyncio.sleep(3)

                                async with session.get(link_url, headers=strategy['headers'], allow_redirects=True) as browser_response:
                                    if browser_response.status == 200:
                                        browser_content_type = browser_response.headers.get('content-type', '').lower()
                                        if 'xml' in browser_content_type or 'application/xml' in browser_content_type:
                                            print(f"Successfully bypassed robot blocking with {strategy['name']}")
                                            return

                                        test_content = await browser_response.text()
                                        if test_content.strip().startswith('<?xml') or test_content.strip().startswith('<yml_catalog'):
                                            print(f"Found XML content with {strategy['name']} despite incorrect Content-Type")
                                            path, filename = await process_xml_data(test_content, link_url)
                                            return path, f"{base_url}/download/data_files/{filename}"

                            except Exception as e:
                                print(f"{strategy['name']} failed: {e}")
                                continue

                        raise ValueError(f"File is blocked for robots. All bypass attempts failed. Recommendations:\n1. Download file manually through browser\n2. Upload through website form\n3. Contact site owner for direct link")
                    elif 'cloudflare' in sample_preview or 'ddos' in sample_preview:
                        raise ValueError(f"Site is protected by DDoS protection system. Try again later or contact site owner.")
                    else:
                        raise ValueError(f"Server returns HTML page (Content-Type: {content_type}) instead of XML file. Check URL correctness and make sure it leads directly to XML/YML file.")

    try:
        async with session.get(link_url, allow_redirects=True) as response:
            if response.status == 200:
                data = await response.text()
                if data and data.strip():
                    path, filename = await process_xml_data(data, link_url)
                    return path, f"{base_url}/download/data_files/{filename}"
    except Exception as e:
        print(f"Final fetch attempt failed: {e}")
    
    raise ValueError(f"Unable to fetch valid XML data from {link_url}")


@app.get("/")
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process_file")
async def process_file_upload(file: UploadFile = File(...)):
    try:
        content = await file.read()

        try:
            xml_data = content.decode('utf-8')
        except UnicodeDecodeError:
            for encoding in ['windows-1251', 'latin1', 'iso-8859-1', 'cp1252']:
                try:
                    xml_data = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                xml_data = content.decode('utf-8', errors='replace')

        print(f"Processing uploaded file: {file.filename}")
        print(f"File size: {len(xml_data)} characters")

        path, filename = await process_xml_data(xml_data, file.filename or "uploaded_file")

        return {
            "file_url": f"/download/data_files/{os.path.basename(path)}",
            "status": "completed",
            "filename": os.path.basename(path)
        }

    except Exception as e:
        print(f"Error processing uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/process_link")
async def process_link_post(link_data: LinkData, request: Request):
    print(f"Processing link: {link_data.link_url}")
    try:
        path, url = await process_link(link_data.link_url,
                                       str(request.url).rstrip(request.url.path))
        if path:
            resp = {
                "file_url": url,
                "preset_id": link_data.preset_id,
                "status": "completed"
            }
            if link_data.return_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(link_data.return_url,
                                                json=resp) as res:
                            res.raise_for_status()
                except Exception as callback_error:
                    print(f"Callback error: {callback_error}")
            return resp
        raise HTTPException(status_code=500, detail="Failed to process the link")
    except ValueError as ve:
        print(f"ValueError occurred: {str(ve)}")
        raise HTTPException(status_code=400, detail=f"Data processing error: {str(ve)}")
    except Exception as e:
        print(f"Unexpected error occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/status/{preset_id}")
async def check_processing_status(preset_id: str):
    return {
        "status":
        "completed",
        "file_url":
        "https://magic-xml.replit.app/download/data_files/your_file.csv"
    }


@app.get("/download/data_files/{filename}")
def download_csv(filename: str):
    file_path = os.path.join("data_files", filename)
    if os.path.isfile(file_path):
        return FileResponse(path=file_path,
                            filename=filename,
                            media_type='application/octet-stream')
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="localhost", port=8080, reload=True)
