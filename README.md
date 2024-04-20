<div align="center">
  <img src="assets/working.png" width="30%"/>
</div>

# Magic-XML ⚡️

**_Magic-XML is available at https://xmlmagic.ru_**

##

<div align="center">
  <h3> <a href="https://github.com/Solrikk/MagicXML/blob/main/README.md"> English | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_RU.md">Русский</a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_GE.md"> Deutsch </a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_JP.md"> 日本語 </a> | <a href="README_KR.md">한국어</a> | <a href="README_CN.md">中文</a> </h3>
</div>

**_Magic-XML_** — is a modern web application developed for the convenient and swift transformation of data from XML files into CSV format. The application leverages the power of FastAPI to ensure high performance in request processing, as well as utilizes machine learning algorithms and natural language processing for efficient analysis and classification of textual information. Magic-XML is ideally suited for data analysts, developers, and anyone who deals with large volumes of XML data and aims at their optimization and simplification of analysis.


**Dependencies:**
- `fastapi` - A framework for building APIs with automatic documentation.
- `uvicorn` - ASGI server for running FastAPI applications.
- `requests` - Library for making HTTP requests.
- `xml.etree.ElementTree` - Module for XML processing.
- `csv` - Module for working with CSV files.
- `os` - Module for interacting with the operating system, used for creating directories.
- `Jinja2Templates` from FastAPI for working with Jinja2 templates.
- `StaticFiles` - For serving static files.
- `BaseModel` from `pydantic` - For data validation.
- `FileResponse` for sending files in responses.
- `spacy` - For natural language processing, used for categorization.
- `TfidfVectorizer` for text vectorization.
- `cosine_similarity` for calculating cosine similarity.
- `re` - Module for working with regular expressions.

**Application Structure:**
- `FastAPI Application`: Initializes the main application with FastAPI, configures the routes for static files and the `Jinja2 templating engine`.
- `LinkData class (Pydantic model)`: A model for validating incoming data received through a `POST request to /process_link`.

**Data processing functions:**
- `Get_category_replacement()`: A function for categorization based on the cosine similarity between vectors.
- `Load_custom_categories()`: Loading custom categories from a CSV file.
- `Remove_unwanted_tags()`: Cleaning product descriptions of HTML tags.
- `Process_link()`: The main function for processing an XML link, extracting, and saving data to a CSV file.

**FastAPI Routes:**
- `GET /`: Display the home page through a Jinja2 template.
- `POST /process_link`: Accepts data for processing the link and generates a CSV file.
- `GET /download/data_files/{filename}`: Ability to download generated CSV files.

_**Adapting Categories Using TF-IDF and Cosine Similarity:**_ 
The program employs `TfidfVectorizer` and `cosine similarity` to determine the most suitable custom category for a product based on its original category name obtained from XML. This showcases an interesting approach to the classification or `category mapping` task, where `machine learning methods` are used instead of direct matching to enhance the accuracy and flexibility of the process.

- TF (term frequency — частота слова) — отношение числа вхождений некоторого слова к общему числу слов документа

<img src="https://wikimedia.org/api/rest_v1/media/math/render/svg/8ef207eb03f6e9b6f71e73739f45b5179b4f17cc" width="15%" />

- IDF (Inverse Document Frequency) - the inversion of the frequency with which a certain word appears in the documents of a collection. Karen Spärck Jones is the founder of this concept. Taking into account IDF reduces the weight of commonly used words. For each unique word within a specific collection of documents, there is only one IDF value.

<img src="https://wikimedia.org/api/rest_v1/media/math/render/svg/b88834044365dea6aedba224eabe7147d4d328ef" width="30%" />

```Python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def get_category_replacement(original_category_name, custom_categories):
    vectorizer = TfidfVectorizer()
    all_categories = [original_category_name] + custom_categories
    tfidf_matrix = vectorizer.fit_transform(all_categories)
    cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
    return custom_categories[cosine_similarities.argmax()]
```

1. **Category Vectorization:**
Using TF-IDF, the program transforms the names of the categories (one of the original names and a list of custom categories) into a vector representation. This means that each category becomes a vector in a multidimensional space, where each dimension represents a word from the category corpus, and the value represents the importance of the word in the context of the category.
2. **Finding Cosine Similarity:**
Then, the program calculates the cosine similarity between the vector of the original category and the vectors of each custom category. This compares how close the custom categories are to the original category in terms of their contextual similarity.
3. **Selecting the Most Suitable Category:**
After calculating the cosine similarities, the custom category with the highest similarity value relative to the original category is selected. This means that this category is considered the most suitable or closest to the original category in terms of semantic content.

Этот подход позволяет автоматически и с высокой степенью точности подбирать наиболее подходящие категории для продуктов из определенного набора пользовательских категорий, полагаясь на анализ содержания названий категорий, а не на строгое сопоставление. Это особенно полезно в случаях, когда требуется автоматическая классификация или категоризация больших объемов данных, и где прямое сопоставление может не покрывать все нюансы и вариации языка.

_**Асинхронная обработка запросов**_
FastAPI основан на Starlette и позволяет обрабатывать запросы асинхронно, используя `async` и `await`. Это дает приложению возможность масштабироваться и обслуживать большое количество запросов эффективно, улучшая производительность на I/O операциях, таких как запросы к внешним API или операции чтения файлов. В данном приложении асинхронная обработка может быть особенно полезна при загрузке файлов через ендпоинт `/download/data_files/{filename},` где асинхронное чтение файла может значительно снизить время ожидания для клиента.

_*Обработка endpoint-ов с асинхронными функциями:*_

- В коде определен асинхронный endpoint `process_link_post` через декоратор `@app.post("/process_link")`. Этот `endpoint` асинхронно обрабатывает `POST-запросы`, отправляя данные о ссылке (например, URL для обработки). Использование ключевого слова `async` перед определением функции указывает на то, что функция выполняется асинхронно.
- Аналогично, асинхронный метод `download_csv` обрабатывает `GET-запросы` на скачивание файлов. Это также позволяет обрабатывать запросы на скачивание файлов, не блокируя основной поток выполнения приложения.

**Работа с текстом и естественным языком**
Использование spaCy и TfidfVectorizer из scikit-learn для категоризации текста показывает, как можно эффективно применять инструменты машинного обучения в веб-приложениях. spaCy используется для предварительной обработки текста на русском языке, что важно для точной работы категоризации, ведь обработка текста включает в себя многие аспекты, такие как лемматизация и удаление стоп-слов, которые значительно влияют на итоговую точность. TfidfVectorizer преобразует текст в векторное представление, позволяя затем вычислить косинусное сходство между векторами, что используется для выбора наиболее подходящей категории для текста.

<img src="https://habrastorage.org/getpro/habr/post_images/bcd/fff/e5c/bcdfffe5c0b9f221a2f6607f96ca0e4a.svg" width="80%" />

**Обработка XML и генерация CSV**
В приложении осуществляется парсинг XML-файлов для извлечения данных о товарах, что демонстрирует умение работать с различными форматами данных. После извлечения данных и их классификации происходит их сохранение в формате CSV, который является широко принятым стандартом для обмена табличными данными и может быть легко импортирован в различные системы и приложения для последующего анализа.

**Кастомизация категоризации**
Особенностями реализации является возможность кастомизации категорий через внешний CSV-файл. Это дает пользователю гибкость в управлении категориями товаров без изменения кода, что делает приложение более удобным и адаптивным под различные бизнес-задачи.

- Пользовательские категории загружаются из CSV-файла с помощью функции `load_custom_categories(filename)`. Этот файл содержит перечень категорий, которые интересуют пользователя, и может быть легко обновлен или изменен без вмешательства в исходный код приложения.

```Python
def load_custom_categories(filename):
  custom_categories = []
  with open(filename, mode='r', encoding='utf-8') as file:
    reader = csv.reader(file)
    custom_categories = [row[0] for row in reader]
  return custom_categories
```

- Для категоризации текста используется процедура векторизации, которая преобразует текст категории и тексты пользовательских категорий в числовые вектора при помощи TfidfVectorizer из scikit-learn. Это позволяет применить математические и аналитические методы для сравнения текстов.

```Python
from sklearn.feature_extraction.text import TfidfVectorizer

vectorizer = TfidfVectorizer()
all_categories = [original_category_name] + custom_categories
tfidf_matrix = vectorizer.fit_transform(all_categories)
```

<img src="https://scikit-learn.org/stable/_images/sphx_glr_plot_discretization_strategies_001.png" width="80%" />

- Косинусное сходство между вектором описания товара и векторами пользовательских категорий вычисляется, чтобы определить, какая из пользовательских категорий наилучшим образом совпадает с данным товаром.

```Python
from sklearn.metrics.pairwise import cosine_similarity

cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
return custom_categories[cosine_similarities.argmax()]
```

- На основе полученных значений косинусного сходства приложение автоматически выбирает для каждого товара наиболее подходящую пользовательскую категорию, что значительно упрощает дальнейшую работу с данными, позволяя пользователям группировать товары по заранее определенным категориям.

**Техническая реализация веб-интерфейса**
В приложении используется Jinja2Templates для генерации динамического HTML-контента. Это дает возможность создавать более интерактивный и пользовательско-ориентированный интерфейс. Вместе с монтированием статических файлов через StaticFiles, это создает полноценный веб-интерфейс для работы с приложением, не требуя от пользователя работы непосредственно с API или командной строкой.

**Валидация данных с Pydantic**
Использование моделей Pydantic для валидации входящих данных позволяет не только обеспечить корректность данных, но и автоматически генерировать документацию к API. Это значительно упрощает как разработку, так и использование API, поскольку клиенты могут точно знать, какие данные и в каком формате ожидаются на входе.

**Обработка ошибок и исключений**
В приложении предусмотрена обработка исключений, таких как ошибка доступа к URL или ошибка чтения файла. Это обеспечивает стабильность работы приложения и информативное сообщение пользователю о возникшей проблеме через механизмы HTTP-исключений FastAPI.

**Клонирование репозитория: Склонируйте код приложения на вашу машину.**
- Установка зависимостей: Установите необходимые зависимости с помощью pip install -r requirements.txt.
- Запуск сервера: Запустите приложение командой uvicorn main:app --reload.
**Использование**
Для обработки XML файлов используйте веб-интерфейс или отправьте запрос на /process_link с URL вашего XML файла. Полученный CSV файл будет доступен для загрузки через предоставленную ссылку.

Докажите ваши данные простым и эффективным способом с Magic-XML!
