import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import shutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QPushButton, QLineEdit, QCheckBox,
    QLabel, QFileDialog, QMessageBox, QDialog, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QFrame, QScrollArea, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont

from collections import defaultdict

class BaseWorker(QObject):
    status_updated = pyqtSignal(str)
    log_message = pyqtSignal(str)
    progress_updated = pyqtSignal(int, int)
    finished = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._stop_requested = False

    def stop_processing(self):
        self._stop_requested = True

class FileProcessorWorker(BaseWorker):
    preview_ready = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.folder_path = ""
        self.find_text = ""
        self.replace_text = ""
        self.case_sensitive = False
        self.whole_words = False
        self.include_subfolders = False
        self.ignored_words = []
        self.ignored_paths = []
        self.ignored_extensions = []
        self.is_preview_mode = False
        self.mode = 'replace'

    def setup_parameters(self, folder_path: str, find_text: str, replace_text: str,
                        case_sensitive: bool, whole_words: bool, include_subfolders: bool,
                        ignored_extensions: List[str], ignored_paths: List[str],
                        ignored_words: List[str], is_preview: bool = False, mode: str = 'replace'):
        self.folder_path = folder_path
        self.find_text = find_text
        self.replace_text = replace_text
        self.case_sensitive = case_sensitive
        self.whole_words = whole_words
        self.include_subfolders = include_subfolders
        self.ignored_words = [word.strip().lower() for word in ignored_words]
        self.ignored_paths = [os.path.normpath(path) for path in ignored_paths]
        self.ignored_extensions = [ext.lower().strip() for ext in ignored_extensions]
        self.is_preview_mode = is_preview
        self.mode = mode

    def run(self):
        try:
            if self.is_preview_mode:
                self._run_preview()
            else:
                if self.mode == 'replace':
                    self._run_replacement()
                elif self.mode == 'copy1':
                    self._run_copy1()
                elif self.mode == 'copy2':
                    self._run_copy2()
        except Exception as e:
            self.log_message.emit(f"Критическая ошибка: {str(e)}")
            self.finished.emit(False)

    def _run_preview(self):
        self.status_updated.emit("Сканирование папки для предпросмотра...")
        try:
            self.temp_matches = []
            all_items = self._get_all_items()
            total = len(all_items)
            if self.mode == 'copy2':
                self.status_updated.emit("Симуляция копирования 2...")
                self._simulate_process_dir(self.folder_path)
            else:
                for i, item_path in enumerate(all_items):
                    if self._stop_requested:
                        break
                    self.progress_updated.emit(i + 1, total)
                    self.status_updated.emit(f"Проверка {i + 1} из {total}...")
                    if self._should_ignore_path(item_path):
                        continue
                    item_name = os.path.basename(item_path)
                    if self._contains_ignored_word(item_name):
                        continue
                    is_file = os.path.isfile(item_path)
                    if is_file and self._should_completely_ignore_file(item_path):
                        continue
                    if self.mode == 'replace':
                        if self._text_matches(item_name):
                            new_name = self._replace_text_in_string(item_name)
                            self.temp_matches.append({
                                'path': item_path,
                                'type': 'name',
                                'old_name': item_name,
                                'new_name': new_name,
                                'is_file': is_file
                            })
                        if is_file and not self._should_ignore_file(item_path):
                            content_matches = self._check_file_content(item_path)
                            if content_matches:
                                self.temp_matches.append({
                                    'path': item_path,
                                    'type': 'content',
                                    'matches': content_matches,
                                    'is_file': True
                                })
                    elif self.mode == 'copy1':
                        if Path(item_path).parent == Path(self.folder_path):
                            if self._text_matches(item_name):
                                self._simulate_copy_with_replace(item_path, self.folder_path)
                if self.mode == 'copy1':
                    # Additional loop for top-level files with only content matching
                    for item_path in all_items:
                        if self._stop_requested:
                            break
                        if Path(item_path).parent != Path(self.folder_path):
                            continue
                        if not os.path.isfile(item_path):
                            continue
                        item_name = os.path.basename(item_path)
                        if self._text_matches(item_name):
                            continue  # Already handled
                        if self._should_ignore_path(item_path) or self._contains_ignored_word(item_name) or self._should_ignore_file(item_path) or self._should_completely_ignore_file(item_path):
                            continue
                        content = self._read_file(item_path)
                        if content is None or self._contains_ignored_word(content) or not self._text_matches(content):
                            continue
                        new_name = self._get_unique_name(item_name, self.folder_path)
                        target = os.path.join(self.folder_path, new_name)
                        self.temp_matches.append({
                            'path': target,
                            'type': 'created_content',
                            'old_name': item_name,
                            'new_name': new_name,
                            'is_file': True
                        })
                        content_matches = self._check_file_content(item_path)
                        if content_matches:
                            self.temp_matches.append({
                                'path': target,
                                'type': 'content',
                                'matches': content_matches,
                                'is_file': True
                            })
            self.preview_ready.emit(self.temp_matches)
            self.status_updated.emit("Предпросмотр завершён")
            self.finished.emit(True)
        except Exception as e:
            self.log_message.emit(f"Ошибка при создании предпросмотра: {str(e)}")
            self.finished.emit(False)

    def _get_unique_name(self, original_name: str, target_dir: str) -> str:
        """Generate a unique name by appending _2, _3, etc., if the target exists."""
        base_name, ext = os.path.splitext(original_name)
        target_path = os.path.join(target_dir, original_name)
        if not os.path.exists(target_path):
            return original_name
        counter = 2
        while True:
            new_name = f"{base_name}_{counter}{ext}" if ext else f"{base_name}_{counter}"
            new_path = os.path.join(target_dir, new_name)
            if not os.path.exists(new_path):
                return new_name
            counter += 1

    def _simulate_copy_with_replace(self, source: str, target_parent: str):
        source_name = os.path.basename(source)
        if self._contains_ignored_word(source_name):
            return
        is_file = os.path.isfile(source)
        if is_file and (self._should_ignore_file(source) or self._should_completely_ignore_file(source)):
            return
        content = self._read_file(source) if is_file else None
        if is_file and (content is None or self._contains_ignored_word(content)):
            return
        renamed = self._text_matches(source_name)
        new_name = self._replace_text_in_string(source_name) if renamed else source_name
        target = os.path.join(target_parent, new_name)
        if renamed:
            self.temp_matches.append({
                'path': target,
                'type': 'created_rename',
                'old_name': source_name,
                'new_name': new_name,
                'is_file': is_file
            })
        else:
            self.temp_matches.append({
                'path': target,
                'type': 'created',
                'details': 'Скопировано без переименования',
                'is_file': is_file
            })
        if is_file and content and self._text_matches(content):
            matches = self._check_file_content(source)
            if matches:
                self.temp_matches.append({
                    'path': target,
                    'type': 'content',
                    'matches': matches,
                    'is_file': True
                })
        if not is_file:
            for child in sorted(os.listdir(source)):
                child_path = os.path.join(source, child)
                self._simulate_copy_with_replace(child_path, target)

    def _simulate_process_dir(self, path: str, source_path: str = None):
        if self._stop_requested:
            return
        if source_path is None:
            source_path = path
        items = sorted(os.listdir(source_path))
        for item in items:
            source_item_path = os.path.join(source_path, item)
            if self._should_ignore_path(source_item_path) or self._contains_ignored_word(source_item_path) or self._contains_ignored_word(item):
                continue
            if not self._text_matches(item):
                continue
            new_name = self._replace_text_in_string(item)
            new_path = os.path.join(path, new_name)
            is_file = os.path.isfile(source_item_path)
            if is_file:
                if self._should_ignore_file(source_item_path) or self._should_completely_ignore_file(source_item_path):
                    continue
                content = self._read_file(source_item_path)
                if content is None or self._contains_ignored_word(content):
                    continue
            self.temp_matches.append({
                'path': new_path,
                'type': 'created_rename',
                'old_name': item,
                'new_name': new_name,
                'is_file': is_file
            })
            if is_file:
                content_matches = self._check_file_content(source_item_path)
                if content_matches:
                    self.temp_matches.append({
                        'path': new_path,
                        'type': 'content',
                        'matches': content_matches,
                        'is_file': True
                    })
        # Additional loop for files with only content matching
        for item in items:
            source_item_path = os.path.join(source_path, item)
            if os.path.isfile(source_item_path) and not self._text_matches(item):
                if self._should_ignore_path(source_item_path) or self._contains_ignored_word(source_item_path) or self._contains_ignored_word(item):
                    continue
                if self._should_ignore_file(source_item_path) or self._should_completely_ignore_file(source_item_path):
                    continue
                content = self._read_file(source_item_path)
                if content is None or self._contains_ignored_word(content) or not self._text_matches(content):
                    continue
                new_name = self._get_unique_name(item, path)
                new_path = os.path.join(path, new_name)
                self.temp_matches.append({
                    'path': new_path,
                    'type': 'created_content',
                    'old_name': item,
                    'new_name': new_name,
                    'is_file': True
                })
                content_matches = self._check_file_content(source_item_path)
                if content_matches:
                    self.temp_matches.append({
                        'path': new_path,
                        'type': 'content',
                        'matches': content_matches,
                        'is_file': True
                    })
        for item in items:
            source_item_path = os.path.join(source_path, item)
            if os.path.isdir(source_item_path):
                item_path = os.path.join(path, item)
                self._simulate_process_dir(item_path, source_item_path)
        for item in items:
            source_item_path = os.path.join(source_path, item)
            if self._text_matches(item) and os.path.isdir(source_item_path):
                new_name = self._replace_text_in_string(item)
                new_path = os.path.join(path, new_name)
                self._simulate_process_dir(new_path, source_item_path)

    def _run_replacement(self):
        self.status_updated.emit("Начинаю замену...")
        try:
            all_items = self._get_all_items()
            replaced_count = 0
            filtered_items = [item_path for item_path in all_items if not self._contains_ignored_word(item_path)]
            files = [item for item in filtered_items if os.path.isfile(item)]
            for i, file_path in enumerate(files):
                if self._stop_requested:
                    break
                self.progress_updated.emit(i + 1, len(filtered_items))
                self.status_updated.emit(f"Обработка файла {i + 1} из {len(files)}...")
                if self._contains_ignored_word(os.path.basename(file_path)):
                    continue
                if self._process_file_content(file_path):
                    replaced_count += 1
            filtered_items_reversed = list(reversed(filtered_items))
            for i, item_path in enumerate(filtered_items_reversed):
                if self._stop_requested:
                    break
                self.progress_updated.emit(len(files) + i + 1, len(filtered_items) + len(files))
                self.status_updated.emit(f"Переименование {i + 1} из {len(filtered_items)}...")
                if self._contains_ignored_word(os.path.basename(item_path)):
                    continue
                if self._process_item_name(item_path):
                    replaced_count += 1
            self.log_message.emit(f"Замена завершена. Обработано объектов: {replaced_count}")
            self.status_updated.emit(f"Завершено. Обработано объектов: {replaced_count}")
            self.finished.emit(True)
        except Exception as e:
            self.log_message.emit(f"Ошибка при выполнении замены: {str(e)}")
            self.finished.emit(False)

    def _run_copy1(self):
        self.status_updated.emit("Начинаю копирование 1...")
        try:
            all_top_items = [str(item) for item in Path(self.folder_path).iterdir()]
            filtered_items = [item_path for item_path in all_top_items if not self._contains_ignored_word(item_path) and not self._should_ignore_path(item_path)]
            created_count = 0
            # First, handle name matches
            for i, item_path in enumerate(filtered_items):
                if self._stop_requested:
                    break
                self.progress_updated.emit(i + 1, len(filtered_items))
                self.status_updated.emit(f"Обработка {i + 1} из {len(filtered_items)}...")
                item_name = os.path.basename(item_path)
                if not self._text_matches(item_name):
                    continue
                if self._process_copy_with_replace(item_path, self.folder_path):
                    created_count += 1
            # Additional handling for top-level files with only content matches
            all_top_files = [p for p in all_top_items if os.path.isfile(p)]
            for file_path in all_top_files:
                if self._stop_requested:
                    break
                item_name = os.path.basename(file_path)
                if self._text_matches(item_name):
                    continue  # Already handled
                if self._contains_ignored_word(item_name) or self._should_ignore_path(file_path) or self._should_ignore_file(file_path) or self._should_completely_ignore_file(file_path):
                    continue
                content = self._read_file(file_path)
                if content is None or self._contains_ignored_word(content) or not self._text_matches(content):
                    continue
                new_name = self._get_unique_name(item_name, self.folder_path)
                target = os.path.join(self.folder_path, new_name)
                shutil.copy2(file_path, target)
                if self._process_file_content(target):
                    self.log_message.emit(f"Файл скопирован для замены содержимого: {target} из {file_path}")
                    created_count += 1
            self.log_message.emit(f"Копирование 1 завершено. Создано объектов: {created_count}")
            self.status_updated.emit("Завершено")
            self.finished.emit(True)
        except Exception as e:
            self.log_message.emit(f"Ошибка при копировании 1: {str(e)}")
            self.finished.emit(False)

    def _process_copy_with_replace(self, source: str, target_parent: str) -> bool:
        try:
            if self._stop_requested:
                return False
            source_name = os.path.basename(source)
            if self._contains_ignored_word(source_name):
                return False
            renamed = self._text_matches(source_name)
            new_name = self._replace_text_in_string(source_name) if renamed else source_name
            target = os.path.join(target_parent, new_name)
            if os.path.exists(target):
                if renamed:
                    self.log_message.emit(f"Переименование невозможно - уже существует: {target}")
                    return False
                else:
                    new_name = self._get_unique_name(source_name, target_parent)
                    target = os.path.join(target_parent, new_name)
            is_file = os.path.isfile(source)
            if is_file:
                if self._should_ignore_file(source) or self._should_completely_ignore_file(source):
                    return False
                content = self._read_file(source)
                if content is None or self._contains_ignored_word(content):
                    return False
                shutil.copy2(source, target)
                replaced = self._process_file_content(target)
                msg = f"Файл скопирован: {target}"
                if renamed:
                    msg += f" (переименован из {source_name})"
                if replaced:
                    msg += " (содержимое изменено)"
                self.log_message.emit(msg)
            else:
                os.mkdir(target)
                for child in os.listdir(source):
                    child_path = os.path.join(source, child)
                    self._process_copy_with_replace(child_path, target)
                msg = f"Папка скопирована: {target}"
                if renamed:
                    msg += f" (переименована из {source_name})"
                self.log_message.emit(msg)
            return True
        except Exception as e:
            self.log_message.emit(f"Ошибка при копировании {source}: {str(e)}")
            return False

    def _run_copy2(self):
        self.status_updated.emit("Начинаю копирование 2...")
        try:
            self._process_dir(self.folder_path)
            self.log_message.emit("Копирование 2 завершено.")
            self.status_updated.emit("Завершено")
            self.finished.emit(True)
        except Exception as e:
            self.log_message.emit(f"Ошибка при копировании 2: {str(e)}")
            self.finished.emit(False)

    def _process_dir(self, path: str):
        if self._stop_requested:
            return
        items = sorted(os.listdir(path))
        created_dirs = []
        # Handle name matches
        for item in items:
            item_path = os.path.join(path, item)
            if self._should_ignore_path(item_path) or self._contains_ignored_word(item_path) or self._contains_ignored_word(item):
                continue
            if not self._text_matches(item):
                continue
            new_name = self._replace_text_in_string(item)
            new_path = os.path.join(path, new_name)
            if os.path.exists(new_path):
                self.log_message.emit(f"Уже существует: {new_path}")
                continue
            is_file = os.path.isfile(item_path)
            if is_file:
                if self._should_ignore_file(item_path) or self._should_completely_ignore_file(item_path):
                    continue
                content = self._read_file(item_path)
                if content is None or self._contains_ignored_word(content):
                    continue
                shutil.copy2(item_path, new_path)
                count = self._process_file_content(new_path) or 0
                msg = f"Файл скопирован: {new_path} (переименован из {item})"
                if count > 0:
                    msg += f" - выполнено замен: {count}"
                self.log_message.emit(msg)
            else:
                os.mkdir(new_path)
                shutil.copytree(item_path, new_path, dirs_exist_ok=True)
                self.log_message.emit(f"Папка скопирована: {new_path} (переименована из {item})")
                created_dirs.append(new_path)
        # Additional handling for files with only content matches
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isfile(item_path) and not self._text_matches(item):
                if self._should_ignore_path(item_path) or self._contains_ignored_word(item_path) or self._contains_ignored_word(item):
                    continue
                if self._should_ignore_file(item_path) or self._should_completely_ignore_file(item_path):
                    continue
                content = self._read_file(item_path)
                if content is None or self._contains_ignored_word(content) or not self._text_matches(content):
                    continue
                new_name = self._get_unique_name(item, path)
                new_path = os.path.join(path, new_name)
                shutil.copy2(item_path, new_path)
                count = self._process_file_content(new_path) or 0
                msg = f"Файл скопирован для замены содержимого: {new_path} (из {item})"
                if count > 0:
                    msg += f" - выполнено замен: {count}"
                self.log_message.emit(msg)
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                self._process_dir(item_path)
        for new_path in created_dirs:
            self._process_dir(new_path)

    def _get_all_items(self) -> List[str]:
        items = []
        folder_path = Path(self.folder_path)
        try:
            for item in folder_path.iterdir():
                items.append(str(item))
            if self.include_subfolders:
                for subfolder in folder_path.iterdir():
                    if subfolder.is_dir():
                        for item in subfolder.rglob('*'):
                            items.append(str(item))
        except PermissionError:
            self.log_message.emit(f"Нет доступа к папке: {self.folder_path}")
        return items

    def _text_matches(self, text: str) -> bool:
        if not self.find_text:
            return False
        search_text = self.find_text if self.case_sensitive else self.find_text.lower()
        target_text = text if self.case_sensitive else text.lower()
        if self.whole_words:
            pattern = r'\b' + re.escape(search_text) + r'\b'
            flags = 0 if self.case_sensitive else re.IGNORECASE
            return bool(re.search(pattern, target_text, flags))
        else:
            return search_text in target_text

    def _replace_text_in_string(self, text: str) -> str:
        if not self.find_text:
            return text
        if self.whole_words:
            pattern = r'\b' + re.escape(self.find_text) + r'\b'
            flags = 0 if self.case_sensitive else re.IGNORECASE
            return re.sub(pattern, self.replace_text, text, flags=flags)
        else:
            if self.case_sensitive:
                return text.replace(self.find_text, self.replace_text)
            else:
                pattern = re.escape(self.find_text)
                return re.sub(pattern, self.replace_text, text, flags=re.IGNORECASE)

    def _contains_ignored_word(self, text: str) -> bool:
        if not self.ignored_words:
            return False
        text_lower = text.lower()
        return any(word in text_lower for word in self.ignored_words)

    def _should_ignore_file(self, file_path: str) -> bool:
        binary_extensions = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.svg',
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
            '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
            '.exe', '.dll', '.so', '.dylib', '.bin',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.db', '.sqlite', '.dat', '.cache'
        }
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in binary_extensions

    def _should_completely_ignore_file(self, file_path: str) -> bool:
        if not self.ignored_extensions:
            return False
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in self.ignored_extensions

    def _should_ignore_path(self, item_path: str) -> bool:
        if not self.ignored_paths:
            return False
        item_path_norm = os.path.normpath(item_path)
        return any(item_path_norm.startswith(ignored_path + os.sep) or item_path_norm == ignored_path
                   for ignored_path in self.ignored_paths)

    def _read_file(self, file_path: str) -> str:
        encodings = ['utf-8', 'cp1251', 'latin-1']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return None

    def _check_file_content(self, file_path: str) -> List[Dict]:
        if self._should_ignore_path(file_path) or self._should_completely_ignore_file(file_path) or self._should_ignore_file(file_path):
            return []
        content = self._read_file(file_path)
        if content is None or self._contains_ignored_word(content):
            return []
        matches = []
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            if self._text_matches(line):
                matches.append({
                    'line_number': line_num,
                    'line_content': line.strip(),
                    'replaced_line': self._replace_text_in_string(line).strip()
                })
        return matches

    def _process_file_content(self, file_path: str) -> bool:
        if self._should_ignore_path(file_path) or self._should_completely_ignore_file(file_path) or self._should_ignore_file(file_path):
            return False
        content = self._read_file(file_path)
        used_encoding = 'utf-8'  # default
        if content is None:
            encodings = ['utf-8', 'cp1251', 'latin-1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                        used_encoding = encoding
                        break
                except UnicodeDecodeError:
                    continue
        if content is None or self._contains_ignored_word(content) or not self._text_matches(content):
            return False
        new_content = self._replace_text_in_string(content)
        flags = re.IGNORECASE if not self.case_sensitive else 0
        pattern = r'\b' + re.escape(self.find_text) + r'\b' if self.whole_words else re.escape(self.find_text)
        old_count = len(re.findall(pattern, content, flags))
        with open(file_path, 'w', encoding=used_encoding) as f:
            f.write(new_content)
        self.log_message.emit(f"Файл: {file_path} - выполнено замен: {old_count}")
        return True

    def _process_item_name(self, item_path: str) -> bool:
        try:
            if self._should_ignore_path(item_path) or (os.path.isfile(item_path) and self._should_completely_ignore_file(item_path)):
                return False
            if os.path.isfile(item_path) and not self._should_ignore_file(item_path):
                try:
                    content = self._read_file(item_path)
                    if content is not None and self._contains_ignored_word(content):
                        return False
                except Exception:
                    pass
            item_name = os.path.basename(item_path)
            if not self._text_matches(item_name):
                return False
            new_name = self._replace_text_in_string(item_name)
            new_path = os.path.join(os.path.dirname(item_path), new_name)
            if os.path.exists(new_path):
                self.log_message.emit(f"Переименование невозможно - уже существует: {new_path}")
                return False
            os.rename(item_path, new_path)
            item_type = "Папка" if os.path.isdir(new_path) else "Файл"
            self.log_message.emit(f"{item_type}: {item_name} → {new_name}")
            return True
        except Exception as e:
            self.log_message.emit(f"Ошибка при переименовании {item_path}: {str(e)}")
            return False

class PreviewDialog(QDialog):
    def __init__(self, matches: List[Dict], parent=None):
        super().__init__(parent)
        self.matches = matches
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Предпросмотр совпадений")
        self.setModal(True)
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        info_label = QLabel(f"Найдено совпадений: {len(self.matches)}")
        info_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(info_label)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Элемент", "Тип", "Изменения"])
        self.tree.setAlternatingRowColors(True)
        self._populate_tree()
        layout.addWidget(self.tree)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _populate_tree(self):
        def get_child_count(node):
            if isinstance(node, QTreeWidgetItem):
                return node.childCount()
            else:
                return node.topLevelItemCount()

        def get_child(node, index):
            if isinstance(node, QTreeWidgetItem):
                return node.child(index)
            else:
                return node.topLevelItem(index)

        path_to_changes = defaultdict(list)
        for match in self.matches:
            path_to_changes[match['path']].append(match)
        root = self.tree
        for path in sorted(path_to_changes.keys()):
            try:
                rel_parts = Path(path).relative_to(self.parent().folder_path).parts
            except ValueError:
                rel_parts = Path(path).parts
            current = root
            for part in rel_parts[:-1]:
                found = None
                for i in range(get_child_count(current)):
                    if get_child(current, i).text(0) == part:
                        found = get_child(current, i)
                        break
                if found:
                    current = found
                else:
                    new_item = QTreeWidgetItem(current) if isinstance(current, QTreeWidgetItem) else QTreeWidgetItem(self.tree)
                    new_item.setText(0, part)
                    new_item.setText(1, "Папка")
                    new_item.setText(2, "")
                    current = new_item
            leaf_part = rel_parts[-1]
            leaf = None
            for i in range(get_child_count(current)):
                if get_child(current, i).text(0) == leaf_part:
                    leaf = get_child(current, i)
                    break
            if not leaf:
                leaf = QTreeWidgetItem(current)
                leaf.setText(0, leaf_part)
            changes = path_to_changes[path]
            is_file = changes[0].get('is_file', False)
            leaf.setText(1, "Файл" if is_file else "Папка")
            leaf.setText(2, "")
            for change in changes:
                change_item = QTreeWidgetItem(leaf)
                if change['type'] == 'name':
                    change_item.setText(0, "Переименование")
                    change_item.setText(1, "")
                    change_item.setText(2, f"{change['old_name']} → {change['new_name']}")
                elif change['type'] == 'content':
                    change_item.setText(0, "Изменение содержимого")
                    change_item.setText(1, "")
                    change_item.setText(2, f"Найдено совпадений: {len(change['matches'])}")
                    for content_match in change['matches'][:10]:
                        child_item = QTreeWidgetItem(change_item)
                        child_item.setText(0, f"Строка {content_match['line_number']}")
                        child_item.setText(1, content_match['line_content'][:100] + ("..." if len(content_match['line_content']) > 100 else ""))
                        child_item.setText(2, content_match['replaced_line'][:100] + ("..." if len(content_match['replaced_line']) > 100 else ""))
                elif change['type'] == 'created_rename':
                    change_item.setText(0, "Создано с переименованием")
                    change_item.setText(1, "")
                    change_item.setText(2, f"{change['old_name']} → {change['new_name']}")
                elif change['type'] == 'created':
                    change_item.setText(0, "Создано")
                    change_item.setText(1, "")
                    change_item.setText(2, change.get('details', ""))
                elif change['type'] == 'created_content':
                    change_item.setText(0, "Создано для замены содержимого")
                    change_item.setText(1, "")
                    change_item.setText(2, f"{change['old_name']} → {change['new_name']}")
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        self.tree.resizeColumnToContents(2)

class LogViewerDialog(QDialog):
    def __init__(self, logs: str, parent=None):
        super().__init__(parent)
        self.logs = logs
        self.parent_window = parent
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Логи операций")
        self.setModal(False)
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlainText(self.logs)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        button_layout = QHBoxLayout()
        clear_btn = QPushButton("Очистить логи")
        clear_btn.clicked.connect(self.clear_logs)
        button_layout.addWidget(clear_btn)
        button_layout.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def clear_logs(self):
        self.log_text.clear()
        if hasattr(self.parent_window, 'clear_logs'):
            self.parent_window.clear_logs()

    def closeEvent(self, event):
        if self.parent_window:
            self.parent_window.log_dialog = None
        event.accept()

    def update_logs(self, new_logs: str):
        self.log_text.setPlainText(new_logs)
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logs = []
        self.worker = None
        self.worker_thread = None
        self.log_dialog = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Replitex")
        self.setGeometry(100, 100, 600, 500)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scrollable_widget = QWidget()
        self.scroll_area.setWidget(scrollable_widget)
        main_layout = QVBoxLayout(scrollable_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        central_layout.addWidget(self.scroll_area)
        folder_group = QGroupBox("Рабочая папка")
        folder_layout = QHBoxLayout(folder_group)
        self.folder_path_label = QLabel("Папка не выбрана")
        self.folder_path_label.setStyleSheet("color: #888888; font-style: italic;")
        folder_layout.addWidget(self.folder_path_label)
        self.select_folder_btn = QPushButton("Выбрать папку")
        self.select_folder_btn.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.select_folder_btn)
        main_layout.addWidget(folder_group)
        replace_group = QGroupBox("Параметры замены")
        replace_layout = QFormLayout(replace_group)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Введите текст для поиска...")
        replace_layout.addRow("Найти:", self.find_input)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Введите текст для замены...")
        replace_layout.addRow("Заменить на:", self.replace_input)
        main_layout.addWidget(replace_group)
        ignored_words_group = QGroupBox("Игнорируемые слова")
        ignored_words_layout = QVBoxLayout(ignored_words_group)
        ignored_words_info_label = QLabel("Если в пути файла/папки или содержимом есть эти слова - объект будет полностью проигнорирован:")
        ignored_words_info_label.setStyleSheet("color: #aaaaaa; font-size: 8pt;")
        ignored_words_layout.addWidget(ignored_words_info_label)
        self.ignored_words_input = QLineEdit()
        self.ignored_words_input.setPlaceholderText("Введите слова через запятую: temp, cache, backup")
        ignored_words_layout.addWidget(self.ignored_words_input)
        main_layout.addWidget(ignored_words_group)
        ignore_paths_group = QGroupBox("Игнорируемые пути")
        ignore_paths_layout = QVBoxLayout(ignore_paths_group)
        ignore_info_label = QLabel("Папки и файлы, которые будут полностью проигнорированы:")
        ignore_info_label.setStyleSheet("color: #aaaaaa; font-size: 8pt;")
        ignore_paths_layout.addWidget(ignore_info_label)
        paths_controls_layout = QHBoxLayout()
        self.ignored_paths_list = QTreeWidget()
        self.ignored_paths_list.setHeaderLabels(["Путь", "Тип"])
        self.ignored_paths_list.setMaximumHeight(120)
        self.ignored_paths_list.setAlternatingRowColors(True)
        paths_controls_layout.addWidget(self.ignored_paths_list)
        paths_buttons_layout = QVBoxLayout()
        self.add_folder_btn = QPushButton("Добавить папку")
        self.add_folder_btn.clicked.connect(self.add_ignored_folder)
        paths_buttons_layout.addWidget(self.add_folder_btn)
        self.add_file_btn = QPushButton("Добавить файл")
        self.add_file_btn.clicked.connect(self.add_ignored_file)
        paths_buttons_layout.addWidget(self.add_file_btn)
        self.remove_path_btn = QPushButton("Удалить")
        self.remove_path_btn.clicked.connect(self.remove_ignored_path)
        paths_buttons_layout.addWidget(self.remove_path_btn)
        paths_buttons_layout.addStretch()
        paths_controls_layout.addLayout(paths_buttons_layout)
        ignore_paths_layout.addLayout(paths_controls_layout)
        main_layout.addWidget(ignore_paths_group)
        options_group = QGroupBox("Опции поиска")
        options_layout = QVBoxLayout(options_group)
        self.case_sensitive_cb = QCheckBox("Учитывать регистр")
        options_layout.addWidget(self.case_sensitive_cb)
        self.whole_words_cb = QCheckBox("Только целые слова")
        options_layout.addWidget(self.whole_words_cb)
        self.include_subfolders_cb = QCheckBox("Включить подпапки")
        self.include_subfolders_cb.setChecked(True)
        options_layout.addWidget(self.include_subfolders_cb)
        extensions_layout = QHBoxLayout()
        extensions_layout.addWidget(QLabel("Полностью игнорировать расширения (через запятую):"))
        extensions_layout.addStretch()
        options_layout.addLayout(extensions_layout)
        self.ignored_extensions_input = QLineEdit()
        self.ignored_extensions_input.setPlaceholderText("Например: .png, .jpg, .bin")
        options_layout.addWidget(self.ignored_extensions_input)
        main_layout.addWidget(options_group)
        mode_group = QGroupBox("Режим обработки")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_button_group = QButtonGroup(self)
        self.replace_radio = QRadioButton("Замена")
        self.copy1_radio = QRadioButton("Копирование 1")
        self.copy2_radio = QRadioButton("Копирование 2")
        self.replace_radio.setChecked(True)
        self.mode_button_group.addButton(self.replace_radio)
        self.mode_button_group.addButton(self.copy1_radio)
        self.mode_button_group.addButton(self.copy2_radio)
        mode_layout.addWidget(self.replace_radio)
        mode_layout.addWidget(self.copy1_radio)
        mode_layout.addWidget(self.copy2_radio)
        main_layout.addWidget(mode_group)
        buttons_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Предпросмотр")
        self.preview_btn.clicked.connect(self.show_preview)
        buttons_layout.addWidget(self.preview_btn)
        self.start_btn = QPushButton("Начать замену")
        self.start_btn.clicked.connect(self.start_processing)
        buttons_layout.addWidget(self.start_btn)
        self.logs_btn = QPushButton("Показать логи")
        self.logs_btn.clicked.connect(self.show_logs)
        buttons_layout.addWidget(self.logs_btn)
        main_layout.addLayout(buttons_layout)
        main_layout.addStretch()
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)
        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet("padding: 5px; color: #00aa00;")
        main_layout.addWidget(self.status_label)
        self.replace_radio.toggled.connect(self.update_start_button)
        self.copy1_radio.toggled.connect(self.update_start_button)
        self.copy2_radio.toggled.connect(self.update_start_button)
        self.update_start_button()
        self._update_ui_state()

    def update_start_button(self):
        if self.replace_radio.isChecked():
            self.start_btn.setText("Начать замену")
        elif self.copy1_radio.isChecked():
            self.start_btn.setText("Начать копирование 1")
        else:
            self.start_btn.setText("Начать копирование 2")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите рабочую папку",
            os.path.expanduser("~")
        )
        if folder:
            self.folder_path = folder
            self.folder_path_label.setText(folder)
            self.folder_path_label.setStyleSheet("color: #ffffff;")
            self._update_ui_state()

    def _update_ui_state(self):
        has_folder = hasattr(self, 'folder_path')
        has_find_text = bool(self.find_input.text().strip())
        self.preview_btn.setEnabled(has_folder and has_find_text)
        self.start_btn.setEnabled(has_folder and has_find_text)
        self.find_input.textChanged.connect(self._update_ui_state)

    def _get_ignored_extensions(self) -> List[str]:
        text = self.ignored_extensions_input.text().strip()
        if not text:
            return []
        extensions = [ext.strip() for ext in text.split(',')]
        return [ext if ext.startswith('.') else f'.{ext}' for ext in extensions if ext]

    def _get_ignored_words(self) -> List[str]:
        text = self.ignored_words_input.text().strip()
        if not text:
            return []
        words = [word.strip() for word in text.split(',')]
        return [word for word in words if word]

    def add_ignored_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для игнорирования",
            os.path.expanduser("~")
        )
        if folder:
            for i in range(self.ignored_paths_list.topLevelItemCount()):
                item = self.ignored_paths_list.topLevelItem(i)
                if item.text(0) == folder:
                    QMessageBox.information(self, "Информация", "Эта папка уже добавлена в список.")
                    return
            item = QTreeWidgetItem(self.ignored_paths_list)
            item.setText(0, folder)
            item.setText(1, "Папка")

    def add_ignored_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл для игнорирования",
            os.path.expanduser("~"),
            "Все файлы (*.*)"
        )
        if file_path:
            for i in range(self.ignored_paths_list.topLevelItemCount()):
                item = self.ignored_paths_list.topLevelItem(i)
                if item.text(0) == file_path:
                    QMessageBox.information(self, "Информация", "Этот файл уже добавлен в список.")
                    return
            item = QTreeWidgetItem(self.ignored_paths_list)
            item.setText(0, file_path)
            item.setText(1, "Файл")

    def remove_ignored_path(self):
        current_item = self.ignored_paths_list.currentItem()
        if current_item:
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Удалить из списка игнорируемых:\n{current_item.text(0)}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                root = self.ignored_paths_list.invisibleRootItem()
                root.removeChild(current_item)

    def _get_ignored_paths(self) -> List[str]:
        return [self.ignored_paths_list.topLevelItem(i).text(0) for i in range(self.ignored_paths_list.topLevelItemCount())]

    def show_preview(self):
        if not self._validate_inputs():
            return
        self._disable_ui()
        self.status_label.setText("Создание предпросмотра...")
        mode = 'replace' if self.replace_radio.isChecked() else 'copy1' if self.copy1_radio.isChecked() else 'copy2'
        self.worker = FileProcessorWorker()
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker.setup_parameters(
            folder_path=self.folder_path,
            find_text=self.find_input.text(),
            replace_text=self.replace_input.text(),
            case_sensitive=self.case_sensitive_cb.isChecked(),
            whole_words=self.whole_words_cb.isChecked(),
            include_subfolders=self.include_subfolders_cb.isChecked(),
            ignored_words=self._get_ignored_words(),
            ignored_extensions=self._get_ignored_extensions(),
            ignored_paths=self._get_ignored_paths(),
            is_preview=True,
            mode=mode
        )
        self.worker.status_updated.connect(self.status_label.setText)
        self.worker.log_message.connect(self._add_log)
        self.worker.preview_ready.connect(self._show_preview_dialog)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def start_processing(self):
        if not self._validate_inputs():
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите начать операцию? Это действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._disable_ui()
        self.status_label.setText("Начинаю операцию...")
        mode = 'replace' if self.replace_radio.isChecked() else 'copy1' if self.copy1_radio.isChecked() else 'copy2'
        self.worker = FileProcessorWorker()
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.show_logs()
        self.worker.setup_parameters(
            folder_path=self.folder_path,
            find_text=self.find_input.text(),
            replace_text=self.replace_input.text(),
            case_sensitive=self.case_sensitive_cb.isChecked(),
            whole_words=self.whole_words_cb.isChecked(),
            include_subfolders=self.include_subfolders_cb.isChecked(),
            ignored_words=self._get_ignored_words(),
            ignored_extensions=self._get_ignored_extensions(),
            ignored_paths=self._get_ignored_paths(),
            is_preview=False,
            mode=mode
        )
        self.worker.status_updated.connect(self.status_label.setText)
        self.worker.log_message.connect(self._add_log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def show_logs(self):
        logs_text = '\n'.join(self.logs) if self.logs else "Логи пусты"
        if self.log_dialog and self.log_dialog.isVisible():
            self.log_dialog.update_logs(logs_text)
            self.log_dialog.raise_()
            self.log_dialog.activateWindow()
            return
        self.log_dialog = LogViewerDialog(logs_text, self)
        self.log_dialog.show()

    def clear_logs(self):
        self.logs.clear()

    def _validate_inputs(self) -> bool:
        if not hasattr(self, 'folder_path'):
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите рабочую папку.")
            return False
        if not self.find_input.text().strip():
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите текст для поиска.")
            return False
        if not os.path.exists(self.folder_path):
            QMessageBox.warning(self, "Ошибка", "Выбранная папка не существует.")
            return False
        return True

    def _disable_ui(self):
        self.select_folder_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.find_input.setEnabled(False)
        self.replace_input.setEnabled(False)
        self.ignored_words_input.setEnabled(False)
        self.add_folder_btn.setEnabled(False)
        self.add_file_btn.setEnabled(False)
        self.remove_path_btn.setEnabled(False)
        self.case_sensitive_cb.setEnabled(False)
        self.whole_words_cb.setEnabled(False)
        self.include_subfolders_cb.setEnabled(False)
        self.ignored_extensions_input.setEnabled(False)
        self.replace_radio.setEnabled(False)
        self.copy1_radio.setEnabled(False)
        self.copy2_radio.setEnabled(False)

    def _enable_ui(self):
        self.select_folder_btn.setEnabled(True)
        self.find_input.setEnabled(True)
        self.replace_input.setEnabled(True)
        self.ignored_words_input.setEnabled(True)
        self.add_folder_btn.setEnabled(True)
        self.add_file_btn.setEnabled(True)
        self.remove_path_btn.setEnabled(True)
        self.case_sensitive_cb.setEnabled(True)
        self.whole_words_cb.setEnabled(True)
        self.include_subfolders_cb.setEnabled(True)
        self.ignored_extensions_input.setEnabled(True)
        self.replace_radio.setEnabled(True)
        self.copy1_radio.setEnabled(True)
        self.copy2_radio.setEnabled(True)
        self._update_ui_state()

    def _add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if self.log_dialog and self.log_dialog.isVisible():
            logs_text = '\n'.join(self.logs)
            self.log_dialog.update_logs(logs_text)

    def _show_preview_dialog(self, matches: List[Dict]):
        if not matches:
            QMessageBox.information(self, "Предпросмотр", "Совпадений не найдено.")
            return
        dialog = PreviewDialog(matches, self)
        dialog.exec()

    def _on_worker_finished(self, success: bool):
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
        self.worker = None
        self._enable_ui()
        if success:
            self.status_label.setText("Операция завершена успешно")
            self.status_label.setStyleSheet("padding: 5px; color: #00aa00;")
        else:
            self.status_label.setText("Операция завершена с ошибками")
            self.status_label.setStyleSheet("padding: 5px; color: #ff6666;")
        QTimer.singleShot(5000, lambda: self.status_label.setText("Готов к работе"))
        QTimer.singleShot(5000, lambda: self.status_label.setStyleSheet("padding: 5px; color: #00aa00;"))

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Операция всё ещё выполняется. Вы уверены, что хотите закрыть приложение?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self.worker:
                    self.worker.stop_processing()
                if self.worker_thread:
                    self.worker_thread.quit()
                    self.worker_thread.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def apply_dark_theme(app: QApplication):
    dark_style = """
    QMainWindow, QDialog, QWidget {
        background-color: #2b2b2b;
        color: #ffffff;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 9pt;
    }
    QGroupBox {
        font-weight: bold;
        border: 2px solid #555555;
        border-radius: 8px;
        margin-top: 1ex;
        padding-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 10px 0 10px;
        color: #ffffff;
    }
    QPushButton {
        background-color: #404040;
        border: 1px solid #606060;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: bold;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #505050;
        border-color: #707070;
    }
    QPushButton:pressed {
        background-color: #353535;
        border-color: #808080;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        border-color: #404040;
        color: #666666;
    }
    QLineEdit {
        background-color: #3a3a3a;
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 6px;
        selection-background-color: #0078d4;
    }
    QLineEdit:focus {
        border-color: #0078d4;
    }
    QLineEdit:disabled {
        background-color: #2a2a2a;
        color: #666666;
    }
    QCheckBox {
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border-radius: 3px;
        border: 1px solid #555555;
        background-color: #3a3a3a;
    }
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border-color: #0078d4;
        image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEwIDNMNC41IDguNUwyIDYiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
    }
    QCheckBox::indicator:hover {
        border-color: #707070;
    }
    QCheckBox:disabled {
        color: #666666;
    }
    QCheckBox::indicator:disabled {
        background-color: #2a2a2a;
        border-color: #404040;
    }
    QLabel {
        color: #ffffff;
    }
    QTextEdit {
        background-color: #3a3a3a;
        border: 1px solid #555555;
        border-radius: 4px;
        selection-background-color: #0078d4;
        font-family: 'Consolas', 'Courier New', monospace;
    }
    QTreeWidget {
        background-color: #3a3a3a;
        border: 1px solid #555555;
        border-radius: 4px;
        selection-background-color: #0078d4;
        alternate-background-color: #404040;
    }
    QTreeWidget::item {
        padding: 4px;
        border: none;
    }
    QTreeWidget::item:selected {
        background-color: #0078d4;
    }
    QTreeWidget::item:hover {
        background-color: #505050;
    }
    QHeaderView::section {
        background-color: #404040;
        border: 1px solid #555555;
        padding: 6px;
        font-weight: bold;
    }
    QFrame[frameShape="4"] {
        border: none;
        border-top: 1px solid #555555;
    }
    QMessageBox {
        background-color: #2b2b2b;
    }
    QMessageBox QPushButton {
        min-width: 60px;
        padding: 6px 12px;
    }
    QScrollArea {
        background-color: #2b2b2b;
        border: none;
    }
    QScrollBar:vertical {
        background-color: #2b2b2b;
        width: 12px;
        border-radius: 6px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background-color: #555555;
        border-radius: 6px;
        min-height: 20px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #666666;
    }
    QScrollBar::handle:vertical:pressed {
        background-color: #777777;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    QScrollBar:horizontal {
        background-color: #2b2b2b;
        height: 12px;
        border-radius: 6px;
        margin: 0;
    }
    QScrollBar::handle:horizontal {
        background-color: #555555;
        border-radius: 6px;
        min-width: 20px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #666666;
    }
    QScrollBar::handle:horizontal:pressed {
        background-color: #777777;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        border: none;
        background: none;
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }
    QRadioButton {
        spacing: 8px;
    }
    QRadioButton::indicator {
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 1px solid #555555;
        background-color: #3a3a3a;
    }
    QRadioButton::indicator:checked {
        background-color: #0078d4;
        border-color: #0078d4;
    }
    QRadioButton::indicator:hover {
        border-color: #707070;
    }
    """
    app.setStyleSheet(dark_style)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Replitex")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Replitex Team")
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
