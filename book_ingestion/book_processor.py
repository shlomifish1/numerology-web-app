"""Corpus scanner and catalog generator for research books."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .knowledge_store import KnowledgeStore
from .ocr_engine import OCREngine


class BookProcessor:
    def __init__(self, store: Optional[KnowledgeStore] = None, engine: Optional[OCREngine] = None):
        self.store = store or KnowledgeStore()
        self.engine = engine or OCREngine()

    def add_book(
        self,
        title: str,
        author: str,
        source_path: str,
        corpus: str,
        method: Optional[str] = None,
    ) -> Dict[str, object]:
        inspection = self.engine.inspect(source_path)
        text = inspection.get('text', '') or ''
        metadata = dict(inspection.get('metadata', {}))
        metadata['method'] = method
        source = Path(source_path)
        book_title = self._derive_title(source, title, metadata, text)
        metadata['derived_title'] = book_title
        outline = self._extract_outline(title=book_title, text=text)
        metadata['outline'] = outline
        record = {
            'corpus': corpus,
            'title': book_title,
            'author': author,
            'source_path': str(source),
            'extension': source.suffix.lower(),
            'language_hint': self._language_hint(book_title),
            'status': inspection.get('status', 'metadata_only'),
            'text_length': len(text),
            'excerpt': text[:500] if text else '',
            'metadata_json': json.dumps(metadata, ensure_ascii=False),
        }
        book_id = self.store.upsert_book(record)
        if text:
            self.store.replace_chunks(book_id, self._chunk_text(text))
        self.store.save_book_artifact(
            book_id,
            artifact_type='raw_extracted',
            content_text=text[:12000] if text else '',
            content_json=metadata,
        )
        outline_text = self._format_outline(title=book_title, outline=outline)
        if outline_text:
            self.store.save_book_artifact(
                book_id,
                artifact_type='book_outline',
                content_text=outline_text,
                content_json=outline,
            )
        return {'book_id': book_id, 'record': record, 'metadata': metadata}

    def index_corpus(self, corpus: str, folder_path: str, method: Optional[str] = None) -> List[Dict[str, object]]:
        folder = Path(folder_path)
        results = []
        valid_sources: List[str] = []
        if folder.is_file():
            source_paths = [folder]
        else:
            source_paths = [path for path in sorted(folder.rglob('*')) if path.is_file() and not self._should_skip(path)]
        total = len(source_paths)
        self.store.set_learning_status(
            corpus,
            'running',
            progress=f'0%|Indexing {folder.name} (0/{total or 1})',
        )
        encountered_error = False
        for index, path in enumerate(source_paths, start=1):
            try:
                result = self.add_book(
                    title=path.stem,
                    author='',
                    source_path=str(path),
                    corpus=corpus,
                    method=method,
                )
                valid_sources.append(str(path))
                results.append(result)
                pct = int((index / max(total, 1)) * 100)
                self.store.set_learning_status(
                    corpus,
                    'running',
                    progress=f'{pct}%|Indexing {index}/{max(total, 1)}: {path.name}',
                )
            except Exception as exc:
                encountered_error = True
                results.append({
                    'error': str(exc),
                    'source_path': str(path),
                    'title': path.stem,
                })
                pct = int((index / max(total, 1)) * 100)
                self.store.set_learning_status(
                    corpus,
                    'running',
                    progress=f'{pct}%|Indexing {index}/{max(total, 1)}: {path.name} failed',
                    )
        self.store.sync_corpus_sources(corpus, valid_sources)
        self.store.purge_generated_records(corpus)
        if encountered_error:
            self.store.set_learning_status(
                corpus,
                'error',
                error='One or more files failed during indexing',
                progress=f'100%|Indexed {len(valid_sources)} files with errors',
            )
        else:
            self.store.set_learning_status(corpus, 'done', progress=f'100%|Indexed {len(valid_sources)} files')
        return results

    def export_markdown_catalog(self, corpus: str, output_path: str) -> str:
        books = self.store.list_books(corpus=corpus)
        lines = [f'# {corpus.title()} Catalog', '', f'סה"כ ספרים/קבצים: {len(books)}', '']
        for book in books:
            lines.append(f"## {book['title']}")
            lines.append(f"- סטטוס: {book['status']}")
            lines.append(f"- סוג קובץ: {book['extension'] or '-'}")
            lines.append(f"- שפה משוערת: {book['language_hint'] or '-'}")
            lines.append(f"- אורך טקסט: {book['text_length']}")
            lines.append(f"- נתיב: {book['source_path']}")
            if book.get('excerpt'):
                excerpt = str(book['excerpt']).replace('\n', ' ').strip()
                lines.append(f"- excerpt: {excerpt[:220]}")
            lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content

    def _chunk_text(self, text: str, chunk_size: int = 1800) -> Iterable[str]:
        clean = ' '.join(text.split())
        if not clean:
            return []
        return [clean[i:i + chunk_size] for i in range(0, len(clean), chunk_size)]

    def _language_hint(self, title: str) -> str:
        has_hebrew = any('\u0590' <= ch <= '\u05FF' for ch in title)
        has_latin = any(('A' <= ch <= 'Z') or ('a' <= ch <= 'z') for ch in title)
        if has_hebrew and has_latin:
            return 'HE+EN'
        if has_hebrew:
            return 'HE'
        if has_latin:
            return 'EN'
        return 'unknown'

    def _derive_title(self, source_path: Path, title: str, metadata: Dict[str, object], text: str) -> str:
        candidates: List[str] = []

        def add_candidate(value: object) -> None:
            if not isinstance(value, str):
                return
            candidate = re.sub(r'\s+', ' ', value).strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        add_candidate(metadata.get('title'))
        add_candidate(metadata.get('book_title'))
        add_candidate(metadata.get('name'))

        if source_path.suffix.lower() == '.json' and text:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                add_candidate(parsed.get('title'))
                add_candidate(parsed.get('book_title'))
                add_candidate(parsed.get('name'))
                add_candidate(parsed.get('book_id'))

        add_candidate(self._folder_title_from_source_path(source_path))
        add_candidate(source_path.parent.name)
        add_candidate(title)
        add_candidate(source_path.stem)

        if not candidates:
            return title or source_path.stem or source_path.name

        return max(candidates, key=lambda candidate: self._title_score(candidate, source_path))

    def _folder_title_from_source_path(self, source_path: Path) -> Optional[str]:
        current = source_path.parent
        while current and current.parent != current:
            name = current.name.strip()
            if name and not self._is_generic_folder_name(name):
                return name
            current = current.parent
        return None

    def _is_generic_folder_name(self, name: str) -> bool:
        normalized = re.sub(r'\s+', ' ', str(name or '')).strip().lower()
        if not normalized:
            return True
        generic_terms = {
            'chapter',
            'chapters',
            'part',
            'pages',
            'page',
            'ocr',
            'scan',
            'pdf',
            'txt',
            'חלק',
            'פרק',
            'עמוד',
            'עמודים',
        }
        if normalized in generic_terms:
            return True
        if re.fullmatch(r'^[\d\s\-–—_]+$', normalized):
            return True
        return False

    def _title_score(self, candidate: str, source_path: Path) -> int:
        text = re.sub(r'\s+', ' ', str(candidate or '')).strip()
        if not text:
            return -100
        lower = text.lower()
        hebrew = sum(1 for ch in text if '\u0590' <= ch <= '\u05FF')
        latin = sum(1 for ch in text if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))
        digits = sum(1 for ch in text if ch.isdigit())
        words = len(text.split())
        score = hebrew * 4 + words * 2 - latin * 2 - digits * 2
        if len(text) <= 4:
            score -= 10
        if len(text) > 80:
            score -= 8
        if any(token in lower for token in ('final_schema', 'strict_schema', 'normalized', 'json', 'pdf', 'scan')):
            score -= 15
        if source_path.parent.name and text == source_path.parent.name:
            score += 6
        if text == source_path.stem:
            score -= 2
        if any(token in text for token in ('ספר', 'נומרולוג', 'אסטרולוג')):
            score += 8
        return score

    def _should_skip(self, path: Path) -> bool:
        name = path.name.lower()
        return name.endswith('_books.md') or name.endswith('_category_map.md') or name.endswith('_ocr_queue.md') or name.endswith('_runtime.md') or name.endswith('_seed_plan.md') or name.endswith('_taxonomy.md') or name.endswith('_intake.md')

    def _extract_outline(self, title: str, text: str) -> Dict[str, object]:
        cleaned_text = re.sub(r'\r\n?', '\n', str(text or ''))
        lines = [re.sub(r'\s+', ' ', line).strip() for line in cleaned_text.split('\n')]
        headings: List[str] = []
        for line in lines:
            if not line:
                continue
            candidate = line.strip('•*-—–# \t:').strip()
            if not candidate or len(candidate) > 120:
                continue
            alpha_count = sum(1 for ch in candidate if ch.isalpha())
            token_count = len(candidate.split())
            if not (
                candidate.endswith(':')
                or candidate[:1].isdigit()
                or candidate.lower().startswith(('chapter', 'topic', 'subject', 'section', 'פרק', 'נושא'))
                or (alpha_count >= 4 and token_count <= 12 and len(candidate) <= 80)
            ):
                continue
            if candidate not in headings:
                headings.append(candidate)
            if len(headings) >= 12:
                break

        raw_tokens = re.findall(r'[\w\u0590-\u05FF]+', f"{title} {' '.join(headings)} {cleaned_text[:4000]}".lower())
        stopwords = {
            'and', 'or', 'the', 'a', 'an', 'of', 'to', 'in', 'for', 'with', 'by',
            'and', 'the', 'this', 'that', 'from', 'into', 'על', 'של', 'את', 'עם',
            'הוא', 'היא', 'זה', 'זו', 'זהו', 'הספר', 'ספר', 'פרק', 'נושא', 'תוכן',
        }
        keywords: List[str] = []
        for token in raw_tokens:
            token = token.strip()
            if len(token) < 3 or token in stopwords:
                continue
            if token not in keywords:
                keywords.append(token)
            if len(keywords) >= 20:
                break

        topic_candidates = headings[:5] if headings else keywords[:5]
        summary_bits = [bit for bit in [title.strip(), headings[0] if headings else '', headings[1] if len(headings) > 1 else ''] if bit]
        return {
            'title': title,
            'headings': headings,
            'keywords': keywords,
            'topic_candidates': topic_candidates,
            'summary': ' | '.join(summary_bits),
        }

    def _format_outline(self, title: str, outline: Dict[str, object]) -> str:
        parts = [f"title: {title}"]
        summary = str(outline.get('summary') or '').strip()
        if summary:
            parts.append(f"summary: {summary}")
        headings = [str(item).strip() for item in list(outline.get('headings') or [])[:8] if str(item).strip()]
        if headings:
            parts.append("headings: " + " | ".join(headings))
        keywords = [str(item).strip() for item in list(outline.get('keywords') or [])[:12] if str(item).strip()]
        if keywords:
            parts.append("keywords: " + " | ".join(keywords))
        topics = [str(item).strip() for item in list(outline.get('topic_candidates') or [])[:6] if str(item).strip()]
        if topics:
            parts.append("topics: " + " | ".join(topics))
        return "\n".join(parts).strip()



