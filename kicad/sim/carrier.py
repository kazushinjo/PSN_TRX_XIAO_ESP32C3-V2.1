# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 JA6FUF (kazushinjo)
"""AM の搬送波を Si5351 の CLK2 で足す案（案 A）の検討

今の AM は送信局発を fc − 4kHz に置き、DSP で 4kHz ずらした搬送波＋音声を作っている（I/Q の出口が
コンデンサ結合で直流＝搬送波を出せないため）。局発の漏れが fc − 4kHz に残り、帯域外領域に入る。
案 A: 送信中は空いている CLK2 を PLLA の fc（CLK0 と同じ周波数）にし、抵抗とコンデンサで送信の
増幅段に足して搬送波にする。局発は fc、DSP は I 側に音声（DSB）を出すだけ → 局発の漏れは搬送波に重なる。

計算すること
  1. 足す点（Q17 のゲート = L12 のリンク、Q18 のベース）と抵抗の値ごとの搬送波の出力
  2. 搬送波と I 側の DSB の位相がそろう CLK2 の位相（Si5351 の位相の刻み 90°/16 = 5.625°）
  3. 搬送波＋I 側の音声で AM になるか（音声の正負で出力の振幅が対称に変わるか）
  4. 搬送波だけのときの高調波
  5. 受信中、CLK2 の BFO（12MHz）が足す点から受信の局発の線（C5 の点 → Q4）へもれる量
"""
import math, cmath, io, contextlib
import ngs
import full
from full import tx_net, tran, lin, phasor, lpf_h, db, pin, node

F = 50.5e6
T = 1 / F
VR5B, VR6B = 0.50, 0.53          # キャリアの漏れが最小になる VR5・VR6（シミュレーション結果.md 7 章）


def clk2(target, rinj, cinj=100e-12, cshunt=0.0, phase_deg=0.0, f=F, on=True):
    """CLK2（3.3V 矩形波、出力抵抗 30Ω、既存の R19・R20 の負荷つき）→ Rinj →（Cshunt）→ Cinj → target"""
    td = (phase_deg % 360) / 360 / f
    t = 1 / f
    src = (f"VCK2 ck2 0 PULSE(0 3.3 {td:g} 0.4n 0.4n {t/2-0.4e-9:g} {t:g})" if on else "VCK2 ck2 0 0")
    e = [src, f"RCK2 ck2 {pin('R19','1')} 30",
         f"R19 {pin('R19','1')} {pin('R19','2')} 1.2k", f"R20 {pin('R19','2')} 0 100",
         f"RINJ {pin('R19','1')} inj1 {rinj:g}"]
    if cshunt: e.append(f"CSH inj1 0 {cshunt:g}")
    e.append(f"CINJ inj1 {target} {cinj:g}")
    return '\n'.join(e) + '\n'


def point(vi=0.0, carrier=None, vs=12.0):
    """出力のフェーザ・電力・2〜5 倍波 dBc。carrier = clk2() の文字列（None なら CLK2 なし）"""
    net = tx_net(vi=vi, vq=0, vr3=VR5B, vr4=VR6B, vs=vs)
    if carrier: net += carrier
    tran(net, 0.1e-9, 12e-6, 10e-6)
    t = lin(0.1e-9)
    vo = ngs.vec(pin('C102', '1'))
    p = phasor(t, vo, F, 80)
    vc = ngs.vec(pin('C98', '1'))
    ph = [phasor(t, vc, F * m, 80) for m in range(1, 6)]
    hc = [abs(ph[m - 1] * lpf_h(m)) for m in range(1, 6)]
    return p, (abs(p) / math.sqrt(2)) ** 2 / 50, [db(x / hc[0]) for x in hc[1:]]


def dbm(w): return 10 * math.log10(max(w, 1e-15) / 1e-3)


def main():
    targets = {'Q17 のゲート（L12 のリンク）': pin('L12', 'AA'), 'Q18 のベース': pin('Q18', 'B')}
    pI, wI, _ = point(vi=0.1)
    p0, w0, _ = point()
    print(f'基準: I 側に音声 100mV（CLK2 なし）出力 {wI:.2f}W、音声なし（VR5 {VR5B}・VR6 {VR6B}）の漏れ {dbm(w0):.0f}dBm')

    print('\n## 1. 足す点と抵抗ごとの搬送波（音声なし、CLK2 の位相 0°）')
    res = {}
    for name, tgt in targets.items():
        for r in ((220, 470, 1000, 2200, 4700) if 'Q17' in name else (1000, 2200, 4700, 6800, 10000, 15000)):
            p, w, hs = point(carrier=clk2(tgt, r))
            res[(name, r)] = (p, w)
            print(f'  {name:18s} R {r:5d}Ω: 出力 {w:6.3f}W（{dbm(w):5.1f}dBm）位相 {math.degrees(cmath.phase(p / pI)):+6.1f}°（I 側の DSB に対して）')

    print('\n## 2〜4. 位相をそろえて AM にする')
    for name, tgt in targets.items():
        # 1W 前後になる抵抗を選ぶ
        cand = sorted(((abs(w - 1.0), r) for (n, r), (p, w) in res.items() if n == name))
        r = cand[0][1]
        p, w = res[(name, r)]
        dphi = math.degrees(cmath.phase(p / pI))
        # 搬送波を I 側の DSB と同相に: CLK2 を −dphi ずらす（5.625° 刻み）
        step = 90 / 16
        ph = round(-dphi / step) * step
        pc, wc, hs = point(carrier=clk2(tgt, r, phase_deg=ph))
        err = math.degrees(cmath.phase(pc / pI))
        print(f'  {name}: R {r}Ω、CLK2 の位相 {ph:+.3f}°（{round(ph/step):+d} 刻み）→ 搬送波 {wc:.2f}W、I 側の DSB との位相差 {err:+.1f}°')
        print(f'    搬送波だけの 2〜5 倍波: ' + ' / '.join(f'{x:+.0f}' for x in hs) + ' dBc')
        amps = []
        for v in (-0.06, -0.03, 0.0, 0.03, 0.06):
            pv, wv, _ = point(vi=v, carrier=clk2(tgt, r, phase_deg=ph))
            amps.append((v, abs(pv), math.degrees(cmath.phase(pv / pc))))
        a0 = abs(pc)
        print('    音声（直流）と出力の振幅（搬送波 = 1）・位相: ' +
              ', '.join(f'{v*1e3:+.0f}mV {a/a0:.2f} {d:+.0f}°' for v, a, d in amps))
        up = amps[-1][1] / a0 - 1; dn = 1 - amps[0][1] / a0
        print(f'    ±60mV で振幅 {up*100:+.0f}% / {-dn*100:+.0f}%（正負がそろっていれば AM、ずれは変調のひずみ。100% を超えると位相が反転）')

    print('\n## 5. 受信中の CLK2（BFO 12MHz）のもれ（送信の電源なし、C5 の点 = 受信の局発の線）')
    fb = 12e6
    for name, tgt in list(targets.items()) + [('注入なし（比較）', None)]:
        r = 1000 if tgt else 1e12
        tgt = tgt or pin('Q18', 'B')
        net = tx_net(vi=0, vq=0, vr3=VR5B, vr4=VR6B, vs=1e-3)
        # 受信中の CLK0 = 局発 38.5MHz に置き換え、CLK1 は止める
        tl = 1 / 38.5e6
        net = net.replace(f"VCK0 ck0 0 PULSE(0 3.3 0 0.4n 0.4n {T/2-0.4e-9:g} {T:g})",
                          f"VCK0 ck0 0 PULSE(0 3.3 0 0.4n 0.4n {tl/2-0.4e-9:g} {tl:g})")
        net = net.replace(f"VCK1 ck1 0 PULSE(0 3.3 {T/4:g} 0.4n 0.4n {T/2-0.4e-9:g} {T:g})", "VCK1 ck1 0 0")
        net += clk2(tgt, r, f=fb)
        tran(net, 0.2e-9, 6e-6, 4e-6)
        t = lin(0.2e-9)
        v = ngs.vec(pin('C5', '2'))
        lo = abs(phasor(t, v, 38.5e6, 77)); bf = abs(phasor(t, v, fb, 24))
        print(f'  {name}（R {r:g}Ω）: 局発 38.5MHz {lo*1e3:.0f}mV、BFO 12MHz のもれ {bf*1e6:.1f}µV（局発に対して {db(bf/lo):.0f}dB）')


if __name__ == '__main__':
    main()
