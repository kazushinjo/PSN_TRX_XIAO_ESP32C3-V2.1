# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 JA6FUF (kazushinjo)
"""JLCPCB 提出用の製造データを作る（kicad-cli を使う）。

使い方（kicad フォルダで）:
    python3 make_production.py [基板ファイル] [出力フォルダ]
既定は PSN_TRX.kicad_pcb → production/。作るもの:
    production/gerbers/  ガーバー 11 層（内層のファイル名は In1_Cu・In2_Cu）、ドリル（PTH・NPTH）、ジョブファイル
    production/PSN_TRX_Gerber_JLCPCB.zip   上の 14 ファイル
    production/PSN_TRX_CPL_JLCPCB.csv      部品の座標（基板専用の H1〜H4・HS1 を除く）
    production/PSN_TRX_BOM_JLCPCB.csv      同じ値・同じ部品形をまとめた部品表
    PSN_TRX_pick_place.csv                 kicad-cli の座標ファイル（全部品）
    PSN_TRX_部品配置図.pdf                  F.Fab と外形の白黒の図（基板の大きさ、SVG を rsvg-convert で PDF に）
"""
import csv, os, re, shutil, subprocess, sys, tempfile, zipfile

K = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, 'PSN_TRX.kicad_pcb')
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HERE, 'production')
POS = os.path.join(os.path.dirname(OUT), 'PSN_TRX_pick_place.csv') if len(sys.argv) > 2 else os.path.join(HERE, 'PSN_TRX_pick_place.csv')
LAYERS = 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts'
BOARD_ONLY = re.compile(r'^(H\d+|HS\d+)$')   # 基板専用（取付穴・放熱器）は CPL・BOM に入れない


def run(*a):
    subprocess.run([K, *a], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def gerbers():
    g = os.path.join(OUT, 'gerbers')
    os.makedirs(g, exist_ok=True)
    for f in os.listdir(g):
        os.remove(os.path.join(g, f))
    run('pcb', 'export', 'gerbers', '--layers', LAYERS, '--subtract-soldermask', '-o', g + '/', PCB)
    run('pcb', 'export', 'drill', '--format', 'excellon', '--drill-origin', 'absolute', '--excellon-units', 'mm',
        '--excellon-separate-th', '-o', g + '/', PCB)
    # 内層はレイヤー名（GND Plane・Power Plane）でファイル名が付くので、In1_Cu・In2_Cu に直す（ジョブファイルの参照も）
    ren = {}
    for f in os.listdir(g):
        m = re.match(r'PSN_TRX-(.+)\.(g1|g2)$', f)
        if m and m.group(1) not in ('In1_Cu', 'In2_Cu'):
            new = f'PSN_TRX-{"In1_Cu" if m.group(2) == "g1" else "In2_Cu"}.{m.group(2)}'
            os.rename(os.path.join(g, f), os.path.join(g, new)); ren[f] = new
    job = os.path.join(g, 'PSN_TRX-job.gbrjob')
    if os.path.exists(job) and ren:
        s = open(job, encoding='utf-8').read()
        for a, b in ren.items():
            s = s.replace(a, b)
        open(job, 'w', encoding='utf-8').write(s)
    z = os.path.join(OUT, 'PSN_TRX_Gerber_JLCPCB.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(g)):
            zf.write(os.path.join(g, f), f)
    return sorted(os.listdir(g))


def positions():
    run('pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'both', '-o', POS, PCB)
    rows = list(csv.DictReader(open(POS, encoding='utf-8')))
    rows = [r for r in rows if not BOARD_ONLY.match(r['Ref'])]
    rows.sort(key=lambda r: natkey(r['Ref']))
    with open(os.path.join(OUT, 'PSN_TRX_CPL_JLCPCB.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\r\n')
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for r in rows:
            rot = float(r['Rot'])
            w.writerow([r['Ref'], f"{float(r['PosX']):.3f}mm", f"{float(r['PosY']):.3f}mm",
                        'Top' if r['Side'] == 'top' else 'Bottom', f'{rot:g}'])
    groups = {}
    for r in rows:
        groups.setdefault((r['Val'], r['Package']), []).append(r['Ref'])
    with open(os.path.join(OUT, 'PSN_TRX_BOM_JLCPCB.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\r\n')
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
        for (val, pkg), refs in sorted(groups.items(), key=lambda kv: natkey(sorted(kv[1], key=natkey)[0])):
            w.writerow([val, ','.join(sorted(refs, key=natkey)), pkg, ''])
    return len(rows), len(groups)


def placement_pdf():
    svg = os.path.join(tempfile.mkdtemp(), 'p.svg')
    run('pcb', 'export', 'svg', '--mode-single', '--layers', 'F.Fab,Edge.Cuts', '--page-size-mode', '2',
        '--exclude-drawing-sheet', '--black-and-white', '-o', svg, PCB)
    pdf = os.path.join(os.path.dirname(POS), 'PSN_TRX_部品配置図.pdf')
    subprocess.run(['rsvg-convert', '-f', 'pdf', '-o', pdf, svg], check=True)


if __name__ == '__main__':
    files = gerbers()
    n, g = positions()
    placement_pdf()
    print(f'gerbers {len(files)} files, CPL {n} parts, BOM {g} rows')
