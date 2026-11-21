"""PA 出力の π 整合＋LPF の周波数特性と、PA 出力のスペクトルの図（README・報告書用）

  使い方: kicad/sim で  <numpy と matplotlib の入った python3> pa_plots.py
  出力: ../../docs/images/lpf_response_10_500MHz.png、../../docs/images/pa_output_spectrum.png
"""
import math, os, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import ngs
from gen import pin
from rf import lpf, DRAIN, RD_OPT
import tran

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, '..', '..', 'docs', 'images')
for fp in ('/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc', 'C:/Windows/Fonts/YuGothM.ttc'):
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=fp).get_name()
        break
plt.rcParams['axes.unicode_minus'] = False


def sweep(k=1.0, coss=18e-12, tc1=11e-12, kt=1.0, tc2=6.5e-12, f0=10e6, f1=500e6):
    """ドレイン（12.5Ω 源）→ π 整合＋LPF → 50Ω の利得（整合時 0dB）と、ドレインから見た負荷"""
    net = re.sub(r'\.ac .*', f'.ac dec 400 {f0:g} {f1:g}', lpf(k, coss, tc1, kt, tc2))
    ngs.run(net)
    f = np.array([x.real for x in ngs.vec('frequency')])
    vin = np.array(ngs.vec(DRAIN)); vo = np.array(ngs.vec(pin('C102', '1')))
    g = 20 * np.log10(np.abs(vo)) - 10 * math.log10(50 / RD_OPT)
    z = RD_OPT * vin / (2 - vin)
    return f, g, z


def fig_lpf():
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 6.8))
    for k, kt, tc2, ls, lab in ((1.00, 1.00, 6.5e-12, '-', 'L×1.00（TC4 6.5pF）'),
                                (0.93, 0.93, 6.5e-12, '--', 'L×0.93（TC4 6.5pF）'),
                                (1.07, 1.07, 5.0e-12, ':', 'L×1.07（TC4 を 5.0pF に合わせた）'),
                                (1.07, 1.07, 6.5e-12, '-.', 'L×1.07・TC4 未調整（6.5pF）')):
        f, g, z = sweep(k=k, kt=kt, tc2=tc2)
        ax[0].plot(f / 1e6, g, ls, lw=1.4, label=lab)
    for m in range(1, 6):
        ax[0].axvline(50.5 * m, color='0.6', lw=0.8, ls=':')
        ax[0].text(50.5 * m, 3, f'{m}f' if m > 1 else '50.5MHz', ha='center', fontsize=9, color='0.3')
    ax[0].axhline(-60, color='r', lw=0.9, ls='--'); ax[0].text(12, -58, '−60dB', color='r', fontsize=9)
    ax[0].set_xscale('log'); ax[0].set_xlim(10, 500); ax[0].set_ylim(-160, 8)
    ax[0].set_xlabel('周波数 [MHz]'); ax[0].set_ylabel('通り方 [dB]（ドレイン 12.5Ω 源 → 50Ω、整合時 0dB）')
    ax[0].set_title('π 整合（C111・L21・C98）＋ 7 素子 LPF ＋ 2 倍波トラップ')
    ax[0].grid(True, which='both', alpha=0.3); ax[0].legend(fontsize=9, loc='lower left')
    f, g, z = sweep(f0=10e6, f1=300e6)
    ax[1].plot(f / 1e6, np.abs(z), 'k-', lw=1.4, label='|Z|')
    ax[1].plot(f / 1e6, z.real, 'b--', lw=1.0, label='実部')
    ax[1].plot(f / 1e6, z.imag, 'g:', lw=1.0, label='虚部')
    ax[1].axhline(RD_OPT, color='r', lw=0.9, ls='--'); ax[1].text(12, RD_OPT + 1, f'{RD_OPT}Ω（12V で 5W に要る負荷）', color='r', fontsize=9)
    i = int(np.argmin(np.abs(f - 50.5e6)))
    ax[1].plot([50.5], [abs(z[i])], 'ro'); ax[1].annotate(f'50.5MHz: {z[i].real:.1f}{z[i].imag:+.1f}j Ω', (50.5, abs(z[i])), (70, 40), fontsize=9, arrowprops=dict(arrowstyle='->'))
    ax[1].set_xscale('log'); ax[1].set_xlim(10, 300); ax[1].set_ylim(-60, 80)
    ax[1].set_xlabel('周波数 [MHz]'); ax[1].set_ylabel('ドレインから見た負荷 [Ω]（Coss 18pF・RFC1 を含む）')
    ax[1].set_title('Q19 のドレインから見た負荷'); ax[1].grid(True, which='both', alpha=0.3); ax[1].legend(fontsize=9)
    fig.suptitle('PA 出力の π 整合と LPF（2026-11-22 の 5W 化後、ngspice の交流解析）', fontsize=12)
    fig.tight_layout(); out = os.path.join(IMG, 'lpf_response_10_500MHz.png'); fig.savefig(out, dpi=110); print('→', out)


def fig_spectrum():
    po, hl, hd, vmax, pdc = tran.pa_point(2.0, 0.2)
    fig, ax = plt.subplots(figsize=(13.5, 6.8))
    m = np.arange(1, 6); x = 50.5 * m
    drain = [0] + hd + [np.nan] * (4 - len(hd))
    out = [0] + hl
    B = -220
    d = [v if not np.isnan(v) else B for v in drain[:5]]
    ax.bar(x - 6, [v - B for v in d], bottom=B, width=10, color='0.65', label='Q19 のドレインの電圧（π 整合・LPF の前）')
    ax.bar(x + 6, [v - B for v in out], bottom=B, width=10, color='#c62828', label='アンテナ端（π 整合・LPF の後）')
    for xi, v in zip(x + 6, out):
        ax.text(xi, v + 2, f'{v:.0f}', ha='center', fontsize=9, color='#c62828')
    for xi, v in zip(x - 6, d):
        if B < v < 0: ax.text(xi, v + 2, f'{v:.0f}', ha='center', fontsize=9, color='0.3')
    ax.axhline(-60, color='k', lw=1.0, ls='--'); ax.text(30, -57, '規定 −60dBc（50MHz 帯、1W を超え 50W 以下）', fontsize=9)
    ax.set_xlim(25, 280)
    ax.set_xticks(x); ax.set_xticklabels([f'{v:.1f}MHz\n（{k} 倍）' if k > 1 else '50.5MHz\n（基本波）' for k, v in zip(m, x)])
    ax.set_ylim(-220, 10); ax.set_ylabel('基本波に対する比 [dBc]'); ax.grid(True, axis='y', alpha=0.3); ax.legend(fontsize=9, loc='upper right')
    ax.set_title(f'PA 出力のスペクトル（RD06HVF1、Idq 200mA・ゲート振幅 2.0V・電源 12V で {po:.1f}W、効率 {100*po/pdc:.0f}%、2 乗特性の簡易モデル）', fontsize=11)
    fig.tight_layout(); outp = os.path.join(IMG, 'pa_output_spectrum.png'); fig.savefig(outp, dpi=110); print('→', outp)
    print(f'  出力 {po:.2f}W、ドレインの 2〜4 倍波 {hd}、アンテナ端の 2〜5 倍波 {[round(v,1) for v in hl]}')


if __name__ == '__main__':
    fig_lpf(); fig_spectrum()
