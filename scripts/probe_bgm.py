# -*- coding: utf-8 -*-
"""探测参考视频并分析 BGM。

用法:
    python probe_bgm.py <参考视频>

输出:
    1. 视频流参数（分辨率/帧率/时长）
    2. 0.25s 粒度 RMS 能量包络柱状图
    3. 歌曲真实结束点与建议成片时长（参考片尾常带水印卡/静音，别带上）

依赖: pip install imageio-ffmpeg numpy
"""
import os
import subprocess
import sys
import wave

import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    video = sys.argv[1]
    ff = get_ffmpeg_exe()
    print('ffmpeg:', ff)

    # 1) 视频参数
    info = subprocess.run([ff, '-i', video], capture_output=True, text=True,
                          encoding='utf-8', errors='ignore')
    for ln in info.stderr.splitlines():
        if 'Duration' in ln or 'Stream #0:' in ln:
            print(ln.strip())

    # 2) 无损抽音轨 → 单声道 wav
    m4a = 'bgm_extract.m4a'
    wav = 'bgm_mono.wav'
    subprocess.run([ff, '-y', '-i', video, '-vn', '-acodec', 'copy', m4a],
                   capture_output=True)
    subprocess.run([ff, '-y', '-i', m4a, '-ac', '1', '-ar', '22050', '-f', 'wav', wav],
                   capture_output=True)
    if not os.path.exists(wav):
        print('FAIL: 音轨提取失败')
        return

    # 3) RMS 包络（0.25s 窗）
    w = wave.open(wav, 'rb')
    sr = w.getframerate()
    n = w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    w.close()
    win = int(sr * 0.25)
    env = np.array([np.sqrt(np.mean(x[i:i + win] ** 2))
                    for i in range(0, max(1, len(x) - win), win)])
    env = env / (env.max() + 1e-9)
    print('\nRMS 包络（0.25s/格）:')
    for i, e in enumerate(env):
        print(f'{i * 0.25:6.2f}s {e:5.2f} {"#" * int(e * 40)}')

    # 4) 歌曲结束点 = 最后一个 >15% 能量窗
    idx = np.where(env > 0.15)[0]
    if len(idx):
        end = idx[-1] * 0.25 + 0.25
        print(f'\n歌曲结束点 ≈ {end:.2f}s')
        print(f'建议成片时长 ≈ {end + 0.4:.1f}s（歌尾后留 0.4s 呼吸并淡出）')


if __name__ == '__main__':
    main()
