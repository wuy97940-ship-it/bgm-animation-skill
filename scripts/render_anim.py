# -*- coding: utf-8 -*-
"""手绘风踩点动画渲染模板（720x720@30fps）。

bgm-animation 技能的参考实现。适配新 BGM 只改三处：
  1. PALETTE 调色板（角色配色）
  2. SUBS 歌词表 [(start, end, [行1, 行2...]), ...]
  3. main() 时间线（各节拍起止秒数与姿势参数）

运行: python render_anim.py
之后用 ffmpeg 合成，完整命令见 SKILL.md 第 5 步。
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

S = 2            # 2x 超采样抗锯齿
W = H = 720
FPS = 30
DUR = 20.2
N = int(DUR * FPS)
OUT = 'frames'
os.makedirs(OUT, exist_ok=True)

# ---------- PALETTE（角色配色，改编时只动这里） ----------
INK    = (52, 44, 42)        # 线稿深棕黑
SKIN   = (255, 233, 220)
HAIR   = (122, 92, 68)
HOODIE = (255, 247, 234)
AMBER  = (245, 176, 65)      # 缎带/抽绳/星星
BLUSH  = (246, 175, 168)
TEAR   = (168, 216, 240)
RED    = (224, 58, 47)       # 印章
WHITE  = (255, 255, 255, 255)

# ---------- SUBS 歌词表 ----------
SUBS = [
    (1.0,  6.0,  ['不小心惹了抖音', '它盯上我的作品']),
    (6.0,  7.0,  ['想用力的限流']),
    (7.0,  11.0, ['我发现我的播放寥寥无几']),
    (11.0, 15.3, ['他翻着烂的剪辑', '连官方都落下泪滴']),
    (15.3, 16.5, ['坨蒜放入我梦里']),
    (16.5, 19.7, ['告诉我连哪都无能为力']),
]

# ---------- 字体缓存 ----------
_F = {}
def F(size, bold=True):
    key = (size, bold)
    if key in _F:
        return _F[key]
    for f in (r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf',
              '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',):
        try:
            ft = ImageFont.truetype(f, size)
            _F[key] = ft
            return ft
    # 全部失败用默认字体
        except Exception:
            continue
    _F[key] = ImageFont.load_default()
    return _F[key]

# ---------- boiling line：每2帧换随机种子 ----------
def jit(pts, part, fi, amp=1.6):
    r = np.random.default_rng((part * 7919 + (fi // 2) * 104729) % (2**31))
    gx, gy = r.uniform(-amp, amp, 2)
    out = []
    for p in pts:
        out.append((p[0] + gx + r.uniform(-amp*0.5, amp*0.5),
                    p[1] + gy + r.uniform(-amp*0.5, amp*0.5)))
    return out

def partial(pts, frac):
    """按折线总长取前 frac 比例的子折线（起手画线演出）"""
    if frac >= 1.0:
        return pts
    if frac <= 0.0 or len(pts) < 2:
        return []
    lens = [math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
            for i in range(len(pts)-1)]
    target = sum(lens) * frac
    acc = 0.0
    out = [pts[0]]
    for i, L in enumerate(lens):
        if acc + L <= target:
            out.append(pts[i+1])
            acc += L
        else:
            k = (target - acc) / max(L, 1e-6)
            out.append((pts[i][0] + (pts[i+1][0]-pts[i][0])*k,
                        pts[i][1] + (pts[i+1][1]-pts[i][1])*k))
            break
    return out

def stroke(d, pts, w=9, fill=INK):
    if len(pts) < 2:
        return
    d.line(pts, fill=fill, width=w, joint='curve')
    r = w / 2 - 1
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0]-r, p[1]-r, p[0]+r, p[1]+r], fill=fill)

def c01(x):
    return max(0.0, min(1.0, x))

def ease_out(x):
    x = c01(x)
    return 1 - (1 - x) ** 3

def circle_pts(cx, cy, r, n=48):
    return [(cx + r * math.cos(2*math.pi*i/n), cy + r * math.sin(2*math.pi*i/n))
            for i in range(n+1)]

def star_pts(x, y, s, rot=0.0):
    pts = []
    for i in range(10):
        rr = s if i % 2 == 0 else s * 0.45
        a = rot + math.pi * i / 5 - math.pi / 2
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    return pts

def draw_subs(img, t, dx, dy):
    """歌词字幕：白字黑边，弹出动画"""
    for a, b, lines in SUBS:
        if not (a <= t < b):
            continue
        pop = 1.0 + (0.10 * (1 - (t - a) / 0.10) if t - a < 0.10 else 0.0)
        lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        lh = 66
        y0 = 645 - (len(lines) - 1) * lh / 2
        for i, ln in enumerate(lines):
            dl.text(((W//2 + dx) * S, (y0 + i*lh + dy) * S), ln,
                    font=F(int(50 * S * pop)), fill=(255, 255, 255, 255),
                    anchor='mm', stroke_width=int(7 * S),
                    stroke_fill=(30, 26, 26, 255))
        img.alpha_composite(lay)

# ---------- 角色 ----------
def draw_char(d, t, fi, st):
    bob = math.sin(t * 2.4) * 3.0 * st['bob_on']
    trem = math.sin(t * 26) * 1.5 if st['tremble'] else 0.0
    dx = st['shake'][0] + trem
    dy = st['shake'][1] + bob + trem * 0.5
    T = lambda p: ((p[0] + dx) * S, (p[1] + dy) * S)
    P = lambda pts: [T(p) for p in pts]
    def B(pts):
        (x0, y0), (x1, y1) = pts
        return ((x0 + dx) * S, (y0 + dy) * S, (x1 + dx) * S, (y1 + dy) * S)

    # 双丸子 + 缎带 + 呆毛
    if st['hair'] > 0:
        for i, (bx, by) in enumerate(((243, 172), (477, 172))):
            if st['hair'] > 0.35:
                d.ellipse(B([(bx-50, by-50), (bx+50, by+50)]), fill=HAIR)
            stroke(d, P(jit(partial(circle_pts(bx, by, 50), c01(st['hair']*1.4 - i*0.15)), 10+i, fi)), 9)
        if st['hair'] > 0.6:
            for i, (bx, by) in enumerate(((216, 208), (504, 208))):
                rib = [(bx, by), (bx-26, by-20), (bx-18, by+16), (bx, by)]
                rib2 = [(bx, by), (bx+26, by-20), (bx+18, by+16), (bx, by)]
                d.polygon(P(rib), fill=AMBER)
                d.polygon(P(rib2), fill=AMBER)
                stroke(d, P(jit(rib + rib2, 12+i, fi)), 7)
        stroke(d, P(jit(partial([(360, 138), (352, 108), (368, 92)], st['hair']), 14, fi)), 8)

    # 脸底 + 起手圆圈（0-1.5s 扫弧）
    hf = c01(t / 1.5)
    if st['face'] > 0.55:
        d.ellipse(B([(220, 145), (500, 425)]), fill=SKIN)
    stroke(d, P(jit(partial(circle_pts(360, 285, 140), hf), 20, fi)), 9)

    # 刘海 + 侧发
    if st['hair'] > 0:
        bang = [(224, 262), (250, 236), (272, 268), (300, 232), (330, 272),
                (360, 228), (392, 270), (424, 234), (452, 266), (478, 240), (496, 264)]
        fill_poly = bang + [(500, 210), (470, 160), (430, 150), (360, 145),
                            (290, 150), (250, 160), (220, 210)]
        if st['hair'] > 0.75:
            d.polygon(P(jit(fill_poly, 22, fi, amp=1.0)), fill=HAIR)
        stroke(d, P(jit(partial(bang, c01(t / 1.2)), 22, fi)), 9)
        for i, x0 in enumerate((232, 488)):
            sgn = -1 if i == 0 else 1
            pts = [(x0, 250), (x0 + 14*sgn, 300), (x0, 352), (x0 + 10*sgn, 392)]
            stroke(d, P(jit(partial(pts, c01(st['hair'] - 0.3)), 24+i, fi)), 8)

    # 眼睛
    eo = st['eye_open']
    show_face = st['face'] > 0.15
    if show_face:
        for i, ex in enumerate((305, 415)):
            if eo <= 0.05:
                stroke(d, P(jit([(ex-24, 296), (ex, 312), (ex+24, 296)], 30+i, fi)), 8)
            else:
                eh = 52 * eo
                ew = 36
                d.rounded_rectangle(B([(ex-ew/2, 296-eh/2), (ex+ew/2, 296+eh/2)]),
                                    radius=16*S, fill=INK)
                hx, hy = ex - 8, 296 - eh/2 + 10 - st['look_up'] * 8
                d.ellipse(B([(hx-6, hy-6), (hx+6, hy+6)]), fill=WHITE)
                if st['cry'] > 0:
                    d.ellipse(B([(ex-5, 299), (ex+9, 313)]), fill=(190, 228, 245))
                    stroke(d, P(jit([(ex-22, 318), (ex+22, 318)], 32+i, fi)), 6)
    # 眉
    if st['brow'] > 0 and show_face:
        for i, ex in enumerate((305, 415)):
            sgn = -1 if i == 0 else 1
            stroke(d, P(jit([(ex - sgn*20, 258 - st['brow']*6),
                             (ex + sgn*20, 252 + st['brow']*8)], 34+i, fi)), 6)
    # 腮红
    if st['face'] > 0.8:
        for bx in (272, 448):
            d.ellipse(B([(bx-17, 331), (bx+17, 349)]), fill=BLUSH)
    # 嘴
    mo = st['mouth']
    if not show_face:
        mpts = None
    elif mo == 'smile':
        mpts = [(346, 352), (360, 360), (374, 352)]
    elif mo == 'sad':
        mpts = [(344, 362), (360, 354), (376, 362)]
    elif mo == 'o':
        mpts = circle_pts(360, 356, 12, 20)
    elif mo == 'wavy':
        mpts = [(340, 358), (350, 352), (360, 358), (370, 352), (380, 358)]
    else:
        mpts = [(350, 356), (370, 356)]
    if mpts:
        stroke(d, P(jit(mpts, 38, fi)), 7)

    # 身体（奶油卫衣）
    if st['body'] > 0:
        frac = st['body']
        torso = [(300, 432), (420, 432), (438, 470), (432, 552), (288, 552), (282, 470), (300, 432)]
        if frac > 0.8:
            d.polygon(P(jit(torso, 40, fi, amp=1.0)), fill=HOODIE)
        stroke(d, P(jit(partial(torso, frac), 40, fi)), 9)
        if frac > 0.5:
            stroke(d, P(jit([(318, 442), (402, 442)], 42, fi)), 8, fill=AMBER)
            for i, sx in enumerate((342, 378)):
                stroke(d, P(jit([(sx, 446), (sx, 478)], 44+i, fi)), 5, fill=AMBER)
        if frac > 0.9:
            stroke(d, P(jit([(322, 498), (398, 498), (390, 540), (330, 540), (322, 498)], 46, fi)), 6)
        if frac > 0.85:
            for i, lx in enumerate((328, 392)):
                d.rectangle(B([(lx-13, 552), (lx+13, 600)]), fill=SKIN)
                d.rectangle(B([(lx-15, 566), (lx+15, 600)]), fill=WHITE)
                stroke(d, P(jit([(lx-15, 578), (lx+15, 578)], 48+i, fi)), 5, fill=AMBER)
                d.ellipse(B([(lx-16, 594), (lx+16, 614)]), fill=(232, 223, 211))
        if frac > 0.7:
            # 手臂：None=垂下；(x,y)=抬到该点(肘外撑)；[路径]=显式路径
            for side, sh, arm in (('l', (292, 448), st['arm_l']), ('r', (428, 448), st['arm_r'])):
                sgn = -1 if side == 'l' else 1
                if arm is None:
                    end = (252, 512) if side == 'l' else (468, 512)
                    mid = (268, 478) if side == 'l' else (452, 478)
                    pts = [sh, mid, end]
                elif isinstance(arm[0], (list, tuple)):
                    pts = list(arm)
                else:
                    end = arm
                    mid = (sh[0] + (end[0]-sh[0])*0.45 + sgn*16,
                           sh[1] + (end[1]-sh[1])*0.45 + 8)
                    pts = [sh, mid, end]
                part = 50 if side == 'l' else 52
                hend = pts[-1]
                d.line(P(jit(pts, part, fi)), fill=HOODIE, width=26*S, joint='curve')
                stroke(d, P(jit(pts, part, fi)), 8)
                d.ellipse(B([(hend[0]-14, hend[1]-14), (hend[0]+14, hend[1]+14)]), fill=SKIN)

# ---------- 道具 ----------
def stamp_state(t):
    """返回 (scale, alpha, shake)"""
    if not (6.0 <= t < 7.3):
        return 0.0, 0, (0, 0)
    slam = t - 6.0
    if slam < 0.18:
        k = slam / 0.18
        scale = 1.9 - 0.9 * ease_out(k)
    else:
        scale = 1.0
    alpha = 255
    if t > 7.0:
        alpha = int(255 * c01((7.3 - t) / 0.3))
    sh = (3, 2) if slam < 0.30 else (0, 0)
    return scale, alpha, sh

def draw_stamp(img, t, dx, dy):
    scale, alpha, _ = stamp_state(t)
    if scale <= 0:
        return
    cx, cy, bw, bh = 540, 156, 192, 96
    lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    b = [cx - bw/2*scale, cy - bh/2*scale, cx + bw/2*scale, cy + bh/2*scale]
    dl.rounded_rectangle([v*S for v in b], radius=14*S, outline=RED + (alpha,), width=int(8*S))
    dl.rounded_rectangle([(b[0]+5)*S, (b[1]+5)*S, (b[2]-5)*S, (b[3]-5)*S], radius=12*S,
                         outline=RED + (int(alpha*0.6),), width=int(3*S))
    dl.text((cx*S, cy*S), '限流', font=F(int(52*scale)), fill=RED + (alpha,), anchor='mm')
    lay = lay.rotate(-9, center=(cx*S, cy*S), resample=Image.BICUBIC)
    img.alpha_composite(lay)

def phone_state(t):
    if not (7.0 <= t < 11.35):
        return None
    rise = ease_out(c01((t - 7.0) / 0.4))
    drop = ease_out(c01((t - 11.0) / 0.3)) if t > 11.0 else 0.0
    px = 396
    py = 452 + (1 - rise) * 220 + drop * 240
    return px, py

def draw_phone(img, t):
    ps = phone_state(t)
    if ps is None:
        return
    px, py = ps
    rise = c01((t - 7.0) / 0.4)
    drop = c01((t - 11.0) / 0.3) if t > 11.0 else 0.0
    alpha = int(255 * min(1.0, rise * 1.4) * (1 - drop))
    pw, ph = 98, 142
    lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    box = [px-pw/2, py-ph/2, px+pw/2, py+ph/2]
    dl.rounded_rectangle([v*S for v in box], radius=12*S, fill=(60, 54, 52, alpha),
                         outline=INK + (alpha,), width=3*S)
    scr = [box[0]+8, box[1]+8, box[2]-8, box[3]-8]
    dl.rounded_rectangle([v*S for v in scr], radius=8*S, fill=(255, 252, 246, alpha))
    dl.text((px*S, (scr[1]+22)*S), '播放量', font=F(30), fill=(120, 110, 105, alpha), anchor='mm')
    if t < 8.0:   num = '3'
    elif t < 8.6: num = '5'
    elif t < 9.2: num = '7'
    else:         num = '9'
    tick = 1.25 if (t % 1.0 < 0.12 and num in ('3', '5', '7')) else 1.0
    dl.text((px*S, py*S), num, font=F(int(52*tick)), fill=(70, 62, 58, alpha), anchor='mm')
    ang = (t * 300) % 360
    dl.arc([(px-16)*S, (scr[3]-34)*S, (px+16)*S, (scr[3]-2)*S], start=ang, end=ang+240,
           fill=(150, 140, 135, alpha), width=int(4*S))
    lay = lay.rotate(4, center=(px*S, py*S), resample=Image.BICUBIC)
    img.alpha_composite(lay)

def draw_tears(img, t, dx, dy):
    if t < 11.0 or t > 19.5:
        return
    lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    drew = False
    for ex, phase in ((296, 0.0), (424, 0.45)):
        life = ((t - 11.0 + phase) % 0.95) / 0.95
        if life > 0.92:
            continue
        if life < 0.45:
            y = 322 + life / 0.45 * 66
            x = ex - life * 10
            size = 11
        else:
            yy = (life - 0.45) / 0.55
            y = 388 + yy * yy * 210
            x = ex - 10 - yy * 6
            size = 11 - 3 * yy
        a = int(235 * (1 - max(0.0, (life - 0.8) / 0.12)))
        cxp, cyp = (x + dx) * S, (y + dy) * S
        r = size * S
        dl.ellipse([cxp-r, cyp-r*0.9, cxp+r, cyp+r*0.9], fill=TEAR + (a,))
        dl.polygon([(cxp-r*0.55, cyp-r*0.75), (cxp+r*0.55, cyp-r*0.75), (cxp, cyp-r*1.9)],
                   fill=TEAR + (a,))
        dl.ellipse([cxp-r*0.35, cyp-r*0.55, cxp-r*0.05, cyp-r*0.2], fill=(226, 243, 252, a))
        drew = True
    if drew:
        img.alpha_composite(lay)

def draw_sleep(img, t):
    if not (15.3 <= t < 16.8):
        return
    lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    for k in range(3):
        life = ((t - 15.3) * 1.6 + k * 0.33) % 1.0
        zx = 468 + life * 40
        zy = 240 - life * 70
        a = int(200 * math.sin(min(1.0, life) * math.pi))
        dl.text((zx*S, zy*S), 'Z', font=F(int(30 + life * 26)), fill=(120, 110, 105, a), anchor='mm')
    cx, cy, r = 556, 112, 80
    a = int(230 * c01((t - 15.3) / 0.35))
    dl.ellipse([(cx-r)*S, (cy-r)*S, (cx+r)*S, (cy+r)*S], outline=(140, 128, 122, a), width=int(5*S))
    dl.ellipse([(cx-r*0.34)*S, (cy+r*0.92)*S, (cx-r*0.10)*S, (cy+r*1.16)*S],
               outline=(140, 128, 122, a), width=int(4*S))
    dl.ellipse([(cx-r*0.05)*S, (cy+r*1.06)*S, (cx+r*0.22)*S, (cy+r*1.30)*S],
               outline=(140, 128, 122, a), width=int(4*S))
    dl.arc([(cx-34)*S, (cy-34)*S, (cx+34)*S, (cy+34)*S], start=300, end=100,
           fill=AMBER + (a,), width=int(9*S))
    for sx, sy, ss in ((cx+30, cy-30, 12), (cx-40, cy+20, 10), (cx+42, cy+26, 9)):
        dl.polygon([(px*S, py*S) for px, py in star_pts(sx, sy, ss)], fill=AMBER + (a,))
    img.alpha_composite(lay)

def draw_end_star(img, t, fi):
    if t < 19.75:
        return
    k = ease_out(c01((t - 19.78) / 0.25))
    a = int(255 * k)
    pop = 1.0 + 0.5 * (1 - k)
    lay = Image.new('RGBA', (W*S, H*S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    dl.polygon([(px*S, py*S) for px, py in star_pts(360, 96, max(1.0, 30*pop*k), rot=fi*0.02)], fill=AMBER + (a,))
    for ang in (-30, 30, 90, 150, 210, 270):
        rr = 44 + 10 * k
        lx = 360 + rr * math.cos(math.radians(ang))
        ly = 96 + rr * math.sin(math.radians(ang))
        dl.line([(lx-7)*S, ly*S, (lx+7)*S, ly*S], fill=AMBER + (a,), width=int(4*S))
    img.alpha_composite(lay)

# ---------- 主循环 ----------
def main():
    print('frames:', N, flush=True)
    for fi in range(N):
        t = fi / FPS
        img = Image.new('RGBA', (W*S, H*S), WHITE)
        d = ImageDraw.Draw(img)
        st = {'face': 0.0, 'hair': 0.0, 'body': 0.0, 'eye_open': 1.0, 'brow': 0.0,
              'mouth': 'smile', 'cry': 0.0, 'tremble': False, 'bob_on': 1.0,
              'look_up': 0.0, 'arm_l': None, 'arm_r': None, 'shake': (0.0, 0.0)}
        # --- 时间线（改编时主要动这里） ---
        st['face'] = c01((t - 1.1) / 0.6)
        st['hair'] = c01((t - 1.75) / 1.2)
        st['body'] = c01((t - 2.75) / 1.2)
        if 3.2 <= t < 5.7:
            w = math.sin((t - 3.2) * 9.0)
            st['arm_r'] = (510 + w * 22, 352 + w * 24)
        if t >= 6.0:
            st['brow'] = c01((t - 6.0) / 0.6)
            st['mouth'] = 'sad'
        if 6.0 <= t < 6.9:
            st['mouth'] = 'o'
        if t >= 11.0:
            st['cry'] = c01((t - 11.0) / 0.5)
        if 15.3 <= t < 16.55:
            st['eye_open'] = 0.0
            st['brow'] = max(0.0, st['brow'] - c01((t - 15.3) / 0.4) * 0.6)
        if 16.5 <= t < 18.3:
            st['eye_open'] = 1.0
            st['arm_l'] = [(292, 448), (236, 416), (303, 322 + math.sin(t * 10) * 8)]
        if 18.3 <= t < 19.7:
            st['tremble'] = True
            st['mouth'] = 'wavy'
        if t >= 19.7:
            st['tremble'] = False
            st['look_up'] = c01((t - 19.7) / 0.3)
            st['mouth'] = 'smile'
            st['arm_l'] = None
        if st['eye_open'] > 0 and st['cry'] == 0:
            bt = (t - 2.0) % 2.7
            if bt < 0.12 and 2.0 < t < 14.5:
                st['eye_open'] = 0.0
        ps = phone_state(t)
        if ps is not None:
            px, py = ps
            st['arm_r'] = (px + 38, py + 34)
        _, _, sh = stamp_state(t)
        st['shake'] = (float(sh[0]), float(sh[1]))

        # --- 绘制（按层级） ---
        draw_char(d, t, fi, st)
        draw_stamp(img, t, st['shake'][0], st['shake'][1])
        draw_phone(img, t)
        draw_tears(img, t, st['shake'][0], st['shake'][1] + math.sin(t*2.4)*3.0)
        draw_sleep(img, t)
        draw_end_star(img, t, fi)
        draw_subs(img, t, 0, 0)

        img = img.convert('RGB').resize((W, H), Image.LANCZOS)
        if t > DUR - 0.45:
            k = c01((t - (DUR - 0.45)) / 0.45)
            img = Image.blend(img, Image.new('RGB', (W, H), (255, 255, 255)), k)
        img.save(os.path.join(OUT, f'{fi:04d}.png'))
        if fi % 120 == 0:
            print('render', fi, flush=True)
    print('done', flush=True)

if __name__ == '__main__':
    main()
