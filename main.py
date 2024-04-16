from urllib.parse import urlparse
import requests
import xml.etree.ElementTree as ET
import csv
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
nlp = spacy.load("ru_core_news_sm")


class LinkData(BaseModel):
  link_url: str
  return_url: str = ""
  preset_id: str = ""


def get_category_replacement(original_category_name, custom_categories):
  vectorizer = TfidfVectorizer()
  all_categories = [original_category_name] + custom_categories
  tfidf_matrix = vectorizer.fit_transform(all_categories)
  cosine_similarities = cosine_similarity(tfidf_matrix[0:1],
                                          tfidf_matrix[1:]).flatten()
  return custom_categories[cosine_similarities.argmax()]


def load_custom_categories(filename):
  custom_categories = []
  with open(filename, mode='r', encoding='utf-8') as file:
    reader = csv.reader(file)
    custom_categories = [row[0] for row in reader]
  return custom_categories


def remove_unwanted_tags(description):
  if description:
    description = re.sub(r'<[^>]+>', '', description)
    description = description.replace('•', '')
    description = re.sub(r'\s*<br>\s*', '\n', description, flags=re.IGNORECASE)
    description = re.sub(r'(\n\s*)+', '\n', description)
    description = f'<p>{description.strip()}</p>'.replace('\n', '<br>')
  else:
    description = ''

  return description


def process_link(link_url):
  try:
    response = requests.get(link_url)
    response.raise_for_status()
    xml_data = response.content.decode('utf-8')
    root = ET.fromstring(xml_data)
    custom_categories = load_custom_categories('categories.csv')

    categories = {}
    for category in root.findall('.//category'):
      categories[category.get('id')] = category.text

    data = []
    for offer_elem in root.findall('.//offer'):
      offer_id = offer_elem.get('id', '0')
      offer_data = {'id': offer_id}
      category_id = offer_elem.find('.//categoryId').text
      original_category_name = categories.get(category_id, "Undefined")
      offer_data['category_name'] = get_category_replacement(
          original_category_name, custom_categories)

      for category_elem in offer_elem:
        if category_elem.tag not in ['picture', 'param']:
          category_name = category_elem.tag
          category_value = category_elem.text
          if category_value and category_value.replace('.', '', 1).isdigit():
            category_value = category_value.replace('.', ',')
          offer_data[category_name] = category_value
      picture_elems = offer_elem.findall('.//picture')
      pictures = "///".join(
          picture_elem.text
          for picture_elem in picture_elems) if picture_elems else ""
      if pictures:
        offer_data['pictures'] = pictures
      param_elems = offer_elem.findall('.//param')
      params = {
          param_elem.get('name'): param_elem.text
          for param_elem in param_elems
      } if param_elems else {}
      offer_data.update(params)
      data.append(offer_data)

    save_path = "data_files"
    os.makedirs(save_path, exist_ok=True)
    domain_name = urlparse(link_url).netloc.replace("www.", "")
    safe_filename = domain_name.replace(".", "_")
    unique_filename = f"{safe_filename}.csv"
    file_path = os.path.join(save_path, unique_filename)

    category_names = set()
    for row in data:
      category_names.update(row.keys())
    for row in data:
      if 'description' in row and row['description']:
        row['description'] = remove_unwanted_tags(row['description'])
    with open(file_path, 'w', newline='', encoding='utf-8-sig') as file:
      writer = csv.DictWriter(file,
                              fieldnames=sorted(category_names),
                              delimiter=';')
      writer.writeheader()
      writer.writerows(data)
    return file_path
  except Exception as e:
    print(f"Произошла ошибка: {str(e)}")
    return None


@app.get("/")
def read_index(request: Request):
  return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process_link")
async def process_link_post(link_data: LinkData):
  link_url = link_data.link_url
  preset_id = link_data.preset_id
  result = process_link(link_url)
  if result:
    downloaded_file_name = os.path.basename(result)
    return {
        "file_url":
        f"https://soldata-cs-cart.replit.app/download/data_files/{downloaded_file_name}",
        "preset_id": preset_id
    }
  else:
    raise HTTPException(status_code=500,
                        detail="Во время обработки ссылки произошла ошибка")


@app.get("/download/data_files/{filename}")
async def download_csv(filename: str):
  file_path = os.path.join("data_files", filename)
  if os.path.isfile(file_path):
    return FileResponse(path=file_path,
                        filename=filename,
                        media_type='application/octet-stream')
  else:
    raise HTTPException(status_code=404, detail="Файл не найден.")
