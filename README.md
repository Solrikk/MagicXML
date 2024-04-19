<div align="center">
  <img src="assets/searching.png" width="30%"/>
</div>

# Magic-XML ⚡️

### _Magic-XML доступно на https://xmlmagic.ru_

##

<div align="center">
  <h3> <a href="https://github.com/Solrikk/MagicXML/blob/main/README.md"> English | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_RU.md">Русский</a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_GE.md"> Deutsch </a> | <a href="https://github.com/Solrikk/MagicXML/blob/main/README_JP.md"> 日本語 </a> | <a href="README_KR.md">한국어</a> | <a href="README_CN.md">中文</a> </h3>
</div>

**_Magic-XML_** is a modern web application designed for the convenient and fast conversion of data from XML files into the CSV format. The application utilizes the power of FastAPI for high-performance request processing and applies machine learning algorithms and natural language processing for efficient analysis and classification of textual information. Magic-XML is perfectly suited for data analysts, developers, and anyone working with large volumes of XML data and looking to optimize and simplify their analysis.

**_Features_** - Automatic data classification and cleaning. Magic-XML automatically classifies information from XML into categories and cleanses textual data from unwanted HTML tags, ensuring the purity and readability of the final CSV file.

**_Ease of working with custom categories_** - Ease of working with custom categories - Users can set their own categories for data classification, making the application flexible and adaptable to specific project requirements.

**_Fast and secure processing_** - Загружаемые данные обрабатываются с высокой скоростью благодаря оптимизированному бэкэнду на FastAPI. Процесс обработки полностью автоматизирован и обеспечивает сохранность данных.

**_Simple and intuitive interface_** - Magic-XML предлагает простой в использовании веб-интерфейс, а также поддержку API для автоматизации задач, что делает приложение доступным для пользователей с различным уровнем знаний и опыта.

**_Технологический стек_**
FastAPI: Эффективный и быстрый веб-фреймворк для создания API.
Spacy и sklearn: Библиотеки для обработки естественного языка и машинного обучения.
XML и CSV: Поддержка работы с популярными форматами данных.
Jinja2: Мощная система шаблонов для Python, используемая для генерации HTML на стороне сервера.
Как начать
Для запуска Magic-XML требуется предустановленный Python версии 3.7 или выше. Выполните следующие шаги для начала работы:

Клонирование репозитория: Склонируйте код приложения на вашу машину.
Установка зависимостей: Установите необходимые зависимости с помощью pip install -r requirements.txt.
Запуск сервера: Запустите приложение командой uvicorn main:app --reload.
Использование
Для обработки XML файлов используйте веб-интерфейс или отправьте запрос на /process_link с URL вашего XML файла. Полученный CSV файл будет доступен для загрузки через предоставленную ссылку.

Докажите ваши данные простым и эффективным способом с Magic-XML!
