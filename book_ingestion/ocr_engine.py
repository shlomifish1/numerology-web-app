"""OCR and lightweight text extraction helpers for research corpora."""

from __future__ import annotations

import html
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List

try:
    import pytesseract
    from PIL import Image
    TESSERACT_PYTHON_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    TESSERACT_PYTHON_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    convert_from_path = None
    PDF2IMAGE_AVAILABLE = False


def _ai_agents_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ocr_root() -> Path:
    return _ai_agents_root() / 'ocr'


def _legacy_site_packages() -> Path:
    return _ocr_root() / 'venv' / 'Lib' / 'site-packages'


def _extend_legacy_paths() -> None:
    for candidate in (_ocr_root(), _legacy_site_packages()):
        if candidate.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)


_extend_legacy_paths()

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PdfReader = None
    PYPDF2_AVAILABLE = False

try:
    import fitz  # type: ignore
    FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    FITZ_AVAILABLE = False


class OCREngine:
    TEXT_EXTENSIONS = {'.txt', '.md', '.csv'}
    HTML_EXTENSIONS = {'.html', '.htm'}
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
    MIN_TEXT_CHARS = 80

    def __init__(self, language: str = 'heb+eng'):
        self.language = language
        self.tessdata_dir = _ocr_root() / 'tessdata'
        self.tesseract_cmd = self._discover_tesseract_cmd()
        if self.tessdata_dir.exists():
            os.environ['TESSDATA_PREFIX'] = str(self.tessdata_dir)
        if TESSERACT_PYTHON_AVAILABLE and self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def inspect(self, source_path: str) -> Dict[str, object]:
        path = Path(source_path)
        extension = path.suffix.lower()
        result = {
            'status': 'metadata_only',
            'text': '',
            'metadata': {
                'extension': extension,
                'size_bytes': path.stat().st_size if path.exists() else 0,
                'ocr_capabilities': self.capabilities(),
            },
        }
        if not path.exists():
            result['status'] = 'missing_file'
            return result
        if extension in self.TEXT_EXTENSIONS:
            text = path.read_text(encoding='utf-8', errors='ignore')
            result['status'] = 'text_extracted'
            result['text'] = text
            return result
        if extension in self.HTML_EXTENSIONS:
            raw = path.read_text(encoding='utf-8', errors='ignore')
            text = re.sub(r'<[^>]+>', ' ', raw)
            result['status'] = 'text_extracted'
            result['text'] = html.unescape(re.sub(r'\s+', ' ', text))
            return result
        if extension == '.docx':
            result.update(self._extract_docx(path))
            return result
        if extension == '.epub':
            result.update(self._extract_epub(path))
            return result
        if extension == '.pdf':
            result.update(self._inspect_pdf(path))
            return result
        if extension in self.IMAGE_EXTENSIONS:
            result.update(self._inspect_image(path))
            return result
        return result

    def capabilities(self) -> Dict[str, object]:
        legacy_root = _ocr_root()
        legacy_packages = _legacy_site_packages()
        has_tessdata = self.tessdata_dir.exists()
        has_tesseract = bool(self.tesseract_cmd)
        return {
            'language': self.language,
            'tesseract_cmd': self.tesseract_cmd or '',
            'tesseract_available': has_tesseract,
            'tessdata_dir': str(self.tessdata_dir),
            'tessdata_available': has_tessdata,
            'pytesseract_available': TESSERACT_PYTHON_AVAILABLE,
            'pypdf2_available': PYPDF2_AVAILABLE,
            'fitz_available': FITZ_AVAILABLE,
            'pdf2image_available': PDF2IMAGE_AVAILABLE,
            'pil_available': Image is not None,
            'legacy_ocr_root': str(legacy_root),
            'legacy_ocr_root_available': legacy_root.exists(),
            'legacy_site_packages': str(legacy_packages),
            'legacy_site_packages_available': legacy_packages.exists(),
            'full_ocr_available': bool(has_tesseract and TESSERACT_PYTHON_AVAILABLE and FITZ_AVAILABLE and Image is not None),
            'text_extraction_available': bool(PYPDF2_AVAILABLE or FITZ_AVAILABLE),
        }

    def runtime_summary(self) -> Dict[str, object]:
        capabilities = self.capabilities()
        blockers: List[str] = []
        if not capabilities['tesseract_available']:
            blockers.append('tesseract_missing')
        if not capabilities['pytesseract_available']:
            blockers.append('pytesseract_missing')
        if not capabilities['fitz_available']:
            blockers.append('fitz_missing')
        return {
            'capabilities': capabilities,
            'ready_for_full_ocr': bool(capabilities['full_ocr_available']),
            'ready_for_text_extraction': bool(capabilities['text_extraction_available']),
            'blockers': blockers,
            'recommended_action': self.recommended_action(),
        }

    def recommended_action(self) -> str:
        capabilities = self.capabilities()
        if capabilities['full_ocr_available']:
            return 'להריץ OCR על הקבצים הממתינים.'
        if capabilities['text_extraction_available']:
            return 'להמשיך בחילוץ טקסט מובנה; עבור OCR מלא חסר כרגע Tesseract.'
        return 'להשלים סביבת OCR בסיסית לפני המשך עיבוד PDF.'

    def _discover_tesseract_cmd(self) -> str | None:
        env_value = os.environ.get('TESSERACT_CMD')
        candidates = [
            Path(env_value) if env_value else None,
            Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),
            Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'),
            _ocr_root() / 'tesseract.exe',
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)
        which_value = shutil.which('tesseract')
        if which_value:
            return which_value
        return None

    def _extract_docx(self, path: Path) -> Dict[str, object]:
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read('word/document.xml').decode('utf-8', errors='ignore')
            text = re.sub(r'<[^>]+>', ' ', xml)
            return {
                'status': 'text_extracted',
                'text': re.sub(r'\s+', ' ', html.unescape(text)),
                'metadata': {'parser': 'zipfile-docx'},
            }
        except Exception as exc:
            return {'status': 'docx_error', 'text': '', 'metadata': {'error': str(exc)}}

    def _extract_epub(self, path: Path) -> Dict[str, object]:
        try:
            snippets: List[str] = []
            with zipfile.ZipFile(path) as archive:
                members = [name for name in archive.namelist() if name.lower().endswith(('.xhtml', '.html', '.htm', '.xml'))]
                for name in members[:25]:
                    raw = archive.read(name).decode('utf-8', errors='ignore')
                    text = re.sub(r'<[^>]+>', ' ', raw)
                    clean = html.unescape(re.sub(r'\s+', ' ', text)).strip()
                    if clean:
                        snippets.append(clean)
            joined = '\n'.join(snippets)
            return {
                'status': 'text_extracted' if joined else 'metadata_only',
                'text': joined,
                'metadata': {'parser': 'zipfile-epub', 'documents_sampled': min(len(snippets), 25)},
            }
        except Exception as exc:
            return {'status': 'epub_error', 'text': '', 'metadata': {'error': str(exc)}}

    def _inspect_pdf(self, path: Path) -> Dict[str, object]:
        py_pdf_result = self._extract_pdf_text_with_pypdf2(path)
        py_pdf_text = str(py_pdf_result.get('text') or '')
        if len(py_pdf_text.strip()) >= self.MIN_TEXT_CHARS:
            return py_pdf_result

        fitz_result = self._extract_pdf_text_with_fitz(path)
        fitz_text = str(fitz_result.get('text') or '')
        if len(fitz_text.strip()) > len(py_pdf_text.strip()):
            candidate = fitz_result
        else:
            candidate = py_pdf_result
        if len(str(candidate.get('text') or '').strip()) >= self.MIN_TEXT_CHARS:
            return candidate

        if self._can_run_ocr() and FITZ_AVAILABLE:
            ocr_result = self._ocr_pdf_with_fitz(path)
            if len((ocr_result.get('text') or '').strip()) >= self.MIN_TEXT_CHARS:
                return ocr_result

        text = str(candidate.get('text') or '').strip()
        candidate['status'] = 'ocr_pending' if not text else 'text_extracted'
        return candidate

    def _extract_pdf_text_with_pypdf2(self, path: Path) -> Dict[str, object]:
        if not PYPDF2_AVAILABLE:
            return {'status': 'ocr_pending', 'text': '', 'metadata': {'parser': 'pdf-no-parser'}}
        try:
            reader = PdfReader(str(path))
            parts: List[str] = []
            total_pages = len(reader.pages)
            for index, page in enumerate(reader.pages[:40], start=1):
                try:
                    text = page.extract_text() or ''
                except Exception:
                    text = ''
                if text.strip():
                    parts.append(f'--- Page {index} ---\n{text.strip()}')
            joined = '\n'.join(parts)
            return {
                'status': 'text_extracted' if joined.strip() else 'ocr_pending',
                'text': joined,
                'metadata': {'parser': 'PyPDF2', 'pages_sampled': min(total_pages, 40)},
            }
        except Exception as exc:
            return {'status': 'pdf_error', 'text': '', 'metadata': {'error': str(exc), 'parser': 'PyPDF2'}}

    def _extract_pdf_text_with_fitz(self, path: Path) -> Dict[str, object]:
        if not FITZ_AVAILABLE:
            return {'status': 'ocr_pending', 'text': '', 'metadata': {'parser': 'fitz-unavailable'}}
        try:
            document = fitz.open(str(path))
            parts: List[str] = []
            total_pages = len(document)
            for index, page in enumerate(document[:40], start=1):
                try:
                    text = page.get_text('text') or ''
                except Exception:
                    text = ''
                if text.strip():
                    parts.append(f'--- Page {index} ---\n{text.strip()}')
            joined = '\n'.join(parts)
            return {
                'status': 'text_extracted' if joined.strip() else 'ocr_pending',
                'text': joined,
                'metadata': {'parser': 'fitz-text', 'pages_sampled': min(total_pages, 40)},
            }
        except Exception as exc:
            return {'status': 'pdf_error', 'text': '', 'metadata': {'error': str(exc), 'parser': 'fitz-text'}}

    def _ocr_pdf_with_fitz(self, path: Path) -> Dict[str, object]:
        try:
            document = fitz.open(str(path))
            snippets: List[str] = []
            for index, page in enumerate(document[:3], start=1):
                pix = page.get_pixmap(dpi=180)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                snippets.append(pytesseract.image_to_string(image, lang=self.language))
            text = '\n'.join(part.strip() for part in snippets if part.strip())
            return {
                'status': 'ocr_extracted' if text else 'ocr_pending',
                'text': text,
                'metadata': {'parser': 'fitz+tesseract', 'pages_sampled': min(len(document), 3)},
            }
        except Exception as exc:
            return {'status': 'ocr_error', 'text': '', 'metadata': {'error': str(exc)}}

    def _inspect_image(self, path: Path) -> Dict[str, object]:
        if self._can_run_ocr() and Image is not None:
            try:
                text = pytesseract.image_to_string(Image.open(path), lang=self.language).strip()
                return {
                    'status': 'ocr_extracted' if text else 'ocr_empty',
                    'text': text,
                    'metadata': {'parser': 'tesseract-image'},
                }
            except Exception as exc:
                return {'status': 'ocr_error', 'text': '', 'metadata': {'error': str(exc)}}
        return {'status': 'ocr_pending', 'text': '', 'metadata': {'parser': 'image-metadata-only'}}

    def _can_run_ocr(self) -> bool:
        return bool(TESSERACT_PYTHON_AVAILABLE and self.tesseract_cmd and FITZ_AVAILABLE and Image is not None)
