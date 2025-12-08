from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import time
import xml.etree.ElementTree as ET
import csv
import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import pandas as pd
from io import BytesIO
import logging
import logging.handlers
import hashlib

os.makedirs("logs", exist_ok=True)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = logging.handlers.RotatingFileHandler('logs/app.log', maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.ERROR)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

conversion_logger = logging.getLogger('conversion')
conversion_logger.setLevel(logging.INFO)
conversion_handler = logging.handlers.RotatingFileHandler('logs/conversions.log', maxBytes=5 * 1024 * 1024, backupCount=3)
conversion_handler.setFormatter(formatter)
conversion_logger.addHandler(conversion_handler)

security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)
security_handler = logging.handlers.RotatingFileHandler('logs/security.log', maxBytes=5 * 1024 * 1024, backupCount=3)
security_handler.setFormatter(formatter)
security_logger.addHandler(security_handler)

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

user_sessions = {}


def add_user_session(ip, user_id, user_agent=""):
    session_key = f"{ip}_{user_id}"
    user_sessions[session_key] = {
        "ip": ip,
        "user_id": user_id,
        "user_agent": user_agent,
        "last_seen": datetime.now(),
        "file_count": 0,
        "has_adblock": False,
        "adblock_conversions": 0
    }


def get_user_file_limit(user_id):
    """Возвращает лимит файлов для пользователя"""
    session_key = None
    for key in user_sessions:
        if key.endswith(f"_{user_id}"):
            session_key = key
            break

    if session_key and user_sessions[session_key].get("file_count", 0) > 50:
        return 50
    return 100


def increment_user_file_count(user_id, ip):
    session_key = f"{ip}_{user_id}"
    if session_key in user_sessions:
        user_sessions[session_key]["file_count"] += 1


def cleanup_old_sessions():
    """Удаляет сессии старше 1 часа"""
    now = datetime.now()
    expired_sessions = []
    for session_key, session_data in user_sessions.items():
        last_seen = session_data.get("last_seen")
        if last_seen and (now - last_seen).total_seconds() > 3600:
            expired_sessions.append(session_key)

    for session_key in expired_sessions:
        del user_sessions[session_key]

    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")


class LinkData(BaseModel):
    link_url: str
    return_url: str = ""
    preset_id: str = ""


def clean_description(description):
    if not description:
        return ''
    import html
    decoded = description
    for _ in range(3):
        prev = decoded
        decoded = html.unescape(decoded)
        if prev == decoded:
            break
    try:
        soup = BeautifulSoup(decoded, 'html5lib')
    except Exception:
        try:
            soup = BeautifulSoup(decoded, 'lxml')
        except Exception:
            soup = BeautifulSoup(decoded, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text).strip()
    if text:
        return f'<p>{text}</p>'
    return ''


def sanitize_name(name):
    if not name:
        return ""
    sanitized = re.sub(r'[^\w\s\-\(\)\[\]\/\\,\.;:!?\'"«»„""`~@#$%^&*+=<>|№°]', '', name)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = re.sub(r'\(\s*([^)]+)\s*\)', r'(\1)', sanitized)
    return sanitized.strip()


def remove_duplicates_from_delimited_string(value, delimiter='///'):
    if not value:
        return ""
    items = [item.strip() for item in value.split(delimiter) if item.strip()]
    unique_items = []
    for item in items:
        if item not in unique_items:
            unique_items.append(item)
    return delimiter.join(unique_items)


def extract_image_urls(raw_val: str):
    if not raw_val:
        return []
    urls = re.findall(r'https?://[^\s,]+', raw_val)
    if not urls:
        parts = re.split(r'[,\s]+', raw_val)
        urls = [p for p in parts if p.startswith('http')]
    clean = []
    for u in urls:
        u = u.strip().rstrip(',').rstrip()
        if u:
            clean.append(u)
    return clean


async def split_offers(xml_data, chunk_size, format_type):
    root = ET.fromstring(xml_data)
    if format_type == 'offer':
        offers = root.findall('.//offer')
        if not offers:
            offers = root.findall('.//предложение')
    elif format_type == 'product':
        offers = root.findall('.//product')
    elif format_type == 'russian':
        offers = root.findall('.//ЭлементСправочника')
    elif format_type == 'service':
        offers = root.findall('.//service') if root.findall('.//service') else [root]
    elif format_type == 'item':
        offers = root.findall('.//item')
    else:
        offers = []
    for i in range(0, len(offers), chunk_size):
        yield offers[i:i + chunk_size]


async def process_offer(offer_elem, build_category_path, format_type, categories=None):
    offer_data = {}
    for key, value in offer_elem.attrib.items():
        offer_data[f"attr_{key}"] = value
    image_tags = {'picture', 'photo', 'optionalImages', 'image', 'images', 'img'}
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
                existing_value = offer_data[child.tag] + f"///{child.text.strip()}"
                offer_data[child.tag] = remove_duplicates_from_delimited_string(existing_value)
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
        if cid_elem is None:
            cid_elem = offer_elem.find('./идентификатор_категории')
        if cid_elem is not None and cid_elem.text:
            cid = cid_elem.text.strip()
        else:
            cid_elem = offer_elem.find('.//categoryId')
            if cid_elem is None:
                cid_elem = offer_elem.find('.//идентификатор_категории')
            cid = cid_elem.text.strip() if cid_elem is not None and cid_elem.text else 'Undefined'
        cat_elem = offer_elem.find('./category')
        if cat_elem is not None and cat_elem.text:
            cid = cat_elem.text.strip()
        category_path = build_category_path(cid)
        offer_data['category_path'] = category_path
        if cid and categories and cid in categories:
            offer_data['category'] = categories[cid]
        else:
            offer_data['category'] = category_path
        offer_data['categoryId'] = cid
    else:
        offer_data['category_path'] = 'Undefined'
        offer_data['category'] = 'Undefined'
        offer_data['categoryId'] = 'Undefined'
    excluded = ['param'] if format_type == 'offer' else ['photos', 'fabric', 'features', 'options']
    image_tags = {'picture', 'photo', 'optionalImages', 'image', 'images', 'img'}
    for child in offer_elem:
        if child.tag not in excluded and child.tag not in image_tags:
            val = child.text or ''
            if child.tag.replace('.', '', 1).isdigit():
                val = val.replace('.', ',')
            field_name = child.tag
            if child.tag == 'name' or child.tag == 'модель':
                val = sanitize_name(val)
                field_name = 'name'
            elif child.tag == 'цена':
                field_name = 'price'
            elif child.tag == 'описание':
                field_name = 'description'
            elif child.tag == 'продавец':
                field_name = 'vendor'
            elif child.tag == 'код_поставщика':
                field_name = 'vendorCode'
            elif child.tag == 'количество':
                field_name = 'quantity'
            elif child.tag == 'штрихкод':
                field_name = 'barcode'
            elif child.tag == 'изображение':
                field_name = 'picture'
            elif child.tag == 'гарантия_производителя':
                field_name = 'manufacturer_warranty'
            if child.tag == 'Size' and '?' in val:
                val = val.replace('?', '').strip()
            if field_name not in offer_data or not offer_data[field_name] or offer_data[field_name] == 'Undefined':
                offer_data[field_name] = val
    if 'vendor' in offer_data and offer_data['vendor'] and 'Brand' not in offer_data:
        offer_data['Brand'] = offer_data['vendor']
    params = {}
    if format_type == 'offer':
        for param_elem in offer_elem.findall('.//param'):
            key = param_elem.get('name')
            if not key:
                continue
            val = param_elem.text or ''
            if ('размер' in key.lower() or 'size' in key.lower()) or (
                    '?' in val and (val.replace('?', '').strip().isdigit() or any(c.isdigit() for c in val))):
                val = val.replace('?', '').strip()
            clean_key = key.strip()
            if clean_key.replace('.', '', 1).isdigit():
                continue
            if clean_key in params:
                params[clean_key] += f"///{val}"
            else:
                params[clean_key] = val
        for param_elem in offer_elem.findall('.//параметр'):
            key = param_elem.get('название') or param_elem.get('имя') or param_elem.get('name')
            if not key:
                continue
            val = param_elem.text or ''
            if ('размер' in key.lower() or 'size' in key.lower()) or (
                    '?' in val and (val.replace('?', '').strip().isdigit() or any(c.isdigit() for c in val))):
                val = val.replace('?', '').strip()
            clean_key = key.strip()
            if clean_key.replace('.', '', 1).isdigit():
                continue
            if clean_key in params:
                params[clean_key] += f"///{val}"
            else:
                params[clean_key] = val
        for elem in offer_elem.iter():
            if elem.tag.startswith('param_name_'):
                key = elem.tag
                val = elem.text or ''
                if ('размер' in key.lower() or 'size' in key.lower()) or (
                        '?' in val and (val.replace('?', '').strip().isdigit() or any(c.isdigit() for c in val))):
                    val = val.replace('?', '').strip()
                if key in offer_data:
                    offer_data[key] += f"///{val}"
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
                    params[key] += f"///{val}"
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
                    params[key] += f"///{val}"
                else:
                    params[key] = val
    offer_data.update(params)
    
    # ============================================================
    # ДОБАВЛЕНО: Обработка delivery-options
    # ============================================================
    delivery_options = offer_elem.find('.//delivery-options')
    if delivery_options is not None:
        for option in delivery_options.findall('option'):
            cost = option.get('cost', '')
            days = option.get('days', '')
            order_before = option.get('order-before', '')
            if cost:
                offer_data['delivery_options@cost'] = cost
            if days:
                offer_data['delivery_options@days'] = days
            if order_before:
                offer_data['delivery_options@order-before'] = order_before
    
    # ============================================================
    # ДОБАВЛЕНО: Обработка pickup-options
    # ============================================================
    pickup_options = offer_elem.find('.//pickup-options')
    if pickup_options is not None:
        for option in pickup_options.findall('option'):
            cost = option.get('cost', '')
            days = option.get('days', '')
            order_before = option.get('order-before', '')
            if cost:
                offer_data['pickup_options@cost'] = cost
            if days:
                offer_data['pickup_options@days'] = days
            if order_before:
                offer_data['pickup_options@order-before'] = order_before
    # ============================================================
    
    main_images = []
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
    for tag_name in ['picture', 'photo', 'image', 'img', 'optionalImages', 'images']:
        for img_elem in offer_elem.findall(f'./{tag_name}'):
            if img_elem.text and img_elem.text.strip():
                url = img_elem.text.strip()
                if url.startswith('http'):
                    main_images.append(url)
    for selector in ['.//photo', './/picture', './/image', './/img', './/optionalImages', './/images']:
        for img_elem in offer_elem.findall(selector):
            if img_elem.text and img_elem.text.strip():
                url = img_elem.text.strip()
                if url.startswith('http') and url not in main_images:
                    main_images.append(url)
    extra_images = []
    for param_elem in offer_elem.findall('.//param'):
        name_attr = (param_elem.get('name') or '').strip()
        if name_attr in ['Картинки', 'картинки', 'Картинка', 'картинка']:
            extra_images.extend(extract_image_urls(param_elem.text or ''))
    ordered_images = []
    for u in main_images + extra_images:
        if u and u not in ordered_images:
            ordered_images.append(u)
    if ordered_images:
        offer_data['pictures'] = '///'.join(ordered_images)
    else:
        offer_data['pictures'] = ''
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


async def process_russian_xml(root):
    offers = []
    for element in root.findall('.//ЭлементСправочника'):
        offer_data = {}
        for child in element:
            if child.tag == 'ТЧ':
                tc_name = child.get('ИмяТабличнойЧасти', 'UnknownTC')
                tc_data = []
                for tc_element in child.findall('ЭлементТЧ'):
                    tc_row = {}
                    for tc_child in tc_element:
                        if tc_child.text and tc_child.text.strip():
                            tc_row[f"{tc_name}_{tc_child.tag}"] = tc_child.text.strip()
                    if tc_row:
                        tc_data.append(tc_row)
                if tc_data:
                    if tc_name == 'Остатки':
                        stock_info = []
                        total_stock = 0
                        for row in tc_data:
                            warehouse = row.get(f'{tc_name}_СкладНаименование', '')
                            quantity = row.get(f'{tc_name}_КоличествоОстаток', '0')
                            try:
                                qty_num = float(quantity)
                                total_stock += qty_num
                                if qty_num > 0:
                                    stock_info.append(f"{warehouse}: {quantity}")
                            except (ValueError, TypeError):
                                if quantity != '0':
                                    stock_info.append(f"{warehouse}: {quantity}")
                        offer_data['available'] = '1' if total_stock > 0 else '0'
                        offer_data['stock_total'] = str(total_stock)
                        offer_data['stock_details'] = "///".join(stock_info)
                    elif tc_name == 'Цены':
                        for row in tc_data:
                            price_name = row.get(f'{tc_name}_Наименование', '')
                            price_value = row.get(f'{tc_name}_Значение', '')
                            if price_name and price_value:
                                if price_name == 'Цена':
                                    offer_data['price'] = price_value
                                elif price_name == 'ЦенаСкидка' and price_value != '0':
                                    offer_data['oldprice'] = offer_data.get('price', '')
                                    offer_data['price'] = price_value
                    elif tc_name == 'Материалы':
                        values = []
                        id_values = []
                        for row in tc_data:
                            name = row.get(f'{tc_name}_Наименование', '')
                            if name and name not in values:
                                values.append(name)
                            material_id = row.get(f'{tc_name}_ID_Материала', '')
                            if material_id and material_id not in id_values:
                                id_values.append(material_id)
                        if values:
                            offer_data[tc_name.lower()] = "///".join(values)
                        if id_values:
                            existing_ids = offer_data.get('ID_Материала', '').split('///')
                            existing_ids = [id.strip() for id in existing_ids if id.strip()]
                            all_ids = existing_ids + id_values
                            unique_ids = []
                            for id_val in all_ids:
                                if id_val not in unique_ids:
                                    unique_ids.append(id_val)
                            offer_data['ID_Материала'] = "///".join(unique_ids)
                    elif tc_name in ['Стили', 'ГруппыСайта']:
                        values = []
                        for row in tc_data:
                            name = row.get(f'{tc_name}_Наименование', '')
                            if name and name not in values:
                                values.append(name)
                        if values:
                            if tc_name == 'ГруппыСайта':
                                offer_data['category_path'] = "///".join(values)
                                offer_data['categoryId'] = values[0] if values else 'Undefined'
                            else:
                                offer_data[tc_name.lower()] = "///".join(values)
            else:
                if child.text and child.text.strip():
                    value = child.text.strip()
                    if child.tag == 'ОписаниеДляСайта' or child.tag == 'description':
                        value = clean_description(value)
                        offer_data['description'] = value
                    elif child.tag == 'Наименование':
                        value = sanitize_name(value)
                        offer_data['name'] = value
                    elif child.tag == 'ПолноеНазваниеСайт':
                        offer_data['full_name'] = sanitize_name(value)
                    elif child.tag == 'Артикул':
                        offer_data['Артикул'] = value
                        offer_data['vendor'] = value
                        offer_data['vendorCode'] = value
                    elif child.tag == 'ID_Материала':
                        offer_data['ID_Материала'] = value
                    elif child.tag in ['Глубина', 'Ширина', 'Высота', 'Вес']:
                        offer_data[child.tag.lower()] = value
                    elif child.tag == 'Цвет':
                        offer_data['param_Цвет'] = value
                    else:
                        offer_data[child.tag] = value
        if 'available' not in offer_data:
            offer_data['available'] = '1'
        if 'category_path' not in offer_data:
            offer_data['category_path'] = 'Undefined'
            offer_data['categoryId'] = 'Undefined'
        if 'ID' in offer_data:
            offer_data['id'] = offer_data['ID']
        for key, value in offer_data.items():
            if isinstance(value, str) and '///' in value:
                offer_data[key] = remove_duplicates_from_delimited_string(value)
        offers.append(offer_data)
    return {"offers": offers}


async def process_service_xml(root):
    offers = []
    for service_elem in root.findall('.//service'):
        service_data = {}
        for attr_name, attr_value in service_elem.attrib.items():
            service_data[attr_name] = attr_value
        for child in service_elem:
            if child.text and child.text.strip():
                service_data[child.tag] = child.text.strip()
            for attr_name, attr_value in child.attrib.items():
                column_name = f"{child.tag}_{attr_name}"
                service_data[column_name] = attr_value
        if 'available' not in service_data:
            service_data['available'] = '1'
        if 'category_path' not in service_data:
            service_data['category_path'] = service_data.get('name', 'Service')
        if 'categoryId' not in service_data:
            service_data['categoryId'] = service_data.get('id', service_data.get('sid', 'service'))
        if 'name' in service_data:
            service_data['name'] = sanitize_name(service_data['name'])
        service_data['service_type'] = 'verification_service'
        offers.append(service_data)
    return {"offers": offers}


async def process_item_xml(root):
    offers = []
    for item_elem in root.findall('.//item'):
        item_data = {}
        for child in item_elem:
            if child.tag == 'param':
                param_name = child.get('name')
                if param_name and child.text and child.text.strip():
                    item_data[f"param_{param_name}"] = child.text.strip()
            else:
                if child.text and child.text.strip():
                    value = child.text.strip()
                    if child.tag == 'name':
                        value = sanitize_name(value)
                    elif child.tag == 'description':
                        value = clean_description(value)
                    item_data[child.tag] = value
        if 'available' not in item_data:
            item_data['available'] = '1'
        if 'category_path' not in item_data:
            item_data['category_path'] = item_data.get('category', 'Undefined')
        if 'categoryId' not in item_data:
            item_data['categoryId'] = item_data.get('category', 'Undefined')
        if 'picture' in item_data:
            item_data['pictures'] = item_data['picture']
        offers.append(item_data)
    return {"offers": offers}


async def process_offers_chunk(offers_chunk, build_category_path, format_type, categories=None):
    offers = []
    for elem in offers_chunk:
        if format_type == 'product' and elem.findall('.//offer'):
            continue
        offers.append(await process_offer(elem, build_category_path, format_type, categories))
    return {"offers": offers}


async def process_csv_to_xml(csv_data, source_name, xml_format='yandex_market'):
    if source_name is None or source_name == "":
        source_name = "converted_data"
    logger.info(f"Converting CSV to XML: {source_name}")
    csv_data_clean = csv_data.strip()
    if not csv_data_clean:
        raise ValueError("CSV data is empty")
    delimiter = ';'
    sample = csv_data_clean.split('\n')[0] if '\n' in csv_data_clean else csv_data_clean
    if sample.count(',') > sample.count(';'):
        delimiter = ','
    csv_reader = csv.DictReader(csv_data_clean.split('\n'), delimiter=delimiter)
    rows = list(csv_reader)
    if not rows:
        raise ValueError("CSV file is empty or invalid")
    root = None
    if xml_format == 'yandex_market':
        root = ET.Element('yml_catalog', date=datetime.now().strftime('%Y-%m-%d %H:%M'))
        shop = ET.SubElement(root, 'shop')
        ET.SubElement(shop, 'name').text = 'Generated from CSV'
        ET.SubElement(shop, 'company').text = 'MagicXML'
        ET.SubElement(shop, 'url').text = 'https://magic-xml.replit.app'
        currencies = ET.SubElement(shop, 'currencies')
        ET.SubElement(currencies, 'currency', id='RUR', rate='1')
        categories = ET.SubElement(shop, 'categories')
        unique_categories = set()
        category_id = 1
        category_map = {}
        for row in rows:
            if 'category_path' in row and row['category_path']:
                cat_path = row['category_path']
                if cat_path not in unique_categories:
                    unique_categories.add(cat_path)
                    category_map[cat_path] = str(category_id)
                    ET.SubElement(categories, 'category', id=str(category_id)).text = cat_path
                    category_id += 1
        offers = ET.SubElement(shop, 'offers')
        for idx, row in enumerate(rows, 1):
            offer = ET.SubElement(offers, 'offer', id=str(row.get('id', idx)))
            if 'available' in row:
                offer.set('available', row['available'])
            basic_fields = ['name', 'price', 'oldprice', 'currencyId', 'vendorCode', 'vendor', 'description']
            for field in basic_fields:
                if field in row and row[field]:
                    ET.SubElement(offer, field).text = row[field]
            if 'category_path' in row and row['category_path'] in category_map:
                ET.SubElement(offer, 'categoryId').text = category_map[row['category_path']]
            if 'pictures' in row and row['pictures']:
                pictures = row['pictures'].split('///')
                for pic_url in pictures:
                    if pic_url.strip():
                        ET.SubElement(offer, 'picture').text = pic_url.strip()
            for key, value in row.items():
                if key.startswith('param_') and value:
                    param_name = key.replace('param_', '')
                    ET.SubElement(offer, 'param', name=param_name).text = value
    elif xml_format == 'simple':
        root = ET.Element('catalog')
        products = ET.SubElement(root, 'products')
        for idx, row in enumerate(rows, 1):
            product = ET.SubElement(products, 'product', id=str(row.get('id', idx)))
            for key, value in row.items():
                if value and key not in ['id']:
                    if key == 'pictures' and '///' in value:
                        images = ET.SubElement(product, 'images')
                        for img_url in value.split('///'):
                            if img_url.strip():
                                ET.SubElement(images, 'image').text = img_url.strip()
                    elif key.startswith('param_'):
                        parameters = product.find('parameters')
                        if parameters is None:
                            parameters = ET.SubElement(product, 'parameters')
                        param_name = key.replace('param_', '')
                        ET.SubElement(parameters, 'parameter', name=param_name).text = value
                    else:
                        clean_key = key.replace(' ', '_').replace('-', '_')
                        ET.SubElement(product, clean_key).text = value
    if root is None:
        raise ValueError(f"Unsupported XML format: {xml_format}")
    ET.indent(root, space="  ", level=0)
    xml_string = ET.tostring(root, encoding='unicode', xml_declaration=True)
    os.makedirs("data_files", exist_ok=True)
    if source_name and source_name.endswith('.csv'):
        base_name = source_name[:-4]
    elif source_name:
        base_name = source_name
    else:
        base_name = "converted_data"
    filename = f"{base_name}_{xml_format}.xml"
    path = os.path.join("data_files", filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml_string)
    return path, filename


async def process_csv_to_excel(csv_data, source_name):
    logger.info("=== process_csv_to_excel started ===")
    logger.info(f"Source name: {source_name}")
    logger.info(f"CSV data length: {len(csv_data)} characters")
    logger.info(f"CSV data preview (first 500 chars): {csv_data[:500]}")
    try:
        from io import StringIO
        delimiters = [';', ',', '\t']
        rows = None
        successful_delimiter = None
        for delimiter in delimiters:
            try:
                logger.info(f"Trying delimiter: '{delimiter}'")
                csv_reader = csv.DictReader(StringIO(csv_data), delimiter=delimiter)
                rows = list(csv_reader)
                logger.info(f"With delimiter '{delimiter}': found {len(rows)} rows")
                if rows and len(rows[0]) > 1:
                    successful_delimiter = delimiter
                    logger.info(f"Successfully parsed with delimiter '{delimiter}', columns: {list(rows[0].keys())}")
                    break
                elif rows:
                    logger.warning(f"Only one column found with delimiter '{delimiter}': {list(rows[0].keys())}")
            except Exception as e:
                logger.error(f"Failed to parse with delimiter '{delimiter}': {e}", exc_info=True)
                continue
        if not rows:
            error_msg = "CSV file is empty or has invalid format after trying all delimiters"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if len(rows[0]) == 1 and list(rows[0].keys())[0] == csv_data.strip().split('\n')[0]:
            error_msg = f"CSV file appears to have no column separation. Check delimiter. Used delimiter: '{successful_delimiter}'"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"Creating DataFrame with {len(rows)} rows and {len(rows[0])} columns")
        df = pd.DataFrame(rows)
        logger.info(f"DataFrame created. Shape: {df.shape}")
        logger.info(f"DataFrame columns: {list(df.columns)}")
        logger.info("Cleaning data...")
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
        original_row_count = len(df)
        df = df.dropna(how='all')
        final_row_count = len(df)
        logger.info(f"Removed {original_row_count - final_row_count} empty rows")
        if df.empty:
            error_msg = "CSV file contains no valid data after processing"
            logger.error(error_msg)
            raise ValueError(error_msg)
        os.makedirs("data_files", exist_ok=True)
        if source_name and source_name.endswith('.csv'):
            base_name = source_name[:-4]
        elif source_name:
            base_name = source_name
        else:
            base_name = "converted_data"
        filename = f"{base_name}.xlsx"
        path = os.path.join("data_files", filename)
        logger.info(f"Creating Excel file: {path}")
        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Data', index=False)
                worksheet = writer.sheets['Data']
                logger.info("Adjusting column widths...")
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value and len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except Exception:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            logger.info(f"Successfully created Excel file: {filename}")
            logger.info(f"File size: {os.path.getsize(path)} bytes")
            return path, filename
        except Exception as excel_error:
            error_msg = f"Error creating Excel file: {str(excel_error)}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error in process_csv_to_excel: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ValueError(f"Подробная ошибка конвертации CSV в Excel: {error_msg}")


async def process_excel_to_csv(excel_data, source_name):
    logger.info(f"Converting Excel to CSV: {source_name}")
    df = pd.read_excel(BytesIO(excel_data), engine='openpyxl')
    if df.empty:
        raise ValueError("Excel file is empty or invalid")
    df = df.fillna('')
    os.makedirs("data_files", exist_ok=True)
    if source_name.endswith(('.xlsx', '.xls')):
        base_name = os.path.splitext(source_name)[0]
    else:
        base_name = source_name
    filename = f"{base_name}.csv"
    path = os.path.join("data_files", filename)
    df.to_csv(path, sep=';', index=False, encoding='utf-8-sig')
    return path, filename


async def process_xml_data(xml_data, source_name, target_node="auto"):
    logger.info(f"Processing data from: {source_name}")
    logger.info(f"Data length: {len(xml_data)} characters")
    logger.info(f"First 500 characters of response: {xml_data[:500]}")
    data_lower = xml_data.strip().lower()
    if data_lower.startswith('<!doctype html') or data_lower.startswith('<html'):
        raise ValueError(f"Data contains HTML page instead of XML/YML file.")
    if (('error' in data_lower or 'not found' in data_lower or '404' in data_lower) and not xml_data.strip().startswith('<?xml')
            and not any(tag in data_lower for tag in ['<yml_catalog', '<catalog', '<offers', '<products', '<shop', '<корневой'])):
        logger.error(f"Error detected in response. Content preview: {xml_data[:200]}")
        raise ValueError(f"Data contains error page.")
    logger.info("Processing as XML file")
    xml_data_clean = xml_data.strip()
    if xml_data_clean.startswith('\ufeff'):
        xml_data_clean = xml_data_clean[1:]
    if not xml_data_clean.startswith('<'):
        raise ValueError(f"Received data is not an XML file. Make sure the URL leads to a valid XML or YML file.")
    xml_lower = xml_data.lower()
    has_yml_catalog = '<yml_catalog' in xml_lower
    has_catalog = '<catalog' in xml_lower
    has_offers = '<offers' in xml_lower or '<offer' in xml_lower
    has_products = '<products' in xml_lower or '<product' in xml_lower
    has_shop = '<shop' in xml_lower
    has_categories = '<categories' in xml_lower or '<category' in xml_lower
    has_russian_format = '<корневой' in xml_lower or '<элементсправочника' in xml_lower
    has_service_format = '<service' in xml_lower
    has_valid_structure = (has_yml_catalog or has_catalog or has_products or has_shop or has_offers or has_categories or has_russian_format or has_service_format)
    if not has_valid_structure:
        raise ValueError(f"XML file does not contain expected elements (yml_catalog, catalog, offers, products, shop, categories, Russian format, or service format). This may not be a valid XML catalog file.")
    try:
        logger.info("Starting XML parsing...")
        xml_data = xml_data_clean
        if xml_data.startswith('\ufeff'):
            xml_data = xml_data[1:]
            logger.info("Removed BOM")
        import re as _re
        original_length = len(xml_data)
        xml_data = _re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_data)
        if len(xml_data) != original_length:
            logger.info(f"Removed {original_length - len(xml_data)} control characters")
        root = ET.fromstring(xml_data)
        logger.info("XML parsed successfully")
    except ET.ParseError as e:
        logger.error(f"Initial XML parsing failed: {str(e)}", exc_info=True)
        try:
            logger.info("Attempting to fix XML issues...")
            xml_data = re.sub(r'&(?![a-zA-Z0-9#]+;)', '&amp;', xml_data)
            xml_data = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]', '', xml_data)
            root = ET.fromstring(xml_data)
            logger.info("XML parsing successful after cleanup")
        except ET.ParseError as e2:
            logger.error(f"XML parsing failed even after cleanup: {str(e2)}", exc_info=True)
            error_location = str(e2)
            if "line" in error_location and "column" in error_location:
                raise ValueError(f"XML file contains syntax errors. {error_location}. Make sure the file is properly formatted and contains valid XML.")
            else:
                raise ValueError(f"XML file is corrupted or contains invalid characters: {str(e2)}")
        except Exception as e3:
            logger.error(f"Unexpected error during XML cleanup: {str(e3)}", exc_info=True)
            raise ValueError(f"Error processing XML file: {str(e3)}")
    if target_node == "auto":
        if root.findall('.//offer') or root.findall('.//предложение'):
            format_type = 'offer'
        elif root.findall('.//product'):
            format_type = 'product'
        elif root.findall('.//ЭлементСправочника'):
            format_type = 'russian'
        elif root.findall('.//service') or root.tag == 'service':
            format_type = 'service'
        elif root.findall('.//item') or root.tag == 'export':
            format_type = 'item'
        else:
            raise ValueError("Unsupported XML format, auto-detection failed.")
    else:
        format_type = target_node
    categories = {}
    parents = {}
    if format_type == 'offer':
        for cat in root.findall('.//category'):
            cid = cat.get('id')
            pid = cat.get('parentId')
            categories[cid] = cat.text or 'Undefined'
            if pid:
                parents[cid] = pid
        for cat in root.findall('.//категория'):
            cid = cat.get('id') or cat.get('идентификатор')
            pid = cat.get('parentId') or cat.get('идентификатор_родительской_категории')
            if cid:
                categories[cid] = cat.text or 'Undefined'
                if pid:
                    parents[cid] = pid

        def build_category_path(cid):
            if not cid or cid == 'Undefined':
                return 'Undefined'
            cid_str = str(cid)
            path = []
            current_cid = cid_str
            visited = set()
            while current_cid and current_cid in categories and current_cid not in visited:
                visited.add(current_cid)
                category_name = categories.get(current_cid, 'Undefined')
                if category_name and category_name != 'Undefined':
                    path.append(category_name)
                current_cid = parents.get(current_cid)
            if not path:
                if cid_str in categories:
                    return categories[cid_str]
                return 'Undefined'
            return '///'.join(reversed(path))
    else:
        def build_category_path(cid):
            return 'Undefined'
    if format_type == 'russian':
        results = [await process_russian_xml(root)]
    elif format_type == 'service':
        results = [await process_service_xml(root)]
    elif format_type == 'item':
        results = [await process_item_xml(root)]
    else:
        tasks = []
        async for chunk in split_offers(xml_data, 100, format_type):
            tasks.append(asyncio.create_task(process_offers_chunk(chunk, build_category_path, format_type, categories)))
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
    
    # ============================================================
    # ИЗМЕНЕНО: Убраны delivery-options из excluded списка
    # ============================================================
    excluded = [
        'param', 'param_name', 'param_unit',
        'images', 'debug_images_found', 'offers'
    ]
    # ============================================================
    
    important = [
        'Размер', 'delivery_options@cost', 'delivery_options@days',
        'delivery_options@order-before'
    ]
    undefined_only_cols = set()
    for col in category_names:
        if col not in excluded:
            col_values = [offer.get(col, '') for offer in combined["offers"]]
            unique_values = set(val for val in col_values if val and val.strip())
            if not unique_values or unique_values == {'Undefined'}:
                undefined_only_cols.add(col)
    fields = [
        col for col in sorted(category_names)
        if (col not in excluded and col not in undefined_only_cols and not col.replace('.', '', 1).isdigit()) or col in important
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


async def process_link(link_url, base_url, target_node="auto"):
    logger.info(f"Fetching data from: {link_url}")
    connector = aiohttp.TCPConnector()
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
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
            'Referer': f'https://{urlparse(link_url).netloc}/',
            'DNT': '1',
            'X-Requested-With': 'XMLHttpRequest'
        }
        try:
            async with session.get(link_url, headers=headers, allow_redirects=True) as initial_response:
                if initial_response.status == 200:
                    try:
                        sample_content = await initial_response.text()
                    except UnicodeDecodeError:
                        raw_content = await initial_response.read()
                        for encoding in ['windows-1251', 'cp1252', 'latin1', 'iso-8859-1']:
                            try:
                                sample_content = raw_content.decode(encoding)
                                logger.info(f"Successfully decoded response using {encoding}")
                                break
                            except UnicodeDecodeError:
                                continue
                        else:
                            sample_content = raw_content.decode('utf-8', errors='replace')
                            logger.warning("Used UTF-8 with error replacement for decoding")
                    if sample_content.strip().startswith('<?xml') or sample_content.strip().startswith('<yml_catalog'):
                        logger.info(f"Found valid XML content, proceeding with processing")
                        path, filename = await process_xml_data(sample_content, link_url, target_node)
                        return path, f"https://magic-xml.replit.app/download/data_files/{filename}"
        except aiohttp.client_exceptions.ClientConnectorError as ce:
            logger.error(f"Connection error to {urlparse(link_url).netloc}: {str(ce)}", exc_info=True)
            if "Connect call failed" in str(ce):
                raise ValueError(f"Server {urlparse(link_url).netloc} is not accessible. The server may be down or blocking connections. Please check the URL or try again later.")
            else:
                raise ValueError(f"Connection error to {urlparse(link_url).netloc}: {str(ce)}")
        except aiohttp.client_exceptions.ConnectionTimeoutError:
            logger.error(f"Connection timeout to {urlparse(link_url).netloc}", exc_info=True)
            raise ValueError(f"Connection timeout to {urlparse(link_url).netloc}. The server is taking too long to respond. Please try again later.")
        except asyncio.TimeoutError:
            logger.error(f"Request timeout to {urlparse(link_url).netloc}", exc_info=True)
            raise ValueError(f"Request timeout to {urlparse(link_url).netloc}. The server took too long to respond (over 2 minutes). Please check the URL or try again later.")
        strategies = [{
            'name': 'Direct XML request',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/xml,text/xml,application/rss+xml,*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept-Encoding': 'gzip, deflate'
            }
        }, {
            'name': 'Yandex.Market bot simulation',
            'headers': {
                'User-Agent': 'YandexBot/3.0; +http://yandex.com/bots',
                'Accept': 'application/xml,text/xml,*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept-Encoding': 'gzip, deflate'
            }
        }, {
            'name': 'Google bot simulation',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                'Accept': 'application/xml,text/xml,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate'
            }
        }, {
            'name': 'RSS Reader simulation',
            'headers': {
                'User-Agent': 'FeedBurner/1.0 (http://www.FeedBurner.com)',
                'Accept': 'application/xml,application/rss+xml,text/xml,*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept-Encoding': 'gzip, deflate'
            }
        }, {
            'name': 'Chrome browser with XML headers',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/xml,text/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
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
                'Cache-Control': 'no-cache'
            }
        }, {
            'name': 'Firefox browser simulation',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                'Accept': 'application/xml,text/xml,application/xhtml+xml,text/html;q=0.9,image/avif,image/webp,*/*;q=0.8',
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
        }, {
            'name': 'Mobile browser simulation',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'Accept': 'application/xml,text/xml,text/html,application/xhtml+xml,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': f'https://{urlparse(link_url).netloc}/',
            }
        }, {
            'name': 'curl-like request',
            'headers': {
                'User-Agent': 'curl/7.68.0',
                'Accept': 'application/xml,text/xml,*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept-Encoding': 'gzip, deflate'
            }
        }]
        successful_response = None
        for strategy in strategies:
            try:
                logger.info(f"Trying {strategy['name']}...")
                await asyncio.sleep(2)
                async with session.get(link_url, headers=strategy['headers'], allow_redirects=True) as response:
                    logger.info(f"Response status with {strategy['name']}: {response.status}")
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        logger.info(f"Content-Type: {content_type}")
                        try:
                            sample_content = await response.text()
                        except UnicodeDecodeError:
                            raw_content = await response.read()
                            for encoding in ['windows-1251', 'cp1252', 'latin1', 'iso-8859-1']:
                                try:
                                    sample_content = raw_content.decode(encoding)
                                    logger.info(f"Successfully decoded response using {encoding} for {strategy['name']}")
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                sample_content = raw_content.decode('utf-8', errors='replace')
                                logger.warning(f"Used UTF-8 with error replacement for {strategy['name']}")
                        logger.info(f"Content preview with {strategy['name']}: {sample_content[:200]}")
                        content_lower = sample_content.strip().lower()
                        is_xml_content = (
                                sample_content.strip().startswith('<?xml') or
                                sample_content.strip().startswith('<yml_catalog') or
                                sample_content.strip().startswith('<catalog') or
                                '<offers>' in content_lower or
                                '<offer' in content_lower or
                                '<products>' in content_lower or
                                '<product' in content_lower or
                                '</yml_catalog>' in content_lower or
                                'xmlns=' in content_lower
                        )
                        is_html_content = (
                                content_lower.startswith('<!doctype html') or
                                content_lower.startswith('<html') or
                                '<title>' in content_lower or
                                '<head>' in content_lower or
                                '<body>' in content_lower
                        )
                        if is_xml_content and not is_html_content:
                            logger.info(f"Found XML content with {strategy['name']}")
                            path, filename = await process_xml_data(sample_content, link_url, target_node)
                            return path, f"https://magic-xml.replit.app/download/data_files/{filename}"
                        elif is_html_content:
                            logger.warning(f"Strategy {strategy['name']} returned HTML page")
                            continue
                        else:
                            logger.warning(f"Strategy {strategy['name']} returned unknown content type")
                        successful_response = response
                        break
                    elif response.status == 404:
                        logger.warning(f"File not found (404) with {strategy['name']}")
                        continue
                    elif response.status == 403:
                        logger.warning(f"Access denied (403) with {strategy['name']}")
                        continue
                    else:
                        logger.warning(f"Server error ({response.status}) with {strategy['name']}")
                        continue
            except asyncio.TimeoutError:
                logger.warning(f"{strategy['name']} timed out after 2 minutes")
                continue
            except Exception as e:
                logger.error(f"{strategy['name']} failed: {e}", exc_info=True)
                continue
        if successful_response is None:
            error_message = f"Не удается получить доступ к файлу. Сервер блокирует все попытки доступа (403)."
            logger.error(error_message)
            raise ValueError(error_message)
        try:
            try:
                final_content = await successful_response.text()
            except UnicodeDecodeError:
                raw_content = await successful_response.read()
                for encoding in ['windows-1251', 'cp1252', 'latin1', 'iso-8859-1']:
                    try:
                        final_content = raw_content.decode(encoding)
                        logger.info(f"Successfully decoded final content using {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    final_content = raw_content.decode('utf-8', errors='replace')
                    logger.warning("Used UTF-8 with error replacement for final content")
            if final_content.strip().startswith('<?xml') or final_content.strip().startswith('<yml_catalog'):
                path, filename = await process_xml_data(final_content, link_url, target_node)
                return path, f"https://magic-xml.replit.app/download/data_files/{filename}"
            else:
                error_message = f"Сервер возвращает HTML страницу вместо XML файла."
                logger.error(error_message)
                raise ValueError(error_message)
        except Exception as e:
            logger.error(f"Error processing final content: {str(e)}", exc_info=True)
            raise ValueError(f"Ошибка обработки содержимого файла: {str(e)}")


@app.middleware("http")
async def user_tracking_middleware(request: Request, call_next):
    start_time = time.time()
    user_ip = request.client.host
    if user_ip == "127.0.0.1" or user_ip.startswith("172."):
        user_ip = request.headers.get("x-forwarded-for", user_ip)
        if "," in user_ip:
            user_ip = user_ip.split(",")[0].strip()
    logger.info(f"Request: {request.method} {request.url.path} from {user_ip}")
    user_id = hashlib.md5(user_ip.encode()).hexdigest()[:8].upper()
    user_agent = request.headers.get("user-agent", "").lower()
    add_user_session(user_ip, user_id, user_agent)

    if len(user_sessions) > 0 and len(user_sessions) % 10 == 0:
        cleanup_old_sessions()

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} for {request.method} {request.url.path} ({process_time:.3f}s)")
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Error processing {request.method} {request.url.path} from {user_ip}: {str(e)} ({process_time:.3f}s)")
        raise


@app.get("/")
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/robots.txt")
def robots_txt():
    return FileResponse("static/robots.txt", media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    return FileResponse("static/sitemap.xml", media_type="application/xml")


@app.get("/api/user-info")
def get_user_info(request: Request):
    user_ip = request.client.host
    if user_ip == "127.0.0.1" or user_ip.startswith("172."):
        user_ip = request.headers.get("x-forwarded-for", user_ip)
        if "," in user_ip:
            user_ip = user_ip.split(",")[0].strip()
    user_id = hashlib.md5(user_ip.encode()).hexdigest()[:8].upper()
    return {"user_id": user_id, "ip_address": user_ip}


@app.post("/process_file")
async def process_file_upload(file: UploadFile = File(...), request: Request = None):
    try:
        user_ip = request.client.host
        if user_ip == "127.0.0.1" or user_ip.startswith("172."):
            user_ip = request.headers.get("x-forwarded-for", user_ip)
            if "," in user_ip:
                user_ip = user_ip.split(",")[0].strip()
        user_id = hashlib.md5(user_ip.encode()).hexdigest()[:8].upper()
        user_limit = get_user_file_limit(user_id)
        current_count = len([f for f in os.listdir("data_files") if f.startswith(user_id)]) if os.path.exists("data_files") else 0
        if current_count >= user_limit:
            raise HTTPException(status_code=429, detail=f"Превышен лимит файлов ({user_limit}).")
        MAX_FILE_SIZE = 100 * 1024 * 1024
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB")
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        try:
            file_data = content.decode('utf-8')
        except UnicodeDecodeError:
            for encoding in ['windows-1251', 'latin1', 'iso-8859-1', 'cp1252']:
                try:
                    file_data = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                file_data = content.decode('utf-8', errors='replace')
        logger.info(f"Processing uploaded file: {file.filename}")
        logger.info(f"File size: {len(file_data)} characters")
        filename = file.filename or "uploaded_file"
        if filename.lower().endswith('.csv'):
            path, output_filename = await process_csv_to_xml(file_data, filename)
        elif filename.lower().endswith(('.xlsx', '.xls')):
            path, output_filename = await process_excel_to_csv(content, filename)
        else:
            path, output_filename = await process_xml_data(file_data, filename)
        increment_user_file_count(user_id, user_ip)
        conversion_logger.info(f"File converted: {filename} by user {user_id} ({user_ip})")
        return {
            "file_url": f"/download/data_files/{os.path.basename(path)}",
            "status": "completed",
            "filename": os.path.basename(path)
        }
    except Exception as e:
        logger.error(f"Error processing uploaded file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.post("/convert_csv_to_xml")
async def convert_csv_to_xml(file: UploadFile = File(...), xml_format: str = "yandex_market"):
    try:
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")
        content = await file.read()
        try:
            csv_data = content.decode('utf-8')
        except UnicodeDecodeError:
            for encoding in ['windows-1251', 'latin1', 'iso-8859-1', 'cp1252']:
                try:
                    csv_data = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                csv_data = content.decode('utf-8', errors='replace')
        path, filename = await process_csv_to_xml(csv_data, file.filename, xml_format)
        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": xml_format
        }
    except Exception as e:
        logger.error(f"Error converting CSV to XML: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_csv_to_excel")
async def convert_csv_to_excel(file: UploadFile = File(...)):
    try:
        logger.info("=== CSV to Excel conversion started ===")
        logger.info(f"File: {file.filename}")
        logger.info(f"Content type: {file.content_type}")
        if not file.filename.lower().endswith('.csv'):
            error_msg = "Only CSV files are supported"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        if not file.filename:
            error_msg = "Filename is required"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        content = await file.read()
        logger.info(f"File content length: {len(content)} bytes")
        if len(content) == 0:
            error_msg = "File is empty"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        try:
            csv_data = content.decode('utf-8')
            logger.info("Successfully decoded as UTF-8")
        except UnicodeDecodeError as decode_error:
            logger.warning(f"UTF-8 decode failed: {decode_error}")
            for encoding in ['windows-1251', 'latin1', 'iso-8859-1', 'cp1252']:
                try:
                    csv_data = content.decode(encoding)
                    logger.info(f"Successfully decoded as {encoding}")
                    break
                except UnicodeDecodeError:
                    logger.warning(f"Failed to decode as {encoding}")
                    continue
            else:
                logger.warning("All encoding attempts failed, using UTF-8 with error replacement")
                csv_data = content.decode('utf-8', errors='replace')
        if not csv_data.strip():
            error_msg = "CSV file contains no data after decoding"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        logger.info(f"CSV data preview (first 200 chars): {csv_data[:200]}")
        try:
            path, filename = await process_csv_to_excel(csv_data, file.filename)
            logger.info(f"Conversion successful: {filename}")
            result = {
                "file_url": f"/download/data_files/{filename}",
                "status": "completed",
                "filename": filename,
                "format": "excel"
            }
            logger.info(f"Returning result: {result}")
            return result
        except Exception as conversion_error:
            error_msg = f"Error in conversion process: {str(conversion_error)}"
            logger.error(error_msg, exc_info=True)
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException as http_error:
        logger.error(f"HTTP Exception: {http_error.detail}")
        raise
    except Exception as e:
        error_msg = f"Unexpected error converting CSV to Excel: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/convert_excel_to_csv")
async def convert_excel_to_csv(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported")
        content = await file.read()
        path, filename = await process_excel_to_csv(content, file.filename)
        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "csv"
        }
    except Exception as e:
        logger.error(f"Error converting Excel to CSV: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/process_link")
async def process_link_post(link_data: LinkData, request: Request):
    logger.info(f"Processing link: {link_data.link_url}")
    logger.info(f"Target node: {link_data.preset_id}")
    try:
        target_node = link_data.preset_id if link_data.preset_id and link_data.preset_id != "" else "auto"
        logger.info(f"Using target node: {target_node}")
        path, url = await process_link(link_data.link_url, str(request.url).rstrip(request.url.path), target_node=target_node)
        if path:
            resp = {
                "file_url": url,
                "preset_id": link_data.preset_id,
                "status": "completed"
            }
            if link_data.return_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(link_data.return_url, json=resp) as res:
                            res.raise_for_status()
                except Exception as callback_error:
                    logger.error(f"Callback error: {callback_error}", exc_info=True)
            return resp
        raise HTTPException(status_code=500, detail="Failed to process the link")
    except ValueError as ve:
        logger.error(f"ValueError occurred: {str(ve)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Data processing error: {str(ve)}")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/status/{preset_id}")
async def check_processing_status(preset_id: str):
    return {
        "status": "completed",
        "file_url": "https://magic-xml.replit.app/download/data_files/your_file.csv"
    }


@app.get("/download/data_files/{filename}")
def download_csv(filename: str):
    file_path = os.path.join("data_files", filename)
    if os.path.isfile(file_path):
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream', headers={"Access-Control-Allow-Origin": "*"})
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
