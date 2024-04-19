<div align="center">
  <img src="assets/working.png" width="30%"/>
</div>

# Magic-XML ⚡️

### _Magic-XML доступно на https://xmlmagic.ru_

##

<div align="center">
  <h3> <a href="https://github.com/Solrikk/MagicXML/blob/main/README.md"> English | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_RU.md">Русский</a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_GE.md"> Deutsch </a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_JP.md"> 日本語 </a> | <a href="README_KR.md">한국어</a> | <a href="README_CN.md">中文</a> </h3>
</div>

**_Magic-XML_** — это современное веб-приложение, разработанное для удобного и быстрого преобразования данных из XML файлов в формат CSV. Приложение использует мощь FastAPI для обеспечения высокой производительности обработки запросов, а также применяет алгоритмы машинного обучения и обработки естественного языка для эффективного анализа и классификации текстовой информации. Magic-XML идеально подходит для аналитиков данных, разработчиков и всех, кто работает с большим объемом данных в формате XML и стремится к их оптимизации и упрощению анализа.


**Зависимости**
- `fastapi` - фреймворк для создания API с автоматической документацией.
- `uvicorn` - ASGI-сервер для запуска FastAPI приложения.
- `requests` - библиотека для выполнения HTTP-запросов.
- `xml.etree.ElementTree` - модуль для обработки XML.
- `csv` - модуль для работы с CSV-файлами.
- `os` - модуль для работы с операционной системой, нужен для создания директории.
- `Jinja2Templates` из инструмент для работы с шаблонами Jinja2.
- `StaticFiles` - для обслуживания статических файлов.
- `BaseModel` из `pydantic` - для валидации данных.
- `FileResponse` для отправки файлов в ответах.
- `spacy` - для обработки естественного языка, используется для категоризации.
- `TfidfVectorizer` для векторизации текста.
- `cosine_similarity` для вычисления косинусного сходства.
- `re` - модуль для работы с регулярными выражениями.

**Структура приложения**

- `FastAPI приложение`: Инициализация основного приложения с `FastAPI`, настройка путей для статических файлов и шаблонизатора `Jinja2`.
- Класс `LinkData` (Pydantic модель): Модель для валидации входящих данных, получаемых через `POST-запрос` на `/process_link.`

Функции обработки данных:

- `get_category_replacement()`: Функция для категоризации на основе косинусного сходства между векторами.
- `load_custom_categories()`: Загрузка пользовательских категорий из CSV-файла.
- `remove_unwanted_tags()`: Очистка описаний товаров от HTML-тегов.
- `process_link()`: Основная функция для обработки XML-ссылки, извлечения и сохранения данных в CSV-файл.

Маршруты FastAPI:
- `GET /:` Отображение главной страницы через Jinja2 шаблон.
- `POST /process_link:` Принимает данные для обработки ссылки и генерирует CSV-файл.
- `GET /download/data_files/{filename}:` Возможность скачивания сгенерированных CSV-файлов.

**Асинхронная обработка запросов**
FastAPI основан на Starlette и позволяет обрабатывать запросы асинхронно, используя async и await. Это дает приложению возможность масштабироваться и обслуживать большое количество запросов эффективно, улучшая производительность на I/O операциях, таких как запросы к внешним API или операции чтения файлов. В данном приложении асинхронная обработка может быть особенно полезна при загрузке файлов через ендпоинт /download/data_files/{filename}, где асинхронное чтение файла может значительно снизить время ожидания для клиента.

**Работа с текстом и естественным языком**
Использование spaCy и TfidfVectorizer из scikit-learn для категоризации текста показывает, как можно эффективно применять инструменты машинного обучения в веб-приложениях. spaCy используется для предварительной обработки текста на русском языке, что важно для точной работы категоризации, ведь обработка текста включает в себя многие аспекты, такие как лемматизация и удаление стоп-слов, которые значительно влияют на итоговую точность. TfidfVectorizer преобразует текст в векторное представление, позволяя затем вычислить косинусное сходство между векторами, что используется для выбора наиболее подходящей категории для текста.

**Обработка XML и генерация CSV**
В приложении осуществляется парсинг XML-файлов для извлечения данных о товарах, что демонстрирует умение работать с различными форматами данных. После извлечения данных и их классификации происходит их сохранение в формате CSV, который является широко принятым стандартом для обмена табличными данными и может быть легко импортирован в различные системы и приложения для последующего анализа.

**Кастомизация категоризации**
Особенностями реализации является возможность кастомизации категорий через внешний CSV-файл. Это дает пользователю гибкость в управлении категориями товаров без изменения кода, что делает приложение более удобным и адаптивным под различные бизнес-задачи.

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
