# Replitex
## Русский:
### Описание
**Replitex** — это инструмент с графическим интерфейсом (GUI) на базе PyQt6, предназначенный для поиска и массовой замены текста в файлах и папках. Программа позволяет находить и изменять текстовые данные как в содержимом файлов, так и в именах файлов и каталогов. Поддерживается гибкая настройка поиска, фильтрация, исключение путей/расширений, а также безопасный предпросмотр изменений.

### Основные возможности
* **Поиск и замена в именах и содержимом:** Выполнение замен как в названиях файлов и каталогов, так и внутри текстовых файлов.
* **3 режима обработки:**
  * **Замена (Replace):** Прямая замена текста в исходной директории.
  * **Копирование 1 (Copy 1):** Создание копий файлов/папок корневого уровня при наличии совпадений с изменением текста в копиях.
  * **Копирование 2 (Copy 2):** Глубокое структурированное копирование всей иерархии папок и файлов с параллельной заменой текста.
* **Гибкие опции поиска:**
  * Учет регистра (*Case Sensitive*).
  * Поиск только целых слов (*Whole Words Only*).
  * Включение или исключение подпапок из зоны поиска (*Include Subfolders*).
* **Система фильтрации и игнорирования:**
  * **Игнорируемые слова:** Абсолютное исключение файлов, папок или содержимого, содержащего указанные ключевые слова.
  * **Игнорируемые пути:** Исключение конкретных файлов и папок из списка обработки.
  * **Игнорирование расширений:** Исключение файлов с определенными расширениями (например, `.png`, `.bin`, `.log`).
  * **Автоматическое пропускание бинарных файлов:** Защита от повреждения исполняемых файлов, архивов, медиа и баз данных.
* **Предпросмотр (Preview):** Древовидное отображение планируемых изменений (переименований и строк в содержимом) до фактического выполнения операции.
* **Кастомизация интерфейса и локализация:**
  * Поддержка тем оформления: *Dark* (тёмная), *Light* (светлая), *Poisonous Purple* (ядовитый пурпур), *Midnight Gold* (полночное золото).
  * Двуязычный интерфейс: Русский / English.
* **Логирование:** Просмотр и очистка логов выполненных операций в отдельном окне.

## English:
### Overview
**Replitex** provides an intuitive interface for replacing text both inside file contents and within file/folder names. It offers flexible search parameters, comprehensive path/extension filtering, binary file detection, and a built-in preview system to verify all upcoming changes safely before modifying any files.

### Features
* **File & Folder Operations:**
  * Search and replace text within file contents.
  * Rename files and directories matching search patterns.
* **3 Execution Modes:**
  * **Replace:** Direct batch search and replacement inside the target directory.
  * **Copy 1:** Copies top-level files/directories containing matches and performs replacements on the copied items.
  * **Copy 2:** Recursively mirrors the entire directory hierarchy while replacing matching text in the duplicated files and folders.
* **Flexible Search Options:**
  * **Case Sensitive:** Enable or disable case-sensitive matching.
  * **Whole Words Only:** Restrict matches strictly to whole words.
  * **Include Subfolders:** Toggle recursive scanning through subdirectories.
* **Advanced Filtering & Exclusions:**
  * **Ignored Words:** Skip files, folders, or lines containing specific keyword list.
  * **Ignored Paths:** Exclude specific files and directories from processing.
  * **Ignored Extensions:** Skip files by extensions (e.g., `.png`, `.bin`, `.log`).
  * **Automatic Binary Detection:** Built-in safeguards to prevent accidental alteration or corruption of binary, executable, and media files.
* **Safe Preview System:**
  * Interactive tree view displaying exact file/folder renames and line-by-line content changes prior to execution.
* **Themes & Localization:**
  * **Multi-language Support:** English and Russian.
  * **Color Themes:** *Dark*, *Light*, *Poisonous Purple*, and *Midnight Gold*.
* **Logging:**
  * Dedicated Log Viewer dialog to monitor and manage application event logs.
