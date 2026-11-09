"""Read only raw PicoLog records from a large TESTS_NO_PCM folder.

- Recurses safely and ignores outputs under Results/PHP_Results.
- Archives inside a directory are ignored to prevent duplicate experiments.
- ZIP archives are supported only when explicitly selected.
- Auxiliary CSV (drut, calibration, exported results) are skipped by header.
"""
from __future__ import annotations

import hashlib
import os
import re
import zipfile
from pathlib import Path

CHANNELS=(1,3,4,5,6,7)
IGNORE_DIRS={'results','php_results','__macosx','_internal','3dphpanalyzer_wersje'}


def is_raw_picolog(data):
    text=data[:2500].decode('utf-8-sig',errors='replace').lower()
    return all(re.search(r'(?:kana[łl]|channel)\s*'+str(ch)+r'\b',text)
               for ch in CHANNELS)


def input_files(path):
    path=Path(path)
    result=[]
    if path.is_dir():
        for base, folders, files in os.walk(path,followlinks=False):
            folders[:]=sorted(d for d in folders
                if d.lower() not in IGNORE_DIRS and not d.startswith('.')
                and not (Path(base)/d).is_symlink())
            for name in sorted(files):
                f=Path(base)/name
                if f.suffix.lower()!='.csv' or f.is_symlink():
                    continue
                with f.open('rb') as stream:
                    head=stream.read(2500)
                if not is_raw_picolog(head):
                    continue
                result.append((f.name,str(f.resolve()),f.read_bytes()))
    elif path.suffix.lower()=='.csv':
        data=path.read_bytes()
        if is_raw_picolog(data):
            result.append((path.name,str(path.resolve()),data))
    elif path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith('.csv'):
                    continue
                if any(part.lower() in IGNORE_DIRS
                       for part in Path(member.filename).parts):
                    continue
                data=archive.read(member)
                if is_raw_picolog(data):
                    result.append((Path(member.filename).name,
                                   str(path.resolve())+' / '+member.filename,data))
    return result


def deduplicate_files(items):
    """Exact SHA256 only: prefix-related CSVs remain marked, not silently discarded."""
    seen={}
    distinct=[]
    duplicates=[]
    for name,origin,data in items:
        digest=hashlib.sha256(data).hexdigest()
        if digest in seen:
            duplicates.append((origin,seen[digest]))
        else:
            seen[digest]=origin
            distinct.append((name,origin,data))
    return distinct,duplicates
