
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import xml.etree.ElementTree as ET
import csv
import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import json
import pandas as pd
from io import BytesIO
from PIL import Image
from pypdf import PdfReader
import pdfplumber
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
import logging
try:
    import tabula
except ImportError:
    tabula = None

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
    try:
        soup = BeautifulSoup(description, 'html5lib')
    except Exception:
        try:
            soup = BeautifulSoup(description, 'lxml')
        except Exception:
            soup = BeautifulSoup(description, 'html.parser')
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

def remove_duplicates_from_delimited_string(value, delimiter='///'):
    if not value:
        return ""
    items = [item.strip() for item in value.split(delimiter) if item.strip()]
    unique_items = []
    for item in items:
        if item not in unique_items:
            unique_items.append(item)
    return delimiter.join(unique_items)


async def split_offers(xml_data, chunk_size, format_type):
    root = ET.fromstring(xml_data)
    if format_type == 'offer':
        offers = root.findall('.//offer')
    elif format_type == 'product':
        offers = root.findall('.//product')
    elif format_type == 'russian':
        offers = root.findall('.//ЭлементСправочника')
    elif format_type == 'service':
        offers = root.findall('.//service') if root.findall('.//service') else [root]
    else:
        offers = []

    for i in range(0, len(offers), chunk_size):
        yield offers[i:i + chunk_size]


async def process_offer(offer_elem, build_category_path, format_type):
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
    image_tags = {'picture', 'photo', 'optionalImages', 'image', 'images', 'img'}

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

    for selector in ['.//photo', './/picture', './/image', './/img', './/optionalImages', './/images']:
        for img_elem in offer_elem.findall(selector):
            if img_elem.text and img_elem.text.strip():
                image_url = img_elem.text.strip()
                if (any(image_url.lower().endswith(ext) for ext in image_extensions)
                    or 'img/' in image_url.lower()
                    or image_url.startswith('http')):
                    all_images.add(image_url)
                    logger.info(f"Image found from tag {img_elem.tag}: {image_url}")

    if format_type == 'product':
        for offer_child in offer_elem.findall('.//offer'):
            for selector in ['.//photo', './/picture', './/image', './/img', './/optionalImages']:
                for img_elem in offer_child.findall(selector):
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

    all_images = sorted(list(all_images))

    if 'id' in offer_data:
        product_id = offer_data['id']
        logger.debug(f"Product ID {product_id}: found {len(all_images)} images")
        if all_images:
            for i, img in enumerate(all_images, 1):
                logger.debug(f"  Image {i}: {img}")

    if all_images:
        offer_data['pictures'] = "///".join(all_images)
        logger.debug(f"Final image string: {offer_data['pictures']}")
    else:
        offer_data['pictures'] = ""
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
                            except:
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


async def process_offers_chunk(offers_chunk, build_category_path, format_type):
    offers = []
    for elem in offers_chunk:
        if format_type == 'product' and elem.findall('.//offer'):
            continue
        offers.append(await process_offer(elem, build_category_path,
                                          format_type))
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
                        if 'parameters' not in [child.tag for child in product]:
                            parameters = ET.SubElement(product, 'parameters')
                        else:
                            parameters = product.find('parameters')
                        param_name = key.replace('param_', '')
                        ET.SubElement(parameters, 'parameter', name=param_name).text = value
                    else:
                        clean_key = key.replace(' ', '_').replace('-', '_')
                        ET.SubElement(product, clean_key).text = value

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
    logger.info(f"=== process_csv_to_excel started ===")
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
                original_values = df[col].value_counts().head()
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
                logger.debug(f"Cleaned column '{col}', sample values: {original_values}")

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

                workbook = writer.book
                worksheet = writer.sheets['Data']

                logger.info("Adjusting column widths...")
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value and len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
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


async def process_json_to_csv(json_data, source_name):
    logger.info(f"Converting JSON to CSV: {source_name}")

    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")

    if isinstance(data, list):
        df = pd.json_normalize(data)
    elif isinstance(data, dict):
        if any(isinstance(v, list) for v in data.values()):
            for key, value in data.items():
                if isinstance(value, list) and value:
                    df = pd.json_normalize(value)
                    break
            else:
                df = pd.json_normalize([data])
        else:
            df = pd.json_normalize([data])
    else:
        raise ValueError("Unsupported JSON structure")

    if df.empty:
        raise ValueError("No data found in JSON")

    os.makedirs("data_files", exist_ok=True)

    if source_name.endswith('.json'):
        base_name = source_name[:-5]
    else:
        base_name = source_name

    filename = f"{base_name}.csv"
    path = os.path.join("data_files", filename)

    df.to_csv(path, sep=';', index=False, encoding='utf-8-sig')

    return path, filename


async def process_csv_to_json(csv_data, source_name, json_format='array'):
    if source_name is None or source_name == "":
        source_name = "converted_data"
    logger.info(f"Converting CSV to JSON: {source_name}")

    from io import StringIO
    csv_reader = csv.DictReader(StringIO(csv_data), delimiter=';')
    rows = list(csv_reader)

    if not rows:
        raise ValueError("CSV file is empty or invalid")

    if json_format == 'array':
        json_data = rows
    elif json_format == 'object':
        json_data = {
            "data": rows,
            "total": len(rows),
            "exported_at": datetime.now().isoformat()
        }
    else:
        json_data = rows

    os.makedirs("data_files", exist_ok=True)

    if source_name and source_name.endswith('.csv'):
        base_name = source_name[:-4]
    elif source_name:
        base_name = source_name
    else:
        base_name = "converted_data"

    filename = f"{base_name}.json"
    path = os.path.join("data_files", filename)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return path, filename


async def process_xml_to_json(xml_data, source_name):
    logger.info(f"Converting XML to JSON: {source_name}")

    def xml_to_dict(element):
        result = {}

        if element.attrib:
            result.update({f"@{k}": v for k, v in element.attrib.items()})

        if element.text and element.text.strip():
            if len(element) == 0:
                return element.text.strip()
            else:
                result["#text"] = element.text.strip()

        for child in element:
            child_data = xml_to_dict(child)
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data

        return result

    try:
        root = ET.fromstring(xml_data)
        json_data = {root.tag: xml_to_dict(root)}
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {str(e)}")

    os.makedirs("data_files", exist_ok=True)

    if source_name.endswith('.xml'):
        base_name = source_name[:-4]
    else:
        base_name = source_name

    filename = f"{base_name}.json"
    path = os.path.join("data_files", filename)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return path, filename


async def process_jpg_to_png(image_data, source_name):
    logger.info(f"Converting JPG to PNG: {source_name}")

    try:
        image = Image.open(BytesIO(image_data))

        if image.mode != 'RGB' and image.mode != 'RGBA':
            image = image.convert('RGB')

        os.makedirs("data_files", exist_ok=True)

        if source_name.lower().endswith(('.jpg', '.jpeg')):
            base_name = os.path.splitext(source_name)[0]
        else:
            base_name = source_name

        filename = f"{base_name}.png"
        path = os.path.join("data_files", filename)

        image.save(path, 'PNG', optimize=True)

        return path, filename

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}", exc_info=True)
        raise ValueError(f"Error processing image: {str(e)}")


async def process_pdf_to_csv(pdf_data, source_name, extraction_method='pdfplumber'):
    logger.info(f"Converting PDF to CSV: {source_name}")

    try:
        all_tables = []

        if extraction_method == 'pdfplumber':
            with pdfplumber.open(BytesIO(pdf_data)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    tables = page.extract_tables()
                    for table_num, table in enumerate(tables):
                        if table and len(table) > 0:
                            df = pd.DataFrame(table[1:], columns=table[0])
                            df = df.dropna(how='all').fillna('')

                            df['pdf_page'] = page_num
                            df['table_number'] = table_num + 1
                            all_tables.append(df)

        elif extraction_method == 'tabula' and tabula:
            try:
                temp_pdf_path = "temp_pdf_file.pdf"
                with open(temp_pdf_path, 'wb') as f:
                    f.write(pdf_data)

                tables = tabula.read_pdf(temp_pdf_path, pages='all', multiple_tables=True)

                for table_num, df in enumerate(tables):
                    if not df.empty:
                        df = df.fillna('')
                        df['table_number'] = table_num + 1
                        all_tables.append(df)

                try:
                    if os.path.exists(temp_pdf_path):
                        os.remove(temp_pdf_path)
                except Exception as cleanup_error:
                    logger.warning(f"Could not remove temporary file {temp_pdf_path}: {cleanup_error}")

            except Exception as e:
                logger.error(f"Tabula extraction failed: {e}, falling back to pdfplumber", exc_info=True)
                return await process_pdf_to_csv(pdf_data, source_name, 'pdfplumber')

        if not all_tables:
            raise ValueError("No tables found in PDF file")

        combined_df = pd.concat(all_tables, ignore_index=True)

        os.makedirs("data_files", exist_ok=True)

        if source_name.lower().endswith('.pdf'):
            base_name = source_name[:-4]
        else:
            base_name = source_name

        filename = f"{base_name}_tables.csv"
        path = os.path.join("data_files", filename)

        combined_df.to_csv(path, sep=';', index=False, encoding='utf-8-sig')

        return path, filename

    except Exception as e:
        logger.error(f"Error extracting tables from PDF: {str(e)}", exc_info=True)
        raise ValueError(f"Error extracting tables from PDF: {str(e)}")


async def process_pdf_to_json(pdf_data, source_name):
    logger.info(f"Converting PDF to JSON: {source_name}")

    try:
        extracted_data = {
            "document_info": {},
            "pages": [],
            "tables": [],
            "text_content": []
        }

        with pdfplumber.open(BytesIO(pdf_data)) as pdf:
            if pdf.metadata:
                extracted_data["document_info"] = {
                    "title": pdf.metadata.get('Title', ''),
                    "author": pdf.metadata.get('Author', ''),
                    "creator": pdf.metadata.get('Creator', ''),
                    "producer": pdf.metadata.get('Producer', ''),
                    "creation_date": str(pdf.metadata.get('CreationDate', '')),
                    "modification_date": str(pdf.metadata.get('ModDate', '')),
                    "pages_count": len(pdf.pages)
                }

            for page_num, page in enumerate(pdf.pages, 1):
                page_data = {
                    "page_number": page_num,
                    "text": page.extract_text() or "",
                    "tables": [],
                    "images_count": len(page.images) if hasattr(page, 'images') else 0
                }

                tables = page.extract_tables()
                for table_num, table in enumerate(tables):
                    if table and len(table) > 0:
                        table_data = {
                            "table_number": table_num + 1,
                            "headers": table[0] if table[0] else [],
                            "rows": table[1:] if len(table) > 1 else [],
                            "rows_count": len(table) - 1 if len(table) > 1 else 0,
                            "columns_count": len(table[0]) if table and table[0] else 0
                        }
                        page_data["tables"].append(table_data)
                        extracted_data["tables"].append({
                            "page": page_num,
                            **table_data
                        })

                extracted_data["pages"].append(page_data)

                if page_data["text"]:
                    extracted_data["text_content"].append({
                        "page": page_num,
                        "text": page_data["text"]
                    })

        os.makedirs("data_files", exist_ok=True)

        if source_name.lower().endswith('.pdf'):
            base_name = source_name[:-4]
        else:
            base_name = source_name

        filename = f"{base_name}_data.json"
        path = os.path.join("data_files", filename)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)

        return path, filename

    except Exception as e:
        logger.error(f"Error extracting data from PDF: {str(e)}", exc_info=True)
        raise ValueError(f"Error extracting data from PDF: {str(e)}")


async def process_csv_to_pdf(csv_data, source_name, report_style='table'):
    logger.info(f"Converting CSV to PDF: {source_name}")

    try:
        from io import StringIO
        csv_reader = csv.DictReader(StringIO(csv_data), delimiter=';')
        rows = list(csv_reader)

        if not rows:
            raise ValueError("CSV file is empty or invalid")

        os.makedirs("data_files", exist_ok=True)

        if source_name.lower().endswith('.csv'):
            base_name = source_name[:-4]
        else:
            base_name = source_name

        filename = f"{base_name}_report.pdf"
        path = os.path.join("data_files", filename)

        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=30, leftMargin=30,
                              topMargin=30, bottomMargin=18)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            textColor=colors.darkblue,
            alignment=1
        )

        story = []

        title = Paragraph(f"Отчет: {base_name}", title_style)
        story.append(title)
        story.append(Spacer(1, 12))

        if report_style == 'table':
            headers = list(rows[0].keys())
            table_data = [headers]

            for row in rows[:50]:
                table_data.append([str(row.get(header, '')) for header in headers])

            table = Table(table_data)

            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(table)

        elif report_style == 'summary':
            summary_text = f"""
            <b>Сводка по данным:</b><br/>
            • Общее количество записей: {len(rows)}<br/>
            • Количество полей: {len(rows[0].keys()) if rows else 0}<br/>
            • Поля данных: {', '.join(rows[0].keys()) if rows else 'Нет данных'}<br/>
            """

            summary = Paragraph(summary_text, styles['Normal'])
            story.append(summary)
            story.append(Spacer(1, 20))

            story.append(Paragraph("<b>Примеры данных:</b>", styles['Heading3']))

            for i, row in enumerate(rows[:5]):
                example_text = f"<b>Запись {i+1}:</b><br/>"
                for key, value in row.items():
                    example_text += f"• {key}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}<br/>"

                story.append(Paragraph(example_text, styles['Normal']))
                story.append(Spacer(1, 10))

        footer_text = f"Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        footer = Paragraph(footer_text, styles['Normal'])
        story.append(Spacer(1, 30))
        story.append(footer)

        doc.build(story)

        return path, filename

    except Exception as e:
        logger.error(f"Error creating PDF report: {str(e)}", exc_info=True)
        raise ValueError(f"Error creating PDF report: {str(e)}")


async def process_excel_to_pdf(excel_data, source_name, report_style='table'):
    logger.info(f"Converting Excel to PDF: {source_name}")

    try:
        df = pd.read_excel(BytesIO(excel_data), engine='openpyxl')

        if df.empty:
            raise ValueError("Excel file is empty or invalid")

        csv_data = df.to_csv(sep=';', index=False)

        return await process_csv_to_pdf(csv_data, source_name, report_style)

    except Exception as e:
        logger.error(f"Error converting Excel to PDF: {str(e)}", exc_info=True)
        raise ValueError(f"Error converting Excel to PDF: {str(e)}")


async def process_image_to_pdf(image_data, source_name):
    logger.info(f"Converting image to PDF: {source_name}")

    try:
        image = Image.open(BytesIO(image_data))

        if image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'RGBA':
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        os.makedirs("data_files", exist_ok=True)

        base_name = os.path.splitext(source_name)[0]
        filename = f"{base_name}.pdf"
        path = os.path.join("data_files", filename)

        max_width = 595
        max_height = 842

        img_width_pts = image.width * 72 / 96
        img_height_pts = image.height * 72 / 96

        if img_width_pts > max_width or img_height_pts > max_height:
            scale_factor = min(max_width / img_width_pts, max_height / img_height_pts)
            pdf_width = img_width_pts * scale_factor
            pdf_height = img_height_pts * scale_factor
            page_width = max_width
            page_height = max_height
        else:
            pdf_width = img_width_pts
            pdf_height = img_height_pts
            page_width = img_width_pts
            page_height = img_height_pts

        page_width = max(page_width, 72)
        page_height = max(page_height, 72)

        doc = SimpleDocTemplate(path, pagesize=(page_width, page_height),
                              rightMargin=0, leftMargin=0, topMargin=0, bottomMargin=0)

        temp_image_path = f"temp_image_{base_name}.jpg"
        image.save(temp_image_path, 'JPEG', quality=95)

        from reportlab.platypus import Image as ReportLabImage

        x_offset = (page_width - pdf_width) / 2
        y_offset = (page_height - pdf_height) / 2

        pdf_image = ReportLabImage(temp_image_path, width=pdf_width, height=pdf_height)

        doc.build([pdf_image])

        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

        return path, filename

    except Exception as e:
        temp_image_path = f"temp_image_{os.path.splitext(source_name)[0]}.jpg"
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        logger.error(f"Error converting image to PDF: {str(e)}", exc_info=True)
        raise ValueError(f"Error converting image to PDF: {str(e)}")


async def process_pdf_to_image(pdf_data, source_name, output_format='png', dpi=300):
    logger.info(f"Converting PDF to {output_format.upper()}: {source_name}")

    try:
        import fitz

        os.makedirs("data_files", exist_ok=True)

        base_name = os.path.splitext(source_name)[0]

        pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

        if len(pdf_document) == 1:
            page = pdf_document[0]

            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat)

            img_data = pix.tobytes("png")
            image = Image.open(BytesIO(img_data))

            if output_format.lower() == 'jpg':
                if image.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')

                filename = f"{base_name}.jpg"
                path = os.path.join("data_files", filename)
                image.save(path, 'JPEG', quality=95, optimize=True)
            else:
                filename = f"{base_name}.png"
                path = os.path.join("data_files", filename)
                image.save(path, 'PNG', optimize=True)

            pdf_document.close()
            return path, filename

        else:
            import zipfile

            zip_filename = f"{base_name}_images.zip"
            zip_path = os.path.join("data_files", zip_filename)

            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                for page_num in range(len(pdf_document)):
                    page = pdf_document[page_num]

                    mat = fitz.Matrix(dpi/72, dpi/72)
                    pix = page.get_pixmap(matrix=mat)

                    img_data = pix.tobytes("png")
                    image = Image.open(BytesIO(img_data))

                    img_buffer = BytesIO()

                    if output_format.lower() == 'jpg':
                        if image.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', image.size, (255, 255, 255))
                            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                            image = background
                        elif image.mode != 'RGB':
                            image = image.convert('RGB')

                        image.save(img_buffer, 'JPEG', quality=95, optimize=True)
                        img_filename = f"page_{page_num + 1:03d}.jpg"
                    else:
                        image.save(img_buffer, 'PNG', optimize=True)
                        img_filename = f"page_{page_num + 1:03d}.png"

                    zip_file.writestr(img_filename, img_buffer.getvalue())

            pdf_document.close()
            return zip_path, zip_filename

    except ImportError:
        try:
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(pdf_data, dpi=dpi)

            if len(images) == 1:
                image = images[0]

                if output_format.lower() == 'jpg':
                    if image.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')

                    filename = f"{base_name}.jpg"
                    path = os.path.join("data_files", filename)
                    image.save(path, 'JPEG', quality=95, optimize=True)
                else:
                    filename = f"{base_name}.png"
                    path = os.path.join("data_files", filename)
                    image.save(path, 'PNG', optimize=True)

                return path, filename
            else:
                import zipfile

                zip_filename = f"{base_name}_images.zip"
                zip_path = os.path.join("data_files", zip_filename)

                with zipfile.ZipFile(zip_path, 'w') as zip_file:
                    for i, image in enumerate(images):
                        img_buffer = BytesIO()

                        if output_format.lower() == 'jpg':
                            if image.mode in ('RGBA', 'LA'):
                                background = Image.new('RGB', image.size, (255, 255, 255))
                                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                                image = background
                            elif image.mode != 'RGB':
                                image = image.convert('RGB')

                            image.save(img_buffer, 'JPEG', quality=95, optimize=True)
                            img_filename = f"page_{i + 1:03d}.jpg"
                        else:
                            image.save(img_buffer, 'PNG', optimize=True)
                            img_filename = f"page_{i + 1:03d}.png"

                        zip_file.writestr(img_filename, img_buffer.getvalue())

                return zip_path, zip_filename

        except ImportError:
            logger.error("PDF to image conversion requires PyMuPDF (fitz) or pdf2image library. Please install one of them.", exc_info=True)
            raise ValueError("PDF to image conversion requires PyMuPDF (fitz) or pdf2image library. Please install one of them.")

    except Exception as e:
        logger.error(f"Error converting PDF to image: {str(e)}", exc_info=True)
        raise ValueError(f"Error converting PDF to image: {str(e)}")


async def process_xml_data(xml_data, source_name, target_node="auto"):
    logger.info(f"Processing data from: {source_name}")
    logger.info(f"Data length: {len(xml_data)} characters")

    logger.info(f"First 500 characters of response: {xml_data[:500]}")

    data_lower = xml_data.strip().lower()
    if data_lower.startswith('<html') or data_lower.startswith('<!doctype html'):
        raise ValueError(f"Data contains HTML page instead of XML/YML file.")

    if (('error' in data_lower or 'not found' in data_lower or '404' in data_lower) and
        not xml_data.strip().startswith('<?xml') and
        not any(tag in data_lower for tag in ['<yml_catalog', '<catalog', '<offers', '<products', '<shop', '<корневой'])):
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

    has_valid_structure = (has_yml_catalog or has_catalog or has_products or
                          has_shop or has_offers or has_categories or has_russian_format or has_service_format)

    if not has_valid_structure:
        raise ValueError(f"XML file does not contain expected elements (yml_catalog, catalog, offers, products, shop, categories, Russian format, or service format). This may not be a valid XML catalog file.")

    try:
        logger.info("Starting XML parsing...")
        xml_data = xml_data_clean

        if xml_data.startswith('\ufeff'):
            xml_data = xml_data[1:]
            logger.info("Removed BOM")

        import re
        original_length = len(xml_data)
        xml_data = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_data)
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
        if root.findall('.//offer'):
            format_type = 'offer'
        elif root.findall('.//product'):
            format_type = 'product'
        elif root.findall('.//ЭлементСправочника'):
            format_type = 'russian'
        elif root.findall('.//service') or root.tag == 'service':
            format_type = 'service'
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

    if format_type == 'russian':
        results = [await process_russian_xml(root)]
    elif format_type == 'service':
        results = [await process_service_xml(root)]
    else:
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
        'option_days', 'option_order-before', 'images', 'debug_images_found', 'offers'
    ]
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
    timeout = aiohttp.ClientTimeout(total=60)
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
            'Referer': 'https://nonton.ru/',
            'Origin': 'https://nonton.ru',
            'DNT': '1',
            'X-Requested-With': 'XMLHttpRequest'
        }

        try:
            async with session.get(link_url, headers=headers, allow_redirects=True) as initial_response:
                if initial_response.status == 200:
                    sample_content = await initial_response.text()
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

        strategies = [
            {
                'name': 'Standard request',
                'headers': headers
            },
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
            },
            {
                'name': 'Mobile browser simulation',
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Referer': f'https://{urlparse(link_url).netloc}/',
                }
            }
        ]

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

                        if 'xml' in content_type or 'application/xml' in content_type:
                            logger.info(f"Successfully accessed XML with {strategy['name']}")
                            sample_content = await response.text()
                            if sample_content.strip().startswith('<?xml') or sample_content.strip().startswith('<yml_catalog'):
                                path, filename = await process_xml_data(sample_content, link_url, target_node)
                                return path, f"https://magic-xml.replit.app/download/data_files/{filename}"
                        else:
                            sample_content = await response.text()
                            if sample_content.strip().startswith('<?xml') or sample_content.strip().startswith('<yml_catalog'):
                                logger.info(f"Found XML content with {strategy['name']} despite incorrect Content-Type")
                                path, filename = await process_xml_data(sample_content, link_url, target_node)
                                return path, f"https://magic-xml.replit.app/download/data_files/{filename}"

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

            except Exception as e:
                logger.error(f"{strategy['name']} failed: {e}", exc_info=True)
                continue

        if successful_response is None:
            error_message = f"Не удается получить доступ к файлу. Сервер блокирует все попытки доступа (403). Возможные причины:\n1. Файл защищен авторизацией\n2. Сайт блокирует автоматические запросы\n3. Требуется специальный токен доступа\n\nРекомендации:\n- Скачайте файл вручную через браузер\n- Загрузите файл через форму на сайте\n- Обратитесь к владельцу сайта за прямой ссылкой"
            logger.error(error_message)
            raise ValueError(error_message)

        try:
            final_content = await successful_response.text()
            if final_content.strip().startswith('<?xml') or final_content.strip().startswith('<yml_catalog'):
                path, filename = await process_xml_data(final_content, link_url, target_node)
                return path, f"https://magic-xml.replit.app/download/data_files/{filename}"
            else:
                error_message = f"Сервер возвращает HTML страницу вместо XML файла. Проверьте корректность URL и убедитесь, что ссылка ведет непосредственно к XML/YML файлу."
                logger.error(error_message)
                raise ValueError(error_message)
        except Exception as e:
            logger.error(f"Error processing final content: {str(e)}", exc_info=True)
            raise ValueError(f"Ошибка обработки содержимого файла: {str(e)}")


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

    import hashlib
    user_id = hashlib.md5(user_ip.encode()).hexdigest()[:8].upper()

    return {
        "user_id": user_id,
        "ip_address": user_ip
    }


@app.post("/process_file")
async def process_file_upload(file: UploadFile = File(...)):
    try:
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
        elif filename.lower().endswith('.json'):
            path, output_filename = await process_json_to_csv(file_data, filename)
        elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            path, output_filename = await process_image_to_pdf(content, filename)
        else:
            path, output_filename = await process_xml_data(file_data, filename)

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
        logger.info(f"=== CSV to Excel conversion started ===")
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


@app.post("/convert_json_to_csv")
async def convert_json_to_csv(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith('.json'):
            raise HTTPException(status_code=400, detail="Only JSON files are supported")

        content = await file.read()

        try:
            json_data = content.decode('utf-8')
        except UnicodeDecodeError:
            json_data = content.decode('utf-8', errors='replace')

        path, filename = await process_json_to_csv(json_data, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "csv"
        }

    except Exception as e:
        logger.error(f"Error converting JSON to CSV: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_csv_to_json")
async def convert_csv_to_json(file: UploadFile = File(...), json_format: str = "array"):
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

        path, filename = await process_csv_to_json(csv_data, file.filename, json_format)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "json"
        }

    except Exception as e:
        logger.error(f"Error converting CSV to JSON: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_xml_to_json")
async def convert_xml_to_json(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(status_code=400, detail="Only XML files are supported")

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

        path, filename = await process_xml_to_json(xml_data, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "json"
        }

    except Exception as e:
        logger.error(f"Error converting XML to JSON: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_jpg_to_png")
async def convert_jpg_to_png(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith(('.jpg', '.jpeg')):
            raise HTTPException(status_code=400, detail="Only JPG/JPEG files are supported")

        content = await file.read()
        path, filename = await process_jpg_to_png(content, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "png"
        }

    except Exception as e:
        logger.error(f"Error converting JPG to PNG: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_png_to_jpg")
async def convert_png_to_jpg(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith('.png'):
            raise HTTPException(status_code=400, detail="Only PNG files are supported")

        content = await file.read()
        path, filename = await process_png_to_jpg(content, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "jpg"
        }

    except Exception as e:
        logger.error(f"Error converting PNG to JPG: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_pdf_to_csv")
async def convert_pdf_to_csv(file: UploadFile = File(...), extraction_method: str = "pdfplumber"):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        content = await file.read()
        path, filename = await process_pdf_to_csv(content, file.filename, extraction_method)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "csv",
            "extraction_method": extraction_method
        }

    except Exception as e:
        logger.error(f"Error converting PDF to CSV: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_pdf_to_excel")
async def convert_pdf_to_excel(file: UploadFile = File(...), extraction_method: str = "pdfplumber"):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        content = await file.read()

        csv_path, csv_filename = await process_pdf_to_csv(content, file.filename, extraction_method)

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            csv_data = f.read()

        excel_path, excel_filename = await process_csv_to_excel(csv_data, file.filename)

        if os.path.exists(csv_path):
            os.remove(csv_path)

        return {
            "file_url": f"/download/data_files/{excel_filename}",
            "status": "completed",
            "filename": excel_filename,
            "format": "excel",
            "extraction_method": extraction_method
        }

    except Exception as e:
        logger.error(f"Error converting PDF to Excel: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_pdf_to_json")
async def convert_pdf_to_json(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        content = await file.read()
        path, filename = await process_pdf_to_json(content, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "json"
        }

    except Exception as e:
        logger.error(f"Error converting PDF to JSON: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_csv_to_pdf")
async def convert_csv_to_pdf(file: UploadFile = File(...), report_style: str = "table"):
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

        path, filename = await process_csv_to_pdf(csv_data, file.filename, report_style)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "pdf",
            "report_style": report_style
        }

    except Exception as e:
        logger.error(f"Error converting CSV to PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_excel_to_pdf")
async def convert_excel_to_pdf(file: UploadFile = File(...), report_style: str = "table"):
    try:
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported")

        content = await file.read()
        path, filename = await process_excel_to_pdf(content, file.filename, report_style)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "pdf",
            "report_style": report_style
        }

    except Exception as e:
        logger.error(f"Error converting Excel to PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_image_to_pdf")
async def convert_image_to_pdf(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            raise HTTPException(status_code=400, detail="Only PNG, JPG, and JPEG files are supported")

        content = await file.read()
        path, filename = await process_image_to_pdf(content, file.filename)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "pdf"
        }

    except Exception as e:
        logger.error(f"Error converting image to PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_pdf_to_png")
async def convert_pdf_to_png(file: UploadFile = File(...), dpi: int = 300):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        content = await file.read()
        path, filename = await process_pdf_to_image(content, file.filename, 'png', dpi)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "png",
            "dpi": dpi
        }

    except Exception as e:
        logger.error(f"Error converting PDF to PNG: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")


@app.post("/convert_pdf_to_jpg")
async def convert_pdf_to_jpg(file: UploadFile = File(...), dpi: int = 300):
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        content = await file.read()
        path, filename = await process_pdf_to_image(content, file.filename, 'jpg', dpi)

        return {
            "file_url": f"/download/data_files/{filename}",
            "status": "completed",
            "filename": filename,
            "format": "jpg",
            "dpi": dpi
        }

    except Exception as e:
        logger.error(f"Error converting PDF to JPG: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")

@app.post("/process_link")
async def process_link_post(link_data: LinkData, request: Request):
    logger.info(f"Processing link: {link_data.link_url}")
    logger.info(f"Target node: {link_data.preset_id}")
    try:
        target_node = link_data.preset_id if link_data.preset_id and link_data.preset_id != "" else "auto"
        logger.info(f"Using target node: {target_node}")
        path, url = await process_link(link_data.link_url,
                                       str(request.url).rstrip(request.url.path),
                                       target_node=target_node)
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
        "status":
        "completed",
        "file_url":
        "https://magic-xml.replit.app/download/data_files/your_file.csv"
    }


@app.get("/download/data_files/{filename}")
def download_csv(filename: str):
    file_path = os.path.join("data_files", filename)
    if os.path.isfile(file_path):
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        return FileResponse(path=file_path,
                            filename=filename,
                            media_type='application/octet-stream',
                            headers={"Access-Control-Allow-Origin": "*"})
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="localhost", port=8080, reload=True)
