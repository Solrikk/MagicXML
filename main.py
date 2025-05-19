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
import yaml

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
        return ''
    sanitized = name.replace('⌀', '')
    sanitized = re.sub(r'[^\w\s\.,-]', '', sanitized)
    return sanitized


async def fetch_url(link_url, max_retries=3):
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept':
        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0'
    }
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
                    total=90)) as session:
                async with session.get(link_url,
                                       headers=headers,
                                       allow_redirects=True) as response:
                    if response.status >= 400:
                        if attempt == max_retries - 1:
                            response.raise_for_status()
                        continue
                    raw_data = await response.read()
                    if not raw_data:
                        if attempt == max_retries - 1:
                            raise ValueError(f"Empty response from {link_url}")
                        await asyncio.sleep(2)
                        continue
                    try:
                        return raw_data.decode('utf-8')
                    except UnicodeDecodeError:
                        for encoding in [
                                'windows-1251', 'latin1', 'iso-8859-1',
                                'cp1252'
                        ]:
                            try:
                                return raw_data.decode(encoding)
                            except UnicodeDecodeError:
                                continue
                        return raw_data.decode('utf-8', errors='replace')
        except aiohttp.ClientError as e:
            if attempt == max_retries - 1:
                raise ValueError(f"Failed after {max_retries} attempts: {e}")
            await asyncio.sleep(2)
        except Exception as e:
            if attempt == max_retries - 1:
                raise ValueError(f"Error after {max_retries} attempts: {e}")
            await asyncio.sleep(2)
    raise ValueError(f"Failed to fetch URL {link_url}")


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
    for elem in offer_elem.iter():
        if elem == offer_elem:
            continue
        for key, value in elem.attrib.items():
            column_name = f"{elem.tag}_{key}"
            if column_name in offer_data:
                offer_data[column_name] += f"///{value}"
            else:
                offer_data[column_name] = value
        if elem.text and elem.text.strip():
            if elem.tag in offer_data:
                offer_data[elem.tag] += f"///{elem.text.strip()}"
            else:
                offer_data[elem.tag] = elem.text.strip()
    if format_type == 'offer':
        del_opts = offer_elem.find('.//delivery-options')
        if del_opts is not None:
            for option in del_opts.findall('.//option'):
                for key, value in option.attrib.items():
                    field_name = f"delivery_options@{key}"
                    if field_name in offer_data and not isinstance(
                            offer_data[field_name], list):
                        offer_data[field_name] = [offer_data[field_name]]
                    if field_name in offer_data:
                        offer_data[field_name].append(value)
                    else:
                        offer_data[field_name] = value
        cid_elem = offer_elem.find('.//categoryId')
        cid = cid_elem.text if cid_elem is not None else 'Undefined'
        offer_data['category_path'] = build_category_path(cid)
    else:
        offer_data['category_path'] = 'Undefined'
    excluded = ['picture', 'param', 'description'
                ] if format_type == 'offer' else [
                    'photos', 'fabric', 'features', 'options'
                ]
    for child in offer_elem:
        if child.tag not in excluded:
            val = child.text or ''
            if child.tag.replace('.', '', 1).isdigit():
                val = val.replace('.', ',')
            if child.tag == 'name':
                val = sanitize_name(val)
            if child.tag == 'Размер' and '?' in val:
                val = val.replace('?', '').strip()
            offer_data[child.tag] = val
    pic_tags = offer_elem.findall(
        './/picture') if format_type == 'offer' else offer_elem.findall(
            './/photo')
    pics = "///".join([t.text or '' for t in pic_tags]) if pic_tags else ''
    if pics:
        offer_data['pictures'] = pics
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
            if key in params:
                params[key] += f", {val}"
            else:
                params[key] = val
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
    desc_elem = offer_elem.find(
        './/description') if format_type == 'offer' else offer_elem.find(
            './/name')
    if desc_elem is not None and desc_elem.text:
        offer_data['description'] = clean_description(desc_elem.text)
    return offer_data


async def process_offers_chunk(offers_chunk, build_category_path, format_type):
    offers = []
    for elem in offers_chunk:
        offers.append(await process_offer(elem, build_category_path,
                                          format_type))
    return {"offers": offers}


async def process_link(link_url, base_url):
    data = await fetch_url(link_url)
    if not data or not data.strip():
        raise ValueError("Received empty data")
    is_yml = link_url.lower().endswith(('.yml', '.yaml'))
    if is_yml:
        if data.strip().startswith('<?xml') or data.strip().startswith(
                '<yml_catalog'):
            xml_data = data
        else:
            fixed = data.replace('\t', '    ')
            yml = yaml.safe_load(fixed)
            xml_data = dicttoxml.dicttoxml(yml,
                                           custom_root='yml_catalog',
                                           attr_type=False).decode()
    else:
        xml_data = data
    root = ET.fromstring(xml_data)
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
            path = []
            while cid:
                path.append(categories.get(cid, 'Undefined'))
                cid = parents.get(cid)
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
    domain = urlparse(link_url).netloc.replace("www.", "")
    filename = f"{domain.replace('.','_')}.csv"
    path = os.path.join("data_files", filename)
    category_names = set()
    for row in combined["offers"]:
        category_names.update(k for k in row.keys() if k is not None)
    excluded = [
        'param', 'param_name', 'param_unit', 'pictures', 'delivery-options',
        'delivery_options', 'delivery_options_xml', 'option_cost',
        'option_days', 'option_order-before'
    ]
    important = [
        'Размер', 'delivery_options@cost', 'delivery_options@days',
        'delivery_options@order-before'
    ]
    fields = [
        col for col in sorted(category_names)
        if col not in excluded or col in important
    ]
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=';')
        writer.writeheader()
        for offer in combined["offers"]:
            filtered = {k: v for k, v in offer.items() if k not in excluded}
            for k, v in filtered.items():
                if isinstance(v, str) and ('размер' in k.lower() or 'size'
                                           in k.lower() or k == 'Размер'):
                    v = v.replace('?', '').strip()
                filtered[k] = v.replace('"',
                                        '""').replace('\n',
                                                      ' ').replace('\r', ' ')
            writer.writerow(filtered)
    return path, f"{base_url}/download/data_files/{filename}"


@app.get("/")
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process_link")
async def process_link_post(link_data: LinkData, request: Request):
    path, url = await process_link(link_data.link_url,
                                   str(request.url).rstrip(request.url.path))
    if path:
        resp = {
            "file_url": url,
            "preset_id": link_data.preset_id,
            "status": "completed"
        }
        if link_data.return_url:
            async with aiohttp.ClientSession() as session:
                async with session.post(link_data.return_url,
                                        json=resp) as res:
                    res.raise_for_status()
        return resp
    raise HTTPException(status_code=500, detail="Failed to process the link")


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
