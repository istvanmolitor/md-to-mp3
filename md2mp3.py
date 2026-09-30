#!/usr/bin/env python3
"""
Markdown -> MP3 felolvasó szkript, magyar Edge-TTS neurális hangokkal.

Használat:
    python3 md2mp3.py 01_bigdata_hadoop.md 02_cloud_iot.md 03_elosztott_rendszerek_1.md
    python3 md2mp3.py *.md --voice hu-HU-TamasNeural --rate +10%

Előfeltétel:
    pip3 install --user edge-tts
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "hu-HU-NoemiNeural"  # alternatíva: hu-HU-TamasNeural
MAX_CHARS = 4000  # egy TTS-kérésben elküldött szöveg max. hossza


def clean_table(block_lines: list[str]) -> str:
    """Egy markdown táblázat sorait natúr, felolvasható mondatokká alakítja."""
    rows = []
    header = None
    for line in block_lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # elválasztó sor (---|---|---) kihagyása
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if header is None:
            header = cells
            continue
        rows.append(cells)

    if not header:
        return ""

    sentences = []
    for row in rows:
        parts = []
        for h, c in zip(header, row):
            h = strip_inline_markdown(h)
            c = strip_inline_markdown(c)
            if not c:
                continue
            if h:
                parts.append(f"{h}: {c}")
            else:
                parts.append(c)
        if parts:
            sentences.append("; ".join(parts) + ".")
    return "\n".join(sentences)


def strip_inline_markdown(text: str) -> str:
    # linkek: [szöveg](url) -> szöveg
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1", text)
    # inline kód
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # félkövér / dőlt
    text = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    return text.strip()


def markdown_to_text(md: str) -> str:
    lines = md.splitlines()
    out = []
    i = 0
    in_code_block = False
    table_buffer: list[str] = []

    def flush_table():
        if table_buffer:
            out.append(clean_table(table_buffer))
            table_buffer.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # kódblokk (```...```) -- teljesen kihagyjuk (ASCII-ábrák, SQL, stb.)
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            i += 1
            continue

        # markdown táblázat sorainak összegyűjtése
        if stripped.startswith("|"):
            table_buffer.append(line)
            i += 1
            continue
        else:
            flush_table()

        # idézet (blockquote) jel törlése
        if stripped.startswith(">"):
            stripped = stripped.lstrip(">").strip()

        # vízszintes vonal kihagyása
        if re.fullmatch(r"[-*_]{3,}", stripped):
            i += 1
            continue

        # fejlécek: # jelek törlése, a szöveg marad
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            text = strip_inline_markdown(heading_match.group(2))
            out.append(text + ".")
            i += 1
            continue

        # listaelemek jelének törlése
        list_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if list_match:
            out.append(strip_inline_markdown(list_match.group(1)))
            i += 1
            continue

        num_list_match = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if num_list_match:
            out.append(strip_inline_markdown(num_list_match.group(2)))
            i += 1
            continue

        if stripped:
            out.append(strip_inline_markdown(stripped))
        else:
            out.append("")

        i += 1

    flush_table()

    text = "\n".join(out)
    # túl sok üres sor összevonása
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for p in paragraphs:
        candidate = (current + "\n\n" + p) if current else p
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = p
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def synthesize_chunk(text: str, voice: str, rate: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


async def convert_file(md_path: Path, outdir: Path, voice: str, rate: str, max_chars: int):
    print(f"[{md_path.name}] beolvasás és tisztítás...")
    raw = md_path.read_text(encoding="utf-8")
    plain = markdown_to_text(raw)
    chunks = chunk_text(plain, max_chars)
    print(f"[{md_path.name}] {len(chunks)} darab hangrészletre bontva.")

    tmpdir = outdir / f".tmp_{md_path.stem}"
    tmpdir.mkdir(parents=True, exist_ok=True)

    part_paths = []
    for idx, chunk in enumerate(chunks, start=1):
        part_path = tmpdir / f"part_{idx:03d}.mp3"
        print(f"[{md_path.name}] {idx}/{len(chunks)} rész felolvasása ({len(chunk)} karakter)...")
        await synthesize_chunk(chunk, voice, rate, part_path)
        part_paths.append(part_path)

    final_path = outdir / f"{md_path.stem}.mp3"
    with open(final_path, "wb") as out_f:
        for p in part_paths:
            out_f.write(p.read_bytes())

    for p in part_paths:
        p.unlink()
    tmpdir.rmdir()

    print(f"[{md_path.name}] KÉSZ -> {final_path}")


async def main_async(args):
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for md_file in args.files:
        md_path = Path(md_file)
        if not md_path.exists():
            print(f"HIBA: nem található: {md_path}", file=sys.stderr)
            continue
        await convert_file(md_path, outdir, args.voice, args.rate, args.max_chars)


def main():
    parser = argparse.ArgumentParser(description="Markdown fájlok felolvasása MP3-ba (Edge-TTS, magyar hang).")
    parser.add_argument("files", nargs="+", help="A konvertálandó .md fájl(ok)")
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                         help=f"TTS hang (alap: {DEFAULT_VOICE}, alternatíva: hu-HU-TamasNeural)")
    parser.add_argument("--rate", default="+0%", help="Beszédsebesség módosítása, pl. +10%% vagy -10%%")
    parser.add_argument("--outdir", default="mp3", help="Kimeneti mappa (alap: ./mp3)")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS, help="Max. karakterszám hangrészletenként")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
