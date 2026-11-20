# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 JA6FUF (kazushinjo)
"""
部品実装図（docs/PSN_TRX_部品実装図_段階組立.pdf）を作る。
段階ごとに「組み立て」と「通電・確認」の 2 ページで、電源を入れて確かめながら 1 段ずつ組み立てられるようにした版。
受信は後ろ（低周波）から前（RF）へ、送信はマイクから PA へ組み、各段の入力に信号を入れて確かめる。

  1) KiCad 付属の Python で基板データを書き出す
       /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
           docs/tools/export_board.py kicad/PSN_TRX.kicad_pcb board.json
  2) matplotlib のある Python で作図する
       python3 docs/tools/make_parts_layout_v2.py board.json docs/tools/build_stages_v2.json docs/PSN_TRX_部品実装図_段階組立.pdf

build_stages_v2.json は段階ごとの部品（[部品番号, 値, 種類, 注意]）・メモ・通電の条件・確認項目・調整の番号。
確認項目の at は測る場所（"R18" は部品、"U7.1" はその部品の 1 番パッド）で、図に赤の番号を付ける。
最後のページは調整箇所（manual/調整手順.md の番号）と、どの段階で行うか。
"""
import json, math, sys, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Circle, Ellipse, Polygon
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.transforms as mtrans
from matplotlib.textpath import TextToPath

# 印刷で薄くならないよう、本文は W5・太字は W7（ない環境は W3・W6）
FW3 = '/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc'
FW6 = '/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc'
if not os.path.exists(FW3):
    FW3, FW6 = '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc', '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc'
if not os.path.exists(FW3):   # Windows: 游ゴシック
    FW3, FW6 = 'C:/Windows/Fonts/YuGothM.ttc', 'C:/Windows/Fonts/YuGothB.ttc'
for f in (FW3, FW6):
    fm.fontManager.addfont(f)
JP = fm.FontProperties(fname=FW3).get_name()
plt.rcParams['font.family'] = JP
BOLD = fm.FontProperties(fname=FW6)

board = json.load(open(sys.argv[1]))
notes = json.load(open(sys.argv[2]))
OUT = sys.argv[3]

TITLE = 'PSN_TRX_XIAO_ESP32C3-V2　部品実装図（段階組立・通電確認）'
SUB = '基板 134.1 × 129.7 mm / 4 層 / 基板 V2 Ver 1.4　部品実装図（段階組立）　2026-11-20　調整の番号は manual/調整手順.md'
COPPER = '#c8762f'
FAB = '#333333'
DONE = '#8a8a8a'
FAINT = '#d0d0d0'
NAVY = '#1f2d6b'
RED = '#d62728'
FS = 7.5               # 説明の文字（表・メモ・注意）はすべてこの大きさ
HEAD_RED = '#f5c4c4'    # 表の見出しの地（文字は黒）
HEAD_NAVY = '#c9d1ee'
A4 = (11.69, 8.27)

FP = {f['ref']: f for f in board['fps']}
stages = notes['stages']
member = {r[0]: si for si, s in enumerate(stages) for r in s['rows']}
SNO = [int(s['short'].split()[0]) for s in stages]   # 段階の番号（段階名の先頭の数字）
VAL = {r[0]: r[1] for s in stages for r in s['rows']}   # 値は表のものを優先（L15 330nH など、基板データより新しい）
xs = [p[0] for e in board['edge'] for p in (e.get('p') or [e.get('a'), e.get('b')]) if p]
ys = [p[1] for e in board['edge'] for p in (e.get('p') or [e.get('a'), e.get('b')]) if p]
BX0, BX1, BY0, BY1 = min(xs), max(xs), min(ys), max(ys)


def draw_shape(ax, s, col, lw):
    t = s['t']
    if t == 'seg':
        ax.plot([s['a'][0], s['b'][0]], [s['a'][1], s['b'][1]], color=col, lw=lw, solid_capstyle='round')
    elif t == 'poly':
        ax.add_patch(Polygon(s['p'], closed=True, fill=bool(s.get('fill')), fc=col if s.get('fill') else 'none', ec=col, lw=lw))
    elif t == 'circ':
        ax.add_patch(Circle(s['c'], s['r'], fill=bool(s.get('fill')), fc=col if s.get('fill') else 'none', ec=col, lw=lw))
    elif t == 'arc3':
        (x1, y1), (x2, y2), (x3, y3) = s['a'], s['m'], s['b']
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-9:
            return
        ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
        uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
        r = math.hypot(x1 - ux, y1 - uy)
        a1, a2, am = (math.atan2(y - uy, x - ux) for x, y in ((x1, y1), (x3, y3), (x2, y2)))

        def norm(a, ref):
            while a < ref:
                a += 2 * math.pi
            return a
        e1 = norm(a2, a1); m1 = norm(am, a1)
        if m1 > e1:
            e1 -= 2 * math.pi
        n = 30
        ax.plot([ux + r * math.cos(a1 + (e1 - a1) * k / n) for k in range(n + 1)],
                [uy + r * math.sin(a1 + (e1 - a1) * k / n) for k in range(n + 1)], color=col, lw=lw)


def draw_pad(ax, p, fc, ec):
    x, y = p['c']
    w, h = p['sz']
    tr = mtrans.Affine2D().rotate_deg_around(x, y, -p['ang']) + ax.transData
    if p['sh'] == 'circle':
        ax.add_patch(Circle((x, y), w / 2, fc=fc, ec=ec, lw=0.3))
    elif p['sh'] == 'oval':
        ax.add_patch(Ellipse((x, y), w, h, fc=fc, ec=ec, lw=0.3, transform=tr))
    else:
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc=fc, ec=ec, lw=0.3, transform=tr))
    if p['drill'] > 0:
        ax.add_patch(Circle((x, y), p['drill'] / 2, fc='white', ec='none'))


def draw_fp(ax, f, mode, label=True, small=False):
    """mode: 'hi'（この段階）/ 'done'（前の段階で付けた）/ 'faint'（まだ付けない）"""
    col = {'hi': FAB, 'done': DONE, 'faint': FAINT}[mode]
    for s in f['fab']:
        draw_shape(ax, s, col, 0.5 if mode == 'hi' else 0.4)
    for p in f['pads']:
        if mode == 'hi':
            draw_pad(ax, p, COPPER, '#7a4a1c')
        elif mode == 'done':
            draw_pad(ax, p, '#e3c9ae', '#a08060')
        else:
            draw_pad(ax, p, 'white', FAINT)
    if not label or mode == 'faint':
        return
    (x0, y0), (x1, y1) = f['bbox']
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ref = 'U7 (XIAO)' if f['ref'] == 'U7' else f['ref']
    if mode == 'done':
        ax.text(cx, cy, ref, ha='center', va='center', fontsize=3.8, color='black', zorder=20)
        return
    ax.text(cx, cy, ref, ha='center', va='center', fontsize=4.6 if small else 6.0, color='black', fontproperties=BOLD,
            zorder=20, bbox=dict(fc='white', ec='none', alpha=0.65, pad=0.2))
    v = VAL.get(f['ref'], f['val'])
    if not small and v and not f['ref'].startswith(('H', 'J')):
        ax.text(cx, cy + 1.7, v[:14], ha='center', va='center', fontsize=3.8, color='black', zorder=20)


def board_axes(fig, rect):
    ax = fig.add_axes(rect)
    ax.set_xlim(BX0 - 2, BX1 + 2)
    ax.set_ylim(BY1 + 2, BY0 - 2)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.add_patch(Rectangle((BX0, BY0), BX1 - BX0, BY1 - BY0, fill=False, ec='black', lw=1.4, zorder=30))
    return ax


def shade_parts(ax, upto, cur, alpha=0.55):
    """この段階の部品はその色で濃く、前の段階の部品は薄い灰色で塗る"""
    for f in board['fps']:
        si = member.get(f['ref'])
        if si is None or si > upto:
            continue
        (x0, y0), (x1, y1) = f['bbox']
        if si == cur:
            fc, a = stages[si]['color'], alpha
        else:
            fc, a = '#bdbdbd', 0.25
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fc, ec='none', alpha=a, zorder=0))


def draw_stage_board(ax, cur, label_cur=True):
    shade_parts(ax, cur, cur)
    for f in board['fps']:
        si = member.get(f['ref'])
        mode = 'faint' if si is None or si > cur else ('hi' if si == cur else 'done')
        draw_fp(ax, f, mode, label=label_cur or mode != 'hi')


def header(fig, sub_title, page, total, color='black'):
    fig.text(0.015, 0.965, TITLE, fontsize=13, fontproperties=BOLD, va='top')
    fig.text(0.015, 0.932, SUB, fontsize=7.5, color='black', va='top')
    if sub_title:
        fig.text(0.015, 0.905, sub_title, fontsize=11, fontproperties=BOLD, va='top', color=color)
    fig.text(0.985, 0.012, f'{page} / {total}', fontsize=7, ha='right', color='black')


SHORT_TYPE = {'セラミックコンデンサ': 'セラミックC', '電解コンデンサ': '電解C', 'トランジスタ/FET': 'Tr/FET', 'コイル/トランス': 'コイル',
              'トリマコンデンサ': 'トリマC', '半固定抵抗': '半固定VR', 'IC/レギュレータ': 'IC', 'マイコン(ソケット)': 'マイコン', 'フィルムコンデンサ': 'フィルムC'}


_TP = TextToPath()
_WCACHE = {}


def tw(v, fs, bold=False):
    """文字列の幅（pt）。フォントで実際に測る"""
    k = (v, bold)
    if k not in _WCACHE:
        prop = (BOLD if bold else fm.FontProperties(fname=FW3)).copy()
        prop.set_size(10)
        _WCACHE[k] = _TP.get_text_width_height_descent(v, prop, ismath=False)[0] / 10 if v else 0.0
    return _WCACHE[k] * fs


def fit(v, width_pt, fs, bold=False):
    """列幅（pt）に収まるよう末尾を「…」で切る"""
    if tw(v, fs, bold) <= width_pt:
        return v
    while v and tw(v + '…', fs, bold) > width_pt:
        v = v[:-1]
    return v + '…'


def wrap(v, width_pt, fs, bold=False):
    """列幅（pt）で折り返した行のリスト（行頭に句読点・閉じかっこが来ないようにする）"""
    lines, cur = [], ''
    for c in v:
        if cur and tw(cur + c, fs, bold) > width_pt:
            if c in '、。）」・，．:：' and len(cur) > 1:
                lines.append(cur[:-1]); cur = cur[-1]
            else:
                lines.append(cur); cur = ''
        cur += c
    if cur:
        lines.append(cur)
    return lines or ['']


def parts_table(fig, rect, rows, color):
    """rows: [[部品番号, 値, 種類, 注意]]。40 行を超えたら 2 段組み。"""
    cols = ['部品番号', '値/型番', '種類', '注意']
    n = len(rows)
    per = n if n <= 40 else math.ceil(n / 2)
    chunks = [rows[i:i + per] for i in range(0, n, per)]
    x0, y0, w, h = rect
    cwid = w / len(chunks)
    for ci, ch in enumerate(chunks):
        ax = fig.add_axes([x0 + ci * cwid, y0, cwid - 0.005, h])
        ax.axis('off')
        rh = min(0.034 / h, 1.0 / (len(ch) + 1))
        widths = [0.11, 0.23, 0.14, 0.52] if len(chunks) == 1 else [0.17, 0.25, 0.25, 0.33]
        xs_ = [sum(widths[:i]) for i in range(4)]
        fs = 6.4 if len(chunks) == 1 else 5.4
        ax.add_patch(Rectangle((0, 1 - rh), 1, rh, fc=color, ec='#888888', lw=0.4))
        for i, c in enumerate(cols):
            ax.text(xs_[i] + 0.01, 1 - rh / 2, c, fontsize=fs, va='center', color='black', fontproperties=BOLD)
        for r, row in enumerate(ch):
            yy = 1 - rh * (r + 2)
            ax.add_patch(Rectangle((0, yy), 1, rh, fc='#f3f3f3' if r % 2 else 'white', ec='#bbbbbb', lw=0.3))
            for i, v in enumerate(row):
                v = str(v)
                if i == 2:
                    v = SHORT_TYPE.get(v, v)
                f_i = fs if i < 3 else fs - 0.6
                v = fit(v, widths[i] * cwid * A4[0] * 72 - 3, f_i)
                ax.text(xs_[i] + 0.01, yy + rh / 2, v, fontsize=f_i, va='center',
                        fontproperties=BOLD if i == 0 else None, color='black', clip_on=True)
        for xv in xs_[1:]:
            ax.plot([xv, xv], [1 - rh * (len(ch) + 1), 1], color='#bbbbbb', lw=0.3)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def wrapped_table(fig, rect, head, rows, widths, hcolor, fs=FS, first_color='black', first_bold=True, pad=4):
    """折り返しつきの表。行の高さは一番長いセルに合わせる。表の高さに入りきらないときは文字を小さくする"""
    x0, y0, w, h = rect
    ax = fig.add_axes(rect); ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    W = w * A4[0] * 72; H = h * A4[1] * 72
    while True:
        lh = fs * 1.32
        cells = [[wrap(str(v), widths[i] * W - 5, fs) for i, v in enumerate(r)] for r in rows]
        heights = [max(len(c) for c in cs) * lh + pad for cs in cells]
        hh = fs * 1.32 + pad + 1
        if hh + sum(heights) <= H or fs < 4.8:
            break
        fs -= 0.2
        print('  表が入りきらないので文字を小さくした:', head[1], round(fs, 1))
    xs_ = [sum(widths[:i]) for i in range(len(widths))]
    y = 1
    ax.add_patch(Rectangle((0, y - hh / H), 1, hh / H, fc=hcolor, ec='#888888', lw=0.4))
    for i, c in enumerate(head):
        ax.text(xs_[i] + 3 / W, y - hh / H / 2, c, fontsize=fs, va='center', color='black', fontproperties=BOLD)
    y -= hh / H
    for k, (cs, rh) in enumerate(zip(cells, heights)):
        ax.add_patch(Rectangle((0, y - rh / H), 1, rh / H, fc='#f3f3f3' if k % 2 else 'white', ec='#bbbbbb', lw=0.3))
        for i, lines in enumerate(cs):
            for j, line in enumerate(lines):
                ax.text(xs_[i] + 3 / W, y - (pad / 2 + lh * (j + 0.5)) / H, line, fontsize=fs, va='center',
                        fontproperties=BOLD if (i == 0 and first_bold) else None,
                        color=first_color if i == 0 else 'black')
        for xv in xs_[1:]:
            ax.plot([xv, xv], [y - rh / H, y], color='#bbbbbb', lw=0.3)
        y -= rh / H
    return y


def at_xy(a):
    """'R18' → 部品の外形の中心、'U7.1' → そのパッドの中心"""
    if '.' in a:
        ref, pn = a.split('.', 1)
        for p in FP[ref]['pads']:
            if p['n'] == pn:
                return p['c'], None
        raise KeyError(a)
    (x0, y0), (x1, y1) = FP[a]['bbox']
    return ((x0 + x1) / 2, (y0 + y1) / 2), FP[a]['bbox']


def mark(ax, a, no):
    (x, y), bb = at_xy(a)
    if bb:
        (x0, y0), (x1, y1) = bb
        ax.add_patch(Rectangle((x0 - 0.6, y0 - 0.6), x1 - x0 + 1.2, y1 - y0 + 1.2, fill=False, ec=RED, lw=1.1, zorder=26))
        tx, ty = x0 - 0.8, y0 - 0.8
    else:
        ax.add_patch(Circle((x, y), 1.4, fill=False, ec=RED, lw=1.2, zorder=26))
        tx, ty = x - 1.6, y - 1.6
    ax.text(tx, ty, str(no), ha='right', va='bottom', fontsize=7.5, color='white', zorder=27,
            fontproperties=BOLD, bbox=dict(boxstyle='circle,pad=0.18', fc=RED, ec='none'))


def darker(col, k=0.72):
    return tuple(x * k for x in matplotlib.colors.to_rgb(col))


def smd_zoom(ax, ref, title):
    """表面実装 IC の周りを拡大して描く。1 番パッドは赤、IC の 1 番マークは黒丸"""
    f = FP[ref]
    pads = f['pads']
    cx = sum(p['c'][0] for p in pads) / len(pads); cy = sum(p['c'][1] for p in pads) / len(pads)
    R = 5.0
    ax.set_xlim(cx - R, cx + R); ax.set_ylim(cy + R, cy - R); ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])
    for g in board['fps']:
        if g['ref'] == ref:
            continue
        near = [p for p in g['pads'] if abs(p['c'][0] - cx) < R + 1.5 and abs(p['c'][1] - cy) < R + 1.5]
        for p in near:
            draw_pad(ax, p, '#e2e2e2', '#b0b0b0')
        if near:
            x = sum(p['c'][0] for p in near) / len(near); y = sum(p['c'][1] for p in near) / len(near)
            if abs(x - cx) < R - 0.3 and abs(y - cy) < R - 0.3:
                ax.text(x, y, g['ref'], ha='center', va='center', fontsize=FS, color='black', zorder=20)
    for p in pads:
        draw_pad(ax, p, RED if p['n'] == '1' else COPPER, '#7a4a1c')
        off = 1.15 if p['c'][1] > cy else -1.15
        ax.text(p['c'][0], p['c'][1] + off, p['n'], ha='center', va='center', fontsize=11, fontproperties=BOLD)
    xs_ = [p['c'][0] for p in pads]; ys_ = [p['c'][1] for p in pads]
    bw = max(xs_) - min(xs_) + 1.0; bh = 4.4   # 本体 3.0 × 4.4mm（足の並びが横）
    if max(ys_) - min(ys_) < max(xs_) - min(xs_):
        bw, bh = 4.4, max(ys_) - min(ys_) + 1.0
    ax.add_patch(Rectangle((cx - bw / 2, cy - bh / 2), bw, bh, fill=False, ec='black', lw=1.2, ls='--'))
    p1 = [p for p in pads if p['n'] == '1'][0]
    sx = 1 if p1['c'][0] > cx else -1; sy = 1 if p1['c'][1] > cy else -1
    ax.add_patch(Circle((cx + sx * (bw / 2 - 0.5), cy + sy * (bh / 2 - 0.55)), 0.25, color='black'))
    ax.text(cx, cy, 'IC 本体\n（印字面を上）', ha='center', va='center', fontsize=FS)
    side = ('右' if sx > 0 else '左') + ('下' if sy > 0 else '上')
    ax.set_title(f'{title}　1 番ピン = {side}', fontproperties=BOLD, fontsize=11)


def detail_page(s, page):
    d = s['detail']
    fig = plt.figure(figsize=A4)
    header(fig, d['title'], page, pages_total)
    for k, (ref, t) in enumerate((('U1', 'U1（第 1 混合）'), ('U2', 'U2（積検波）'))):
        smd_zoom(fig.add_axes([0.02 + k * 0.275, 0.47, 0.255, 0.34]), ref, t)
    yy = 0.445
    cap = ('部品面から見た拡大図（向きは部品実装図と同じ）。赤 = 1 番パッド、黒丸 = IC の 1 番マーク（くぼみ・点）、'
           '点線 = IC 本体、灰色 = まわりの部品の穴。')
    for w_ in wrap(cap, 0.53 * A4[0] * 72 - 10, FS):
        fig.text(0.015, yy, w_, fontsize=FS, va='top', color='black'); yy -= 0.0205
    fig.text(0.015, yy - 0.005, 'U1 と U2 は 180° 逆向き。', fontsize=FS + 1.5, va='top', fontproperties=BOLD, color=RED)
    # 左下と右側に文章
    cols = [(0.015, yy - 0.05, 0.03, 0.53), (0.565, 0.875, 0.03, 0.42)]
    ci = 0; x0, yy, ymin, wcol = cols[0]
    lh = 0.0205
    for head_, lines in d['sections']:
        need = lh * 1.3 + sum(len(wrap(l, wcol * A4[0] * 72 - 10, FS)) for l in lines) * lh
        if yy - need < ymin and ci == 0:
            ci = 1; x0, yy, ymin, wcol = cols[1]
        fig.text(x0, yy, '■ ' + head_, fontsize=FS, va='top', fontproperties=BOLD, color='black')
        yy -= lh * 1.25
        for l in lines:
            for j, w_ in enumerate(wrap(l, wcol * A4[0] * 72 - 10, FS)):
                fig.text(x0 + 0.008, yy, w_, fontsize=FS, va='top', color='black')
                yy -= lh
        yy -= lh * 0.4
    if yy < 0.03:
        print('  詳細ページの文字がはみ出した', yy)
    return fig


ADJ = {a['no']: a for a in notes['adjust']}
adj_stage = {}
for si, s in enumerate(stages):
    for n in s.get('adj', []):
        adj_stage.setdefault(n, []).append(str(SNO[si]))
pages_total = 1 + 2 * len(stages) + 1 + sum(1 for s in stages if s.get('detail'))
pdf = PdfPages(OUT, metadata={'Title': 'PSN_TRX_XIAO_ESP32C3-V2 部品実装図（段階組立・通電確認）', 'Author': 'JA6FUF'})

# ---- 1. 全体図と段階の一覧
fig = plt.figure(figsize=A4)
header(fig, '全体図と組み立ての段階（受信は低周波 → RF の順、送信はマイク → PA の順）', 1, pages_total)
ax = board_axes(fig, [0.01, 0.04, 0.50, 0.84])
for f in board['fps']:
    si = member.get(f['ref'])
    if si is None:
        continue
    (x0, y0), (x1, y1) = f['bbox']
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=stages[si]['color'], ec='none', alpha=0.5, zorder=0))
for f in board['fps']:
    draw_fp(ax, f, 'hi', label=False)
# 段階の番号を、その段階の部品の重心に置く
for si, s in enumerate(stages):
    pts = [((FP[r[0]]['bbox'][0][0] + FP[r[0]]['bbox'][1][0]) / 2, (FP[r[0]]['bbox'][0][1] + FP[r[0]]['bbox'][1][1]) / 2) for r in s['rows']]
    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    ax.text(cx, cy, str(SNO[si]), ha='center', va='center', fontsize=9, color='white', zorder=40, fontproperties=BOLD,
            bbox=dict(boxstyle='circle,pad=0.25', fc=darker(s['color'], 0.6), ec='white', lw=0.8))
rows = []
for si, s in enumerate(stages):
    adj = '・'.join(str(n) for n in s.get('adj', [])) or '—'
    rows.append([str(SNO[si]), s['name'], str(len(s['rows'])),
                 ' / '.join(c['where'].split('（')[0] for c in s['checks'][:2]), adj])
wrapped_table(fig, [0.525, 0.36, 0.46, 0.525], ['段階', '内容', '点数', '通電して確かめる主な所', '調整'], rows,
              [0.06, 0.29, 0.06, 0.44, 0.15], HEAD_NAVY)
gen = ['・段階ごとに、組み立てのページ（部品表）→ 通電・確認のページの順に進める。確認が全部合ってから次の段階へ。',
       '・通電は電流制限つきの安定化電源 12V で（段階 1 は 100mA、2〜12 は 300mA、13 は 500mA）。はんだ付けは必ず電源を切って。',
       '・電圧は GND（H1〜H4 の取付穴、J2 の 2 番）基準。まだ付けていない部品の穴（パッド）で測ってもよい。',
       '・前の段ができていないうちは、次の段の入力の穴に信号発生器から 0.01µF を通して信号を入れて確かめる（なければ飛ばして次へ）。',
       '・U1・U2 は秋月の NJM2594V SIP 化基板（表面実装なし）。背が高いので、それぞれ段階 8・5 の最後に縦に立てて付ける。',
       '・D0（送信検出）・D9（エンコーダの SW）は起動設定ピン。PTT やつまみを押したまま電源を入れない。',
       '・送信（段階 10〜13）は PTT を押している間だけ。段階 13 は ANT に必ず 50Ω ダミーロードをつなぐ。']
yy = 0.34
for line in gen:
    for j, l in enumerate(wrap(line, 0.46 * A4[0] * 72 - 8, FS)):
        fig.text(0.525 + (0.008 if j else 0), yy, l, fontsize=FS, va='top')
        yy -= 0.021
    yy -= 0.004
pdf.savefig(fig); plt.close(fig)

# ---- 段階ごとに 2 ページ
page = 2
for si, s in enumerate(stages):
    tcol = s['color']
    # (a) 組み立て
    fig = plt.figure(figsize=A4)
    header(fig, f"段階 {SNO[si]}　{s['name']}（{len(s['rows'])} 点）— 組み立て", page, pages_total)
    memo = s.get('memo', [])
    ax = board_axes(fig, [0.01, 0.06, 0.53, 0.80 - len(memo) * 0.022])
    draw_stage_board(ax, si)
    prow = [[r[0], r[1], SHORT_TYPE.get(r[2], r[2]), r[3]] for r in s['rows']]
    wrapped_table(fig, [0.55, 0.045, 0.44, 0.845], ['部品番号', '値/型番', '種類', '注意'], prow,
                  [0.12, 0.20, 0.15, 0.53], tcol, pad=3)
    for k, line in enumerate(memo):
        fig.text(0.015, 0.877 - k * 0.022, '・' + line, fontsize=FS, va='top', color='black')
    fig.text(0.015, 0.03, '色の濃い部品 = この段階で付ける。灰色 = 前の段階までに付けた部品。薄い線 = まだ付けない。'
             '□（四角）パッド = 1 番ピン / 電解コンデンサの＋ / ダイオードの K。', fontsize=FS, va='center', color='black')
    pdf.savefig(fig); plt.close(fig); page += 1
    if s.get('detail'):
        fig = detail_page(s, page)
        pdf.savefig(fig); plt.close(fig); page += 1

    # (b) 通電・確認
    fig = plt.figure(figsize=A4)
    header(fig, f"段階 {SNO[si]}　{s['name']} — 通電・確認", page, pages_total)
    fig.text(0.015, 0.878, '電源: ' + s['power'], fontsize=FS, va='top', fontproperties=BOLD, color='black')
    ax = board_axes(fig, [0.01, 0.04, 0.47, 0.80])
    draw_stage_board(ax, si, label_cur=True)
    for k, c in enumerate(s['checks'], 1):
        for a in c['at']:
            mark(ax, a, k)
    rows = [[str(k), c['where'], c['ok'], c.get('ng', '')] for k, c in enumerate(s['checks'], 1)]
    y = wrapped_table(fig, [0.49, 0.20, 0.50, 0.66], ['No', '測る所・操作', '目安（合格）', '外れたとき（確かめる所）'], rows,
                      [0.05, 0.38, 0.30, 0.27], HEAD_RED)
    yy = 0.20 + y * 0.66 - 0.035
    if s.get('adj'):
        fig.text(0.49, yy, 'この段階で行う調整（manual/調整手順.md）', fontsize=FS, va='top', fontproperties=BOLD, color='black')
        for n in s['adj']:
            a = ADJ[n]; yy -= 0.022
            fig.text(0.50, yy, f"調整 {n}　{a['what']}（{a.get('parts') or '・'.join(a['refs'])}）: {a['how']}", fontsize=FS, va='top')
        yy -= 0.03
    if s.get('note'):
        fig.text(0.49, yy, '注意: ' + s['note'], fontsize=FS, va='top', fontproperties=BOLD, color='black')
        yy -= 0.026
    nxt = f"→ 全部合ったら電源を切り、段階 {SNO[si + 1]}（{stages[si + 1]['name']}）へ" if si + 1 < len(stages) else '→ 組み立て・調整の完了。ケースに組み込む'
    fig.text(0.49, 0.045, nxt, fontsize=FS, va='center', fontproperties=BOLD, color='black')
    fig.text(0.49, 0.022, '赤の番号 = 表の No の測る所（四角 = 部品、丸 = その部品のピン・穴）', fontsize=FS, va='center', color='black')
    pdf.savefig(fig); plt.close(fig); page += 1

# ---- 調整箇所（どの段階で行うか）
fig = plt.figure(figsize=A4)
header(fig, '調整箇所（丸数字は manual/調整手順.md の手順の番号）', page, pages_total)
ax = board_axes(fig, [0.01, 0.06, 0.55, 0.80])
adj_refs = {r for a in notes['adjust'] for r in a['refs']}
for f in board['fps']:
    draw_fp(ax, f, 'hi' if f['ref'] in adj_refs else 'faint', label=f['ref'] in adj_refs)
for a in notes['adjust']:
    for r in a['refs']:
        mark(ax, r, a['no'])
rows = [[str(a['no']), a['what'], a.get('parts') or '・'.join(a['refs']), '段階 ' + '・'.join(adj_stage[a['no']]), a['how']] for a in notes['adjust']]
wrapped_table(fig, [0.575, 0.10, 0.415, 0.78], ['No', '調整', '部品', '行う段階', '合わせ方'], rows,
              [0.06, 0.25, 0.18, 0.12, 0.39], HEAD_RED)
fig.text(0.015, 0.875, '赤枠 = 調整する部品（半固定抵抗・トリマ・コア付きコイル）と、測る・値を選ぶ部品。番号順に、表の段階で調整する', fontsize=FS, va='top')
pdf.savefig(fig); plt.close(fig)
pdf.close()
print('pages', page, OUT)
