"""Local, atomic autosave for operator-entered experiment assumptions.

Files are stored only on the local computer, under ~/3DPHPAnalyzer/Sessions.
Identified by SHA-256 of the measured sample array; never overwrites CSV.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from session_config import export_configuration, record_identity, validated_import
from timeline_editor import resolve_schedule


def session_path(record, *, base_dir=None):
    identity = record_identity(record)
    safe=''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in record.name)
    root = Path(base_dir) if base_dir is not None else Path.home()/'3DPHPAnalyzer'/'Sessions'
    return root / (safe[:80]+'_'+identity['values_sha256'][:16]+'.json')


def save_session(row, *, base_dir=None):
    """Atomic save, keeping the previous valid session on interruption."""
    target=session_path(row['record'],base_dir=base_dir)
    target.parent.mkdir(parents=True,exist_ok=True)
    content=export_configuration(row)
    temp_path=None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=target.parent, prefix='.session_',suffix='.tmp',
                                         delete=False) as out:
            temp_path=Path(out.name)
            json.dump(content,out,ensure_ascii=False,indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path,target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return target


def restore_session(row, *, base_dir=None):
    target=session_path(row['record'],base_dir=base_dir)
    if not target.exists():
        return False
    with target.open('r',encoding='utf-8') as f:
        content=json.load(f)
    try:
        restored=validated_import(content,row)
    except ValueError as error:
        # Editing ON/OFF markers can invalidate a previously selected R_ref.
        # Recover Q and all manual edits rather than discard the entire
        # autosaved experiment. An explicit JSON import stays strictly validated.
        if (content.get('reference_enabled') is not True
                or 'Nie można przywrócić Rref:' not in str(error)):
            raise
        content=dict(content,reference_enabled=False)
        restored=validated_import(content,row)
        row['session_restore_note'] = (
            'Poprzednia referencja R/Rref przestała obowiązywać po zmianie Q; '
            'przywrócono wszystkie znaczniki i wyłączono referencję.')
    row.update(restored)
    return True
