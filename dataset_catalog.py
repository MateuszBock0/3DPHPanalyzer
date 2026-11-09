"""Safe large-folder import for PicoLog CSV / archives.

Keep original TESTS_NO_PCM untouched. Results, old exports, unrelated
calibration sheets, notebook CSVs and executables must not become tests.
"""
from __future__ import annotations
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

SKIP_DIRS={'results','php_results','3dphpanalyzer_wersje','_internal',
           '.git','__pycache__','.venv','venv'}
REQUIRED_CHANNELS=frozenset((1,3,4,5,6,7))
MAX_CSV_BYTES=100*1024*1024


def picolog_header(data):
    if not data:
        return False
    first=data[:10000].decode('utf-8-sig',errors='replace').splitlines()
    if not first:
        return False
    header=first[0]
    delim=';' if header.count(';')>header.count(',') else ','
    fields=next(csv.reader(io.StringIO(header),delimiter=delim),[])
    channels=set()
    for field in fields:
        found=re.search(r'(?:kana[łl]|channel)\s*(\d+)\b',field,re.I)
        if found:
            channels.add(int(found.group(1)))
    return REQUIRED_CHANNELS.issubset(channels)


def _excluded(parts):
    return any(part.casefold() in SKIP_DIRS for part in parts)


def input_files(path):
    """Return only source measurement CSVs. Nested ZIPs are read, never edited.

    Identical file content from a ZIP and a local export is deduplicated.
    Truncated prefix exports are separately recognised by unique_records().
    """
    path=Path(path)
    # Prefer loose source CSV over an identical copy embedded in an archive.
    files=sorted((p for p in path.rglob('*') if p.is_file()
                  and not _excluded(p.relative_to(path).parts)),
                 key=lambda p:(p.suffix.lower()=='.zip',str(p).casefold())) if path.is_dir() else [path]
    rows=[]
    digests=set()
    for file in files:
        if file.suffix.lower()=='.csv':
            if file.stat().st_size>MAX_CSV_BYTES:
                continue
            with file.open('rb') as stream:
                data=stream.read()
            if not picolog_header(data):
                continue
            origin=str(file.resolve())
            name=file.name
            datasets=[(name,origin,data)]
        elif file.suffix.lower()=='.zip':
            datasets=[]
            try:
                with zipfile.ZipFile(file) as z:
                    for entry in z.infolist():
                        if (entry.is_dir() or not entry.filename.lower().endswith('.csv')
                            or entry.file_size>MAX_CSV_BYTES
                            or _excluded(Path(entry.filename.replace('\\','/')).parts)):
                            continue
                        with z.open(entry) as stream:
                            data=stream.read()
                        if not picolog_header(data):
                            continue
                        name=Path(entry.filename.replace('\\','/')).name
                        datasets.append((name,f'{file.resolve()} / {entry.filename}',data))
            except (zipfile.BadZipFile,OSError):
                # A corrupt archive is not a reason to discard other CSV files.
                continue
        else:
            continue
        for name,origin,data in datasets:
            digest=hashlib.sha256(data).digest()
            if digest in digests:
                continue
            digests.add(digest)
            rows.append((name,origin,data))
    return rows
