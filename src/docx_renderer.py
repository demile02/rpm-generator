#!/usr/bin/env python3
"""Renderer DOCX final RPM Pembelajaran Mendalam.

Kontrak (AGENTS.md §12/§32): renderer HANYA menerima hasil FINAL
VALIDATED (``result["status"] == "success"`` dan
``result["validation"]["final"]["passed"] is True``). Selain itu
-> ExportError, tanpa bypass apa pun (tanpa force/skip/fallback).

Single source of truth (AGENTS.md §43):
FINAL VALIDATED RPM RESULT ├──> WEB RENDERER └──> DOCX RENDERER.
Renderer murni representasi: tidak memanggil AI, tidak meregenerasi,
tidak enrich/paraphrase/infer/default, tidak mengubah
CP/TP/level/provenance/validation, tidak menambah konten DOCX-only.

Layout memakai ``templates/Templatku.docx`` sebagai master package (A4,
margin 2,5 cm, style Normal 1,5, font Bookman Old Style, Word numbering,
cell alignment, table styles, borders, shading, dan numbering dipertahankan).
Renderer hanya mengosongkan sample body lalu mengisi content final; layout
bukan dibangun ulang dari ``Document()``.
Urutan: A. IDENTITAS MODUL → B → C → D (Pertemuan → Pembuka → Inti →
Penutup → blok prinsip standalone per pertemuan) → E.

Parity Web (Batch 1): judul, topik, field identitas, B–E, TP/KKTP,
meeting/aktivitas, prinsip per pertemuan, asesmen — sama dengan
Web Preview untuk result yang sama. Glosarium dipertahankan karena
bagian dari final result (ditampilkan Web).
"""

from copy import deepcopy
from pathlib import Path
import re

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

# Geometri Templatku.docx: A4, margin 2,5 cm, banner #E2EFD9.
PAGE_W_CM = 21.0
PAGE_H_CM = 29.7
MARGIN_CM = 2.5
USABLE_CM = PAGE_W_CM - 2 * MARGIN_CM
FONT = 'Bookman Old Style'
BANNER_FILL = 'E2EFD9'
# Border template per section (tblBorders Templatku.docx):
# A hitam (auto), B/C/D biru 365F91, E abu BFBFBF; single sz 4.
BORDER_AUTO = 'auto'
BORDER_SECT = '365F91'
BORDER_ASESMEN = 'BFBFBF'
INK = '000000'
MUTED = '595959'

# Proporsi kolom template (gridCol Templatku.docx).
# E: grid 4 kolom Instrumen|Tipe|TP|KKTP; diagnostik memakai 3 kolom
# pertama dengan 2 terakhir merged (Jawaban Benar).
TP_FRACS = [0.109, 0.782, 0.109]
ACTIVITY_FRACS = [0.187, 0.422, 0.109, 0.094, 0.188]
ASSESS_FRACS = [0.6561, 0.1251, 0.0937, 0.1251]
GLOS_FRACS = [0.25, 0.75]

BODY_SIZE = Pt(11)
SMALL_SIZE = Pt(9)
TITLE_SIZE = Pt(11)
TOPIC_SIZE = Pt(11)
BANNER_SIZE = BODY_SIZE
SUB_SIZE = Pt(11)


class ExportError(Exception):
    """Export ditolak: input bukan FINAL VALIDATED RPM."""


def assert_final_validated(result) -> dict:
    """Kembalikan dict module bila result FINAL VALIDATED.

    Raise ExportError untuk: bukan dict, status != success, final
    validation tidak PASS, atau module/master_outline hilang.
    """
    if not isinstance(result, dict):
        raise ExportError("Export ditolak: hasil bukan dict result pipeline.")
    if result.get('status') != 'success':
        raise ExportError(
            "Export ditolak: status=%r (final validation tidak lulus atau "
            "draft belum tervalidasi)." % (result.get('status'),))
    validation = result.get('validation') or {}
    final = validation.get('final') or {}
    if final.get('passed') is not True:
        raise ExportError(
            "Export ditolak: final validation != PASS "
            "(errors=%r)." % (final.get('errors'),))
    module = result.get('module')
    if not isinstance(module, dict) or not isinstance(
            module.get('master_outline'), dict):
        raise ExportError(
            "Export ditolak: module/master_outline final tidak tersedia.")
    return module


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Ya' if value else 'Tidak'
    return str(value).strip()


def _continuous_text(value) -> str:
    """Render long text without source line breaks becoming Word breaks."""
    text = _text(value).replace(chr(13) + chr(10), chr(10))
    text = text.replace(chr(13), chr(10))
    lines = text.split(chr(10))
    compact = []
    for line in lines:
        line = line.strip()
        if compact and compact[-1].endswith('-'):
            compact[-1] += line
        elif line:
            compact.append(line)
    return ' '.join(compact)


# ------------------------------------------------------------------
# Display mapping presentasi (data final tidak diubah; hanya cara
# tampil mengikuti Templatku.docx).
# ------------------------------------------------------------------

def _display_grade(code) -> str:
    """Kode 'MA_10' -> '10' (presentation-friendly, template §2)."""
    code = _text(code)
    if '_' in code:
        tail = code.split('_', 1)[1].strip()
        if tail:
            return tail.replace('_', ' ')
    return code


def _display_semester(value) -> str:
    """1 -> 'Ganjil', 2 -> 'Genap'; selain itu tampil apa adanya."""
    text = _text(value)
    if text == '1':
        return 'Ganjil'
    if text == '2':
        return 'Genap'
    return text


_TYPE_LABELS = {
    'multiple_choice': 'Pilihan Ganda',
    'short_answer': 'Isian',
    'essay': 'Uraian',
    'true_false': 'Benar/Salah',
    'matching': 'Menjodohkan',
    'performance_task': 'Unjuk Kerja',
    'performance_assessment': 'Unjuk Kerja',
    'performance': 'Unjuk Kerja',
    'oral_reading': 'Membaca Nyaring',
}


def _display_type(value) -> str:
    """Enum tipe -> Bahasa Indonesia (template §8)."""
    text = _text(value)
    return _TYPE_LABELS.get(text, text)


def _answer_label(item: dict, options) -> str:
    """Label A/B/C/D untuk kolom Jawaban Benar diagnostik (Batch 4.1).

    Presentation-only: 'D' -> 'D'; 'D. teks...' -> 'D';
    teks lengkap -> label opsi yang cocok; tak cocok -> nilai mentah
    apa adanya (jujur, tanpa karangan).
    """
    if not isinstance(item, dict):
        return ''
    raw = ''
    for key in ('correct_answer', 'answer_key', 'answer'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break
        if isinstance(value, list) and value:
            raw = _text(value[0])
            break
    if not raw:
        return ''
    labels = [o['label'] for o in (options or [])
              if isinstance(o, dict) and o.get('label')]
    if len(raw) == 1 and raw.upper() in labels:
        return raw.upper()
    first = raw.split('.', 1)[0].strip().upper()
    if len(first) == 1 and first in labels:
        return first
    for opt in options or []:
        if isinstance(opt, dict) and opt.get('text', '').strip().lower() \
                == raw.lower():
            return opt['label']
    return raw


def _inline_mc_options(question: str):
    """Ambil opsi yang sudah tertanam pada question hasil impor lama."""
    text = _text(question)
    matches = list(re.finditer(r'(?<!\w)([A-D])\.\s*', text))
    start = next((i for i, match in enumerate(matches)
                  if match.group(1).upper() == 'A'), None)
    if start is None:
        return '', []
    selected = []
    expected = 'A'
    for match in matches[start:]:
        if match.group(1).upper() != expected:
            continue
        selected.append(match)
        expected = chr(ord(expected) + 1)
        if expected > 'D':
            break
    if len(selected) < 2:
        return text, []
    options = []
    for index, match in enumerate(selected):
        begin = match.end()
        end = (selected[index + 1].start()
               if index + 1 < len(selected) else len(text))
        options.append({'label': match.group(1).upper(),
                        'text': _text(text[begin:end])})
    return _text(text[:selected[0].start()]), options


def _mc_question(item: dict) -> str:
    """Question diagnostik tanpa opsi inline yang akan dirender terpisah."""
    question = _text(item.get('question')) if isinstance(item, dict) else ''
    stem, inline = _inline_mc_options(question)
    return stem if len(inline) >= 2 else _text(question)


def _mc_options(item: dict):
    """Opsi Pilihan Ganda ternormalisasi [{label, text}]."""
    question = item.get('question') if isinstance(item, dict) else ''
    _stem, inline = _inline_mc_options(question)
    if len(inline) >= 2:
        return inline
    options = item.get('options') if isinstance(item, dict) else None
    if not isinstance(options, list):
        return []
    out = []
    seen = set()
    for i, opt in enumerate(options):
        if isinstance(opt, dict):
            label = (_text(opt.get('label')) or chr(ord('A') + i)).upper()
            text = _text(opt.get('text', opt.get('option', '')))
        else:
            label, text = chr(ord('A') + i), _text(opt)
        if text and label not in seen:
            out.append({'label': label, 'text': text})
            seen.add(label)
    return out


# ------------------------------------------------------------------
# Primitif template (Oxml + paragraf).
# ------------------------------------------------------------------

def _run(paragraph, text: str, bold: bool = False, size=BODY_SIZE,
         italic: bool = False, color_hex: str = INK):
    """Add content without overriding template character inheritance."""
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    return run


def _para(doc_or_cell, text: str, bold: bool = False, size=BODY_SIZE,
          italic: bool = False, align=None, space_after=None,
          color_hex: str = INK, style=None):
    if hasattr(doc_or_cell, 'sections'):
        paragraph = doc_or_cell.add_paragraph()
    else:
        paras = doc_or_cell.paragraphs
        if len(paras) == 1 and not paras[0].text:
            paragraph = paras[0]
        else:
            paragraph = doc_or_cell.add_paragraph()
    if style is not None:
        paragraph.style = style
    # Templatku.docx carries 1.5 spacing through Normal/List Paragraph.
    # Keep direct paragraph spacing unset unless caller explicitly needs it;
    # this lets the template style remain the source of truth.
    paragraph.paragraph_format.space_before = None
    # Cell paragraphs inherit Normal/List Paragraph spacing from template;
    # renderer must not inject the former 2pt direct spacing.
    paragraph.paragraph_format.space_after = (
        space_after if hasattr(doc_or_cell, 'sections') else None)
    if align is not None:
        paragraph.alignment = align
    if text:
        _run(paragraph, text, bold=bold, size=size, italic=italic,
             color_hex=color_hex)
    return paragraph


def _set_num(paragraph, num_id: int, ilvl: int = 0) -> None:
    """Apply Word numbering metadata; never bake the number into layout."""
    p_pr = paragraph._p.get_or_add_pPr()
    old = p_pr.find(qn('w:numPr'))
    if old is not None:
        p_pr.remove(old)
    num_pr = OxmlElement('w:numPr')
    level = OxmlElement('w:ilvl')
    level.set(qn('w:val'), str(ilvl))
    number = OxmlElement('w:numId')
    number.set(qn('w:val'), str(num_id))
    num_pr.append(level)
    num_pr.append(number)
    p_pr.append(num_pr)


def _numbered_text(paragraph, prefix: str, text: str, *, num_id: int,
                   ilvl: int = 0, bold: bool = False,
                   size=BODY_SIZE, style='List Paragraph'):
    """Write text with Word numbering; ``prefix`` is never rendered.

    Callers retain ``prefix`` for API compatibility, but visible labels must
    come from ``numPr``. A hidden/manual prefix still appears in
    ``Paragraph.text`` and causes duplicate labels in exported documents.
    """
    del prefix, size
    paragraph.style = style
    paragraph.clear()
    _run(paragraph, text, bold=bold)
    _set_num(paragraph, num_id, ilvl)
    return paragraph


def _shade_cell(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tc_pr.append(shd)


def _set_table_borders(table, size: str = '4',
                       color: str = BORDER_AUTO) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        element = OxmlElement(f'w:{edge}')
        element.set(qn('w:val'), 'single')
        element.set(qn('w:sz'), size)
        element.set(qn('w:space'), '0')
        element.set(qn('w:color'), color)
        borders.append(element)
    tbl_pr.append(borders)


def _dxa(cm_value: float) -> int:
    return int(round(cm_value * 567.0))  # 1 cm = 567 dxa


def _set_tc_width(tc, width_dxa: int) -> None:
    tc_pr = tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn('w:tcW')):
        tc_pr.remove(old)
    tc_w = OxmlElement('w:tcW')
    tc_w.set(qn('w:w'), str(width_dxa))
    tc_w.set(qn('w:type'), 'dxa')
    tc_pr.append(tc_w)


def _fix_layout(table, fractions) -> None:
    """Kunci layout fixed + lebar kolom proporsional template.

    Templatku menyimpan vertical alignment hanya pada sel-sel yang memang
    pendek/terstruktur. Jangan mengisi sel lain dengan TOP secara paksa:
    default itu menjadi sumber beda visual dari template.
    """
    table.autofit = False
    try:
        table.allow_autofit = False
    except AttributeError:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    usable = _dxa(USABLE_CM)
    widths = [int(round(usable * f)) for f in fractions]
    widths[-1] += usable - sum(widths)
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn('w:tblW'))
    if tbl_w is None:
        tbl_w = OxmlElement('w:tblW')
        tbl_pr.append(tbl_w)
    tbl_w.set(qn('w:w'), str(usable))
    tbl_w.set(qn('w:type'), 'dxa')
    layout = tbl_pr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        tbl_pr.append(layout)
    layout.set(qn('w:type'), 'fixed')
    grid = tbl.find(qn('w:tblGrid'))
    if grid is None:
        grid = OxmlElement('w:tblGrid')
        tbl.append(grid)
    for old in grid.findall(qn('w:gridCol')):
        grid.remove(old)
    for width in widths:
        column = OxmlElement('w:gridCol')
        column.set(qn('w:w'), str(width))
        grid.append(column)
    for row in table.rows:
        cursor = 0
        for tc in row._tr.findall(qn('w:tc')):
            tc_pr = tc.get_or_add_tcPr()
            span_el = tc_pr.find(qn('w:gridSpan'))
            merged_away = (tc_pr.find(qn('w:hMerge')) is not None
                           and span_el is None)
            if merged_away:
                if cursor < len(widths):
                    _set_tc_width(tc, widths[cursor])
                cursor += 1
                continue
            span = int(span_el.get(qn('w:val'))) if span_el is not None else 1
            _set_tc_width(tc, sum(widths[cursor:cursor + span]))
            cursor += span


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement('w:tblHeader'))


def _center_cell(cell, vertical: bool = True) -> None:
    """Rata tengah isi sel; vertical center mengikuti template."""
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    if vertical:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _justify_cell(cell, vertical: bool = False) -> None:
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
    if vertical:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _section_banner(table, label: str, prefix: str, num_id: int) -> None:
    """Render section label with Word numbering, not literal label text."""
    label = re.sub(r'^[A-E]\.\s*', '', _text(label))
    ncols = len(table.columns)
    row = table.add_row()
    row.cells[0].merge(row.cells[ncols - 1])
    cell = row.cells[0]
    _shade_cell(cell, BANNER_FILL)
    # Keep template paragraph roles, but use one numbering definition for all
    # A-E banners. Indent must come from numPr/abstractNum, not direct text
    # formatting; direct w:ind caused uneven section starts.
    heading_style = 'List Paragraph' if prefix.startswith('A.') else 'Heading 1'
    paragraph = _para(cell, '', bold=True, size=BANNER_SIZE,
                      space_after=Pt(2), style=heading_style)
    _numbered_text(paragraph, '', label, num_id=num_id,
                   bold=True, size=BANNER_SIZE, style=heading_style)
    # Keep template's direct banner indent identical for every A-E header;
    # the letter itself still comes only from the shared numId=4 definition.
    p_pr = paragraph._p.get_or_add_pPr()
    direct_indent = p_pr.find(qn('w:ind'))
    if direct_indent is None:
        direct_indent = OxmlElement('w:ind')
        p_pr.append(direct_indent)
    direct_indent.set(qn('w:left'), '360')
    direct_indent.attrib.pop(qn('w:hanging'), None)
    direct_indent.attrib.pop(qn('w:firstLine'), None)


def _set_section_heading(table, label: str, prefix: str, num_id: int) -> None:
    # Compatibility alias for callers/tests that inspect banner construction.
    _section_banner(table, label, prefix, num_id)


def _new_table(doc, ncols, style_id=None):
    table = doc.add_table(rows=0, cols=ncols)
    # Template table styles carry subtle table defaults/looks in addition to
    # explicit borders. Select matching custom styles by shape/order.
    if style_id is None:
        style_id = {1: 'a', 3: 'a2', 4: 'a4', 5: 'a3'}.get(ncols)
    if style_id:
        try:
            table.style = style_id
        except KeyError:
            table.style = None
    return table


def _clear_template_body(doc) -> None:
    """Remove sample content while retaining template styles/numbering."""
    body = doc._body._body
    for child in list(body):
        if child.tag != qn('w:sectPr'):
            body.remove(child)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / 'templates' / 'Templatku.docx'


def _render_principles(doc, meeting: dict) -> None:
    """Render principle block as body paragraphs, outside activity tables."""
    principles = meeting.get('principles') or {}
    items = []
    for label, key in (
            ('Berkesadaran (Mindful Learning)', 'berkesadaran'),
            ('Bermakna (Meaningful Learning)', 'bermakna'),
            ('Menggembirakan (Joyful Learning)', 'menggembirakan')):
        value = _text(principles.get(key)) if isinstance(principles, dict) else ''
        if value:
            items.append((label, value))
    if not items:
        return
    _para(doc, 'Prinsip Pembelajaran Mendalam', bold=True,
          size=SUB_SIZE, space_after=None)
    principle_num_id = _new_numbering_instance(doc, 1)
    for label, value in items:
        paragraph = _para(doc, '', size=BODY_SIZE,
                          space_after=None, style='List Paragraph')
        _numbered_text(paragraph, '', label,
                       num_id=principle_num_id, ilvl=3,
                       size=BODY_SIZE, style='List Paragraph')
        # Template keeps English parenthetical label italic, without a
        # literal list number in the paragraph text.
        match = re.match(r'^(.*?)(\s+\([^)]*\))$', label)
        if match:
            paragraph.clear()
            _run(paragraph, match.group(1))
            _run(paragraph, match.group(2), italic=True)
            _set_num(paragraph, principle_num_id, 3)
        # Match template principle-list geometry. The template deliberately
        # uses a small direct left indent on these body paragraphs, while the
        # section banners take indent from the shared abstract numbering.
        p_pr = paragraph._p.get_or_add_pPr()
        old_indent = p_pr.find(qn('w:ind'))
        if old_indent is not None:
            p_pr.remove(old_indent)
        indent = OxmlElement('w:ind')
        indent.set(qn('w:left'), '360')
        p_pr.append(indent)
        # Penjelasan mengikuti margin normal; hanya nama prinsip yang
        # memakai indent daftar dari template.
        _para(doc, value, size=BODY_SIZE,
              space_after=None, style='Normal')


def _banner_row(table, text: str) -> None:
    """Baris banner merged + shade dengan numbering Word template."""
    match = re.match(r'^([A-E])\.\s*(.+)$', _text(text))
    if match:
        # One Word numbering instance keeps A-E on identical definition and
        # indent. The visible letter comes only from numPr.
        _section_banner(table, match.group(2), f'{match.group(1)}. ', 4)
        return
    ncols = len(table.columns)
    row = table.add_row()
    row.cells[0].merge(row.cells[ncols - 1])
    cell = row.cells[0]
    _shade_cell(cell, BANNER_FILL)
    _para(cell, _text(text), bold=True, size=BANNER_SIZE,
          space_after=Pt(2))


def _head_row(table, headers) -> None:
    """Baris header kolom: bold, horizontal/vertical center."""
    row = table.add_row()
    for i, head in enumerate(headers):
        _para(row.cells[i], _text(head), bold=True, size=BODY_SIZE,
              space_after=None)
        _center_cell(row.cells[i])
    _repeat_header(row)
    return row


def _new_numbering_instance(doc, abstract_num_id: int = 1) -> int:
    """Create a fresh Word list instance so each principle block restarts."""
    numbering = doc.part.numbering_part.element
    ids = [int(value) for value in numbering.xpath('./w:num/@w:numId')]
    num_id = max(ids or [0]) + 1
    num = OxmlElement('w:num')
    num.set(qn('w:numId'), str(num_id))
    abstract = OxmlElement('w:abstractNumId')
    abstract.set(qn('w:val'), str(abstract_num_id))
    num.append(abstract)
    # LibreOffice/Word may continue a list when only a new num instance is
    # added. Explicit override guarantees every principle block starts at 1.
    override = OxmlElement('w:lvlOverride')
    override.set(qn('w:ilvl'), '3')
    start = OxmlElement('w:startOverride')
    start.set(qn('w:val'), '1')
    override.append(start)
    num.append(override)
    numbering.append(num)
    return num_id


def _body_row(table, values) -> None:
    row = table.add_row()
    for i in range(len(table.columns)):
        _para(row.cells[i],
              _text(values[i]) if i < len(values) else '',
              space_after=None)
    return row


def _bullets_cell(cell, items, indent: bool = False) -> None:
    for item in items or []:
        text = _text(item.get('text', item) if isinstance(item, dict)
                     else item)
        if not text:
            continue
        paragraph = cell.add_paragraph(style='List Bullet')
        if indent:
            paragraph.paragraph_format.left_indent = Cm(0.75)
        _run(paragraph, text)


# ------------------------------------------------------------------
# Section A–E + Glosarium (struktur Templatku.docx, isi final result).
# ------------------------------------------------------------------

def _render_identitas(doc, identity: dict, module: dict):
    # Template §2: presentation label-value (bukan grid 2 kolom),
    # tanpa Versi Kurikulum, tanpa metadata internal.
    table = _new_table(doc, 1, 'a')
    _banner_row(table, 'A. IDENTITAS MODUL')
    ident = module.get('module_identity') or {}
    ctx = module.get('curriculum_context') or {}
    meetings = module.get('meetings') or []
    alokasi = ''
    if meetings:
        total_jp = sum(int(m.get('jp') or 0) for m in meetings
                       if isinstance(m, dict))
        if total_jp > 0:
            jps = {int(m['jp']) for m in meetings
                   if isinstance(m, dict) and int(m.get('jp') or 0) > 0}
            alokasi = (f"{total_jp} JP ({len(meetings)} Pertemuan"
                       + (f" x {sorted(jps)[0]} JP" if len(jps) == 1 else '')
                       + ")")
    kfs = '/'.join(_text(v) for v in
                   (_display_grade(module.get('grade')),
                    _text(module.get('phase')),
                    _display_semester(ident.get('semester'))) if _text(v))
    nama_label = ('Nama Madrasah' if ctx.get('education_system') == 'KEMENAG'
                  else 'Nama Sekolah')
    rows = [
        (nama_label, ident.get('satuan_pendidikan')),
        ('Nama Penyusun', module.get('penyusun')),
        ('Mata Pelajaran', module.get('subject')),
        ('Kelas / Fase /Semester', kfs),
        ('Alokasi Waktu', alokasi),
        ('Tahun Pelajaran', ident.get('year')),
    ]
    row = table.add_row()
    for label, value in rows:
        if _text(value):
            paragraph = _para(row.cells[0], '', space_after=None)
            paragraph.paragraph_format.tab_stops.add_tab_stop(Cm(5.0))
            _run(paragraph, f"{label}\t: {_text(value)}")
            paragraph.alignment = None
    _fix_layout(table, [1.0])
    _set_table_borders(table, color=BORDER_AUTO)


def _render_identifikasi(doc, identification: dict, module: dict,
                         general: dict):
    # Template §4: satu blok dokumen (satu sel isi), bukan row-table
    # terpisah per subbagian.
    table = _new_table(doc, 1, 'a0')
    _banner_row(table, 'B. IDENTIFIKASI')
    row = table.add_row()
    cell = row.cells[0]
    readiness = identification.get('learner_readiness') or {}
    _para(cell, 'Kesiapan Murid', bold=True, size=SUB_SIZE,
          space_after=Pt(2))
    readiness_paragraph = _para(
        cell,
        _text(readiness.get('summary')
              or readiness.get('note')
              or 'Belum ada data kesiapan.'),
        space_after=None)
    readiness_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY

    for aspect in readiness.get('aspects') or []:
        paragraph = cell.add_paragraph(style='List Bullet')
        _run(paragraph, _text(aspect))
    material = identification.get('material_characteristics') or {}
    _para(cell, 'Karakteristik Materi', bold=True, size=SUB_SIZE,
          space_after=Pt(2))
    _para(cell,
          _text(material.get('summary') or 'Belum ada ringkasan.'),
          space_after=Pt(2))
    dims = identification.get('profile_dimensions') or []
    dim_notes = identification.get('profile_dimension_notes') or {}
    if dims:
        _para(cell, 'Dimensi Profil Lulusan', bold=True,
              size=SUB_SIZE, space_after=Pt(2))
        for number, dim in enumerate(dims, start=1):
            _para(cell, f"{number}. {_text(dim)}", bold=True,
                  space_after=Pt(1))
            note = dim_notes.get(dim) if isinstance(dim_notes, dict) else None
            if isinstance(note, str) and note.strip():
                _para(cell, _text(note), space_after=Pt(2))
    _render_kbc_di_identifikasi(cell, module, general)
    _fix_layout(table, [1.0])
    _set_table_borders(table, color=BORDER_SECT)


def pair_kbc_items(themes, insertions):
    """Pasangan bernomor (tema, insersi) untuk render KBC (Batch 4).

    Aturan deterministik, tanpa karangan:
    1. insersi ber-field 'tema' dipasangkan ke tema yang sama
       (setiap insersi dipakai sekali);
    2. bila TIDAK ADA info tema sama sekali dan jumlah seimbang,
       pasangan posisional;
    3. selain itu: tema tanpa insersi tampil tanpa rincian, insersi
       tanpa tema tampil sebagai butir bernomor sendiri — tidak ada
       pasangan yang dikarang.
    Kembalikan list [(tema_atau_None, teks_atau_None)].
    """
    themes = [_text(t) for t in (themes or []) if _text(t)]
    items = []
    for ins in insertions or []:
        if isinstance(ins, dict):
            text = _text(ins.get('text'))
            tema = ins.get('tema')
            tema = tema if isinstance(tema, str) and tema.strip() else None
        else:
            text, tema = _text(ins), None
        if text:
            items.append({'text': text, 'tema': tema})
    pairs, used = [], set()
    any_tema = any(it['tema'] for it in items)
    for pos, theme in enumerate(themes):
        idx = None
        if any_tema:
            idx = next((i for i, it in enumerate(items)
                        if i not in used and it['tema'] == theme), None)
        elif items and len(items) == len(themes) and pos not in used:
            idx = pos
        if idx is not None:
            used.add(idx)
            pairs.append((theme, items[idx]['text']))
        else:
            pairs.append((theme, None))
    for i, it in enumerate(items):
        if i not in used:
            pairs.append((None, it['text']))
    return pairs


def _render_kbc_di_identifikasi(cell, module: dict, general: dict) -> bool:
    """KBC sebagai blok B. Identifikasi (khusus madrasah)."""
    ctx = module.get('curriculum_context') or {}
    if ctx.get('education_system') != 'KEMENAG':
        return False
    kbc = general.get('kbc') or {}
    themes = kbc.get('themes') or []
    if 'insertions' in kbc:
        insertion = [ins for ins in (kbc.get('insertions') or [])
                     if isinstance(ins, dict) and ins.get('active')
                     and _text(ins.get('text'))]
    else:
        insertion = kbc.get('insertion_material') or []
    if not (themes or insertion):
        return False
    _para(cell, 'Kurikulum Berbasis Cinta & Materi Insersi',
          bold=True, size=SUB_SIZE, space_after=Pt(2))
    # Batch 4: pasangan bernomor tema + insersi terkait (bukan dua
    # blok daftar terpisah).
    for number, (theme, text) in enumerate(
            pair_kbc_items(themes, insertion), start=1):
        if theme:
            _para(cell, f"{number}. {_text(theme)}", bold=True,
                  space_after=Pt(1))
        else:
            _para(cell, f"{number}. Materi insersi", bold=True,
                  space_after=Pt(1))
        if text:
            _para(cell, _text(text), space_after=Pt(2))
    return True


def _render_desain(doc, design: dict):
    table = _new_table(doc, 3, 'a2')
    _banner_row(table, 'C. DESAIN PEMBELAJARAN')
    row = table.add_row()
    row.cells[0].merge(row.cells[2])
    _para(row.cells[0], 'Capaian Pembelajaran (CP)', bold=True,
          size=SUB_SIZE, space_after=Pt(2))
    cp_paragraph = _para(
        row.cells[0],
        _continuous_text(design.get('cp') or 'CP tidak tersedia.'),
        italic=True, space_after=None)
    cp_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
    prov = design.get('cp_provenance') or {}
    source_doc = _text(prov.get('source_document_id'))
    if source_doc:
        line = f"Sumber: {source_doc}"
        page = prov.get('source_page')
        if isinstance(page, int) or (
                isinstance(page, str) and page.strip()):
            line += f", halaman {_text(page)}"
        _para(row.cells[0], line, size=SMALL_SIZE, color_hex=MUTED,
              space_after=Pt(2))
    row = table.add_row()
    row.cells[0].merge(row.cells[2])
    _para(row.cells[0], 'Tujuan Pembelajaran', bold=True, size=SUB_SIZE,
          space_after=Pt(2))
    _head_row(table, ['Nomor', 'Tujuan Pembelajaran', 'Level'])
    for t in design.get('tp') or []:
        row = _body_row(table, [_text(t.get('id')), _text(t.get('text')),
                                _text(t.get('cognitive_level'))])
        _center_cell(row.cells[0])
        _justify_cell(row.cells[1], vertical=True)
        _center_cell(row.cells[2])
    kktp = design.get('kktp') or []
    if kktp:
        row = table.add_row()
        row.cells[0].merge(row.cells[2])
        _para(row.cells[0], 'Kriteria Ketercapaian (KKTP)', bold=True,
              size=SUB_SIZE, space_after=Pt(2))
        for number, entry in enumerate(kktp, start=1):
            _para(row.cells[0], f"{number}. {_text(entry.get('id'))}",
                  bold=True, space_after=Pt(1))
            for crit in entry.get('criteria') or []:
                _para(row.cells[0], _text(crit), space_after=Pt(1))
    # Template §5: Topik TIDAK dirender di C (sudah di bawah judul).
    practices = design.get('pedagogical_practices') or []
    if practices:
        row = table.add_row()
        row.cells[0].merge(row.cells[2])
        _para(row.cells[0], 'Praktik Pedagogis', bold=True, size=SUB_SIZE,
              space_after=Pt(2))
        for number, practice in enumerate(practices, start=1):
            _para(row.cells[0], f"{number}. {_text(practice)}",
                  space_after=Pt(1))
    _fix_layout(table, TP_FRACS)
    _set_table_borders(table, color=BORDER_SECT)


def _render_pengalaman(doc, learning_experience: dict, meetings) -> None:
    meetings = [m for m in (meetings or []) if isinstance(m, dict)]

    def render_meeting(meeting, include_banner):
        table = _new_table(doc, 5)
        if include_banner:
            _banner_row(table, 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN')
        index = meeting.get('index')
        minutes = meeting.get('minutes') or 0
        row = table.add_row()
        row.cells[0].merge(row.cells[4])
        _para(row.cells[0],
              f"Pertemuan {index}: {meeting.get('jp')} JP "
              f"({minutes} menit)", bold=True, size=SUB_SIZE,
              space_after=Pt(2))
        stages = meeting.get('stages') or {}
        for stage in ('Pembuka', 'Inti', 'Penutup'):
            acts = stages.get(stage) or []
            row = table.add_row()
            row.cells[0].merge(row.cells[4])
            _para(row.cells[0], stage, bold=True, size=SUB_SIZE,
                  space_after=Pt(2))
            if acts:
                _head_row(table, ['Aktivitas', 'Deskripsi', 'Durasi',
                                  'TP', 'Pengalaman'])
                for activity in acts:
                    if not isinstance(activity, dict):
                        continue
                    row = _body_row(table, [
                        _text(activity.get('name')),
                        _text(activity.get('description')),
                        _text(activity.get('duration')),
                        _text(activity.get('tp_linked')
                              or activity.get('tp_reference')),
                        _text(activity.get('experience'))])
                    # Template keeps activity prose left-aligned, while all
                    # short/code columns are centered both ways.
                    for column in (2, 3, 4):
                        _center_cell(row.cells[column])
        _fix_layout(table, ACTIVITY_FRACS)
        _set_table_borders(table, color=BORDER_SECT)
        return table

    if meetings:
        for position, meeting in enumerate(meetings):
            render_meeting(meeting, include_banner=(position == 0))
            # A principle block is document body content, not a merged table
            # row. It therefore follows each meeting exactly like template.
            _render_principles(doc, meeting)
        return

    table = _new_table(doc, 5)
    _banner_row(table, 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN')
    experiences = learning_experience.get('experiences') or {}
    order = [k for k in ('memahami', 'mengaplikasi', 'merefleksi')
             if k in experiences] + [k for k in experiences
                                     if k not in ('memahami', 'mengaplikasi',
                                                  'merefleksi')]
    for exp in order:
        acts = experiences.get(exp) or []
        row = table.add_row()
        row.cells[0].merge(row.cells[4])
        _para(row.cells[0], f"Pengalaman {exp}", bold=True,
              size=SUB_SIZE, space_after=Pt(2))
        for activity in acts:
            if not isinstance(activity, dict):
                continue
            row = _body_row(table, [
                _text(activity.get('name')), _text(activity.get('description')),
                _text(activity.get('duration')),
                _text(activity.get('tp_linked') or activity.get('tp_reference')), ''])
            _center_cell(row.cells[2])
            _center_cell(row.cells[3])
    _fix_layout(table, ACTIVITY_FRACS)
    _set_table_borders(table, color=BORDER_SECT)


def _render_asesmen(doc, assessment: dict):
    # Template §8: Diagnostik 3 kolom + Jawaban Benar; Formatif dan
    # Sumatif 4 kolom + TP/KKTP. Tipe dalam Bahasa Indonesia.
    table = _new_table(doc, 4)
    _banner_row(table, 'E. ASESMEN')
    for label, key, diagnostic in (('Asesmen Diagnostik', 'awal', True),
                                   ('Asesmen Formatif', 'proses', False),
                                   ('Asesmen Sumatif', 'akhir', False)):
        items = assessment.get(key)
        row = table.add_row()
        row.cells[0].merge(row.cells[3])
        _shade_cell(row.cells[0], BANNER_FILL)
        _para(row.cells[0], label, bold=True, size=SUB_SIZE,
              space_after=Pt(2))
        if isinstance(items, dict):
            items = items.get('items', [])
        if diagnostic:
            rows = []
            for i in (items or []):
                if not isinstance(i, dict):
                    continue
                opts = _mc_options(i)
                rows.append((_mc_question(i),
                             _display_type(i.get('type')),
                             _answer_label(i, opts), opts))
            if rows:
                # Header template: Instrumen | Tipe | Jawaban Benar
                # (merged 2 kolom terakhir, grid 4 kolom dipertahankan).
                row = table.add_row()
                _para(row.cells[0], 'Instrumen', bold=True,
                      space_after=Pt(2))
                _center_cell(row.cells[0])
                _para(row.cells[1], 'Tipe', bold=True, space_after=Pt(2))
                _center_cell(row.cells[1])
                row.cells[2].merge(row.cells[3])
                _para(row.cells[2], 'Jawaban Benar', bold=True,
                      space_after=Pt(2))
                _repeat_header(row)
                for values in rows:
                    row = table.add_row()
                    _para(row.cells[0], values[0], space_after=Pt(2))
                    for opt in values[3]:
                        _para(row.cells[0],
                              f"{opt['label']}. {opt['text']}",
                              space_after=Pt(1))
                    _para(row.cells[1], values[1], space_after=Pt(2))
                    _center_cell(row.cells[1])
                    row.cells[1].vertical_alignment = \
                        WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    row.cells[2].merge(row.cells[3])
                    _para(row.cells[2], values[2], space_after=Pt(2))
                    _center_cell(row.cells[2])
                    row.cells[2].vertical_alignment = \
                        WD_CELL_VERTICAL_ALIGNMENT.CENTER
            elif items:
                row = table.add_row()
                row.cells[0].merge(row.cells[3])
                _bullets_cell(row.cells[0], items)
            continue
        rows = [(_text(i.get('question')), _display_type(i.get('type')),
                 _text(i.get('tp_linked')), _text(i.get('kktp_linked')))
                for i in (items or []) if isinstance(i, dict)]
        if rows:
            _head_row(table, ['Instrumen', 'Tipe', 'TP', 'KKTP'])
            for values in rows:
                row = _body_row(table, list(values))
                _center_cell(row.cells[1])
                _center_cell(row.cells[2])
                _center_cell(row.cells[3])
        elif items:
            row = table.add_row()
            row.cells[0].merge(row.cells[3])
            _bullets_cell(row.cells[0], items)
    _fix_layout(table, ASSESS_FRACS)
    _set_table_borders(table, color=BORDER_ASESMEN)


def _render_lampiran(doc, outline: dict):
    attachments = outline.get('attachments') or {}
    glosarium = attachments.get('glosarium') or []
    if not glosarium:
        return False
    table = _new_table(doc, 2)
    _banner_row(table, 'Glosarium')
    _head_row(table, ['Istilah', 'Definisi'])
    for g in glosarium:
        if isinstance(g, dict) and _text(g.get('istilah')):
            _body_row(table, [_text(g.get('istilah')),
                              _text(g.get('definisi'))])
    _fix_layout(table, GLOS_FRACS)
    _set_table_borders(table)
    return True


def _apply_base_styles(doc) -> None:
    """Keep style definitions from Templatku.docx untouched.

    The old renderer started from ``Document()`` and reconstructed styles,
    which silently changed Normal line spacing and list/heading inheritance.
    Template is now loaded before rendering; this hook intentionally only
    verifies required styles exist.
    """
    for name in ('Normal', 'List Paragraph', 'Heading 1'):
        if name not in doc.styles:
            raise ExportError(f"Template style hilang: {name}")


def _template_status() -> dict:
    """Status template master ``templates/Templatku.docx``.

    Renderer memakai file template sebagai master layout aktif.
    Fungsi memberi sinyal apakah template tersedia; saat hilang, export
    berhenti fail-closed dan tidak memakai fallback layout.
    """
    from pathlib import Path as _Path
    tpl = _Path(__file__).resolve().parents[1] / 'templates' / 'Templatku.docx'
    return {
        'exists': tpl.is_file(),
        'path': str(tpl),
        'layout_source': ('Templatku.docx (acuan visual)'
                          if tpl.is_file() else 'fallback kode (template hilang)'),
    }


def render_final_rpm_docx(result: dict, output_path) -> str:
    """Render FINAL VALIDATED RPM menjadi file .docx.

    Raise ExportError bila input bukan hasil final tervalidasi.
    Tidak memanggil AI; tidak mengubah data (deepcopy untuk
    keamanan). Return path file sebagai string.
    """
    module = assert_final_validated(result)
    module = deepcopy(module)
    outline = module['master_outline']

    template = _template_path()
    if not template.is_file():
        raise ExportError(
            f"Export ditolak: template layout tidak ditemukan: {template}")

    # Start from current master template. This preserves its styles,
    # numbering.xml, document defaults, table defaults, borders, and section
    # properties instead of approximating them with Document().
    doc = Document(str(template))
    _clear_template_body(doc)
    section = doc.sections[0]
    # Keep template page geometry as-is; these assertions prevent accidental
    # drift if master template is replaced again.
    if (abs(section.page_width.pt - Cm(PAGE_W_CM).pt) > 1.0
            or abs(section.page_height.pt - Cm(PAGE_H_CM).pt) > 1.0):
        raise ExportError('Template bukan A4; layout source tidak sesuai.')
    if any(abs(m.pt - Cm(MARGIN_CM).pt) > 1.0 for m in (
            section.top_margin, section.bottom_margin,
            section.left_margin, section.right_margin)):
        raise ExportError('Margin template bukan 2,5 cm; export dihentikan.')
    _apply_base_styles(doc)

    _para(doc, 'PERENCANAAN PEMBELAJARAN MENDALAM', bold=True,
          size=TITLE_SIZE, align=WD_PARAGRAPH_ALIGNMENT.CENTER,
          space_after=None)
    topik = (module.get('topic') or (module.get('unit') or {}).get('name')
             or '')
    if topik.strip():
        _para(doc, f"\u201c{topik.strip()}\u201d", size=TOPIC_SIZE,
              align=WD_PARAGRAPH_ALIGNMENT.CENTER, space_after=Pt(6))

    general = outline.get('general_information') or {}
    _render_identitas(doc, general.get('identity') or {}, module)
    _render_identifikasi(doc, outline.get('identification') or {},
                         module, general)
    _render_desain(doc, outline.get('design') or {})
    _render_pengalaman(doc, outline.get('learning_experience') or {},
                       module.get('meetings'))
    _render_asesmen(doc, outline.get('assessment') or {})
    _render_lampiran(doc, outline)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() != '.docx':
        out = out.with_suffix('.docx')
    doc.save(str(out))
    return str(out)
