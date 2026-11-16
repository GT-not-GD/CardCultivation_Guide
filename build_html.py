#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【卡牌修仙传】图鉴攻略 HTML & Markdown 生成器
读取 docs/data/*.json，自动生成可直接双击打开、也可直接部署到 GitHub Pages 的 docs/index.html 与 Markdown 文档。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DATA_DIR = DOCS_DIR / "data"
MD_DIR = DOCS_DIR / "markdown"

# 分类排序优先级（与游戏内【图鉴】顺序一致）
CATEGORY_ORDER = [
    "卡牌 / 材料",
    "卡牌 / 灵草&丹药",
    "卡牌 / 感悟&心法",
    "卡牌 / 技能&口诀",
    "卡牌 / 道具&传闻",
    "卡牌 / 指点卡",
    "卡牌 / 载具",
    "卡牌 / 天赋",
    "人物",
    "剧情",
    "法宝&傀儡",
    "灵兽",
    "妖兽",
    "妖王",
]


def load_categories(data_dir: Path) -> List[Dict[str, Any]]:
    categories: List[Dict[str, Any]] = []
    if not data_dir.exists():
        return categories

    for jf in sorted(data_dir.glob("*.json")):
        if jf.name == "manifest.json":
            continue
        try:
            payload = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[警告] 跳过无法解析的数据文件 {jf.name}: {exc}")
            continue
        if not isinstance(payload, dict) or "items" not in payload:
            continue
        payload.setdefault("file_name", jf.name)
        categories.append(payload)

    def sort_key(cat: Dict[str, Any]) -> tuple:
        full_name = cat.get("full_category") or cat.get("category") or ""
        try:
            idx = CATEGORY_ORDER.index(full_name)
        except ValueError:
            idx = 999
        return (idx, full_name)

    categories.sort(key=sort_key)
    return categories


def write_markdown_files(categories: List[Dict[str, Any]]) -> None:
    if not categories:
        return
    MD_DIR.mkdir(parents=True, exist_ok=True)
    for cat in categories:
        slug = cat.get("slug") or "category"
        title = cat.get("full_category") or cat.get("category") or slug
        items = cat.get("items", [])
        unlocked = [it for it in items if not it.get("locked")]
        lines = [
            f"# 【卡牌修仙传】图鉴攻略 — {title}",
            "",
            f"- 收录总数：{len(items)}（已获得 {len(unlocked)} / 🔒 未获得 {len(items) - len(unlocked)}）",
            f"- 更新时间：{cat.get('updated_at', '')}",
            "",
            "---",
            "",
        ]
        for it in items:
            idx = it.get("index", 0) + 1
            name = it.get("name") or f"条目 #{idx}"
            if it.get("locked"):
                lines.append(f"## {idx}. {name}（🔒 未获得）")
                lines.append("")
                lines.append("> 尚未获得此卡牌，以下为图鉴中可见的部分信息。")
            else:
                lines.append(f"## {idx}. {name}")
            lines.append("")
            icon_rel = it.get("icon_image") or it.get("card_image")
            if icon_rel:
                lines.append(f"![{name}](../{icon_rel})")
                lines.append("")
            for para in it.get("intro_paragraphs", []):
                if para.strip():
                    lines.append(para.strip())
                    lines.append("")
            for sec in it.get("sections", []):
                sec_title = sec.get("title", "").strip()
                if sec_title:
                    lines.append(f"### 【{sec_title}】")
                    lines.append("")
                for para in sec.get("paragraphs", []):
                    if para.strip():
                        lines.append(para.strip())
                        lines.append("")
            if not it.get("intro_paragraphs") and not it.get("sections") and it.get("full_text"):
                lines.append(it["full_text"].strip())
                lines.append("")
            lines.append("---")
            lines.append("")

        out_md = MD_DIR / f"{slug}.md"
        out_md.write_text("\n".join(lines), encoding="utf-8")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>卡牌修仙传 · 图鉴全攻略</title>
<style>
  :root {
    --bg-outer: #1d1915;
    --bg-ink: #27211b;
    --parchment: #e9dec9;
    --parchment-light: #f3ecdd;
    --parchment-dark: #d9cab0;
    --card-bg: #6f5d4b;
    --card-header: #211d18;
    --ink: #2d241b;
    --ink-body: #584931;
    --ink-muted: #7e6e56;
    --accent-gold: #e7c86b;
    --accent-gold-dark: #9d7827;
    --accent-red: #a34838;
    --accent-tab: #c69a88;
    --border-dark: #1f1a15;
    --border-soft: #c7b596;
    --warn-bg: #fff3cd;
    --warn-border: #d6a22a;
    --ok-green: #386b42;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background:
      radial-gradient(ellipse at 20% 0%, rgba(231, 200, 107, 0.08), transparent 55%),
      radial-gradient(ellipse at 85% 100%, rgba(163, 72, 56, 0.10), transparent 55%),
      var(--bg-outer);
    color: var(--ink);
    font-family: "STKaiti", "KaiTi", "FangSong", "Noto Serif SC", "PingFang SC", "Microsoft YaHei", serif;
    min-height: 100vh;
    line-height: 1.65;
  }

  .app-shell {
    max-width: 1460px;
    margin: 0 auto;
    padding: 20px 18px 40px;
  }

  /* 顶部标题栏 */
  .top-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 14px 22px;
    background: linear-gradient(180deg, #322a22 0%, #241e18 100%);
    border: 2px solid #0f0d0a;
    border-bottom: 3px solid var(--accent-gold-dark);
    border-radius: 6px 6px 0 0;
    color: var(--parchment-light);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .brand-seal {
    width: 42px;
    height: 42px;
    border-radius: 4px;
    background: var(--accent-red);
    border: 2px solid #f2dec0;
    color: #fff8eb;
    display: grid;
    place-items: center;
    font-weight: 700;
    font-size: 18px;
    letter-spacing: 1px;
    box-shadow: inset 0 0 0 2px rgba(0,0,0,0.2);
    flex-shrink: 0;
  }

  .brand h1 {
    font-size: 23px;
    letter-spacing: 2px;
    color: var(--accent-gold);
    text-shadow: 0 2px 4px rgba(0,0,0,0.6);
  }

  .brand-sub {
    font-size: 13px;
    color: #bfb199;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .header-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .btn {
    cursor: pointer;
    border: 1.5px solid #594b3b;
    background: #3a3128;
    color: var(--parchment-light);
    padding: 7px 13px;
    border-radius: 4px;
    font-size: 13px;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: inherit;
  }

  .btn:hover { background: #4b3f33; border-color: var(--accent-gold); }
  .btn.active {
    background: var(--accent-gold);
    color: #1f1912;
    border-color: #fff1b8;
    font-weight: 600;
  }
  .btn-light {
    background: var(--parchment-light);
    color: var(--ink);
    border-color: #9e8b6e;
  }
  .btn-light:hover { background: #fffaf0; border-color: var(--accent-red); }
  .btn-primary {
    background: var(--accent-red);
    color: #fff9ef;
    border-color: #7d2e20;
  }
  .btn-primary:hover { background: #b85341; }

  /* 分类页签 */
  .category-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 16px 0;
    background: #2b241d;
    border-left: 2px solid #0f0d0a;
    border-right: 2px solid #0f0d0a;
  }

  .cat-tab {
    cursor: pointer;
    padding: 9px 18px;
    background: #877860;
    color: #f4ecdc;
    border: 2px solid #181410;
    border-bottom: none;
    border-radius: 5px 5px 0 0;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 1px;
    transition: all 0.15s ease;
  }
  .cat-tab:hover { background: #9c8c71; }
  .cat-tab.active {
    background: linear-gradient(180deg, #f6e18b 0%, #dfc065 100%);
    color: #261d12;
  }
  .cat-tab .count {
    font-size: 12px;
    opacity: 0.8;
    margin-left: 5px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  /* 卷轴羊皮纸主框 */
  .scroll-frame {
    background: var(--parchment);
    border: 3px solid var(--border-dark);
    border-radius: 0 0 6px 6px;
    box-shadow:
      inset 0 0 40px rgba(120, 95, 60, 0.18),
      0 14px 36px rgba(0, 0, 0, 0.5);
    min-height: 680px;
  }

  /* 工具栏：搜索 & 筛选 */
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 20px;
    background: rgba(212, 196, 168, 0.55);
    border-bottom: 1.5px solid var(--border-soft);
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .search-wrap {
    position: relative;
    flex: 1 1 280px;
    max-width: 440px;
  }

  .search-input {
    width: 100%;
    padding: 8px 34px 8px 14px;
    border: 1.5px solid #9d8b6f;
    border-radius: 4px;
    background: var(--parchment-light);
    color: var(--ink);
    font-size: 14px;
    outline: none;
  }
  .search-input:focus { border-color: var(--accent-red); background: #fffdf8; }

  .search-clear {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    border: none;
    background: transparent;
    color: var(--ink-muted);
    cursor: pointer;
    font-size: 16px;
    display: none;
  }

  .filter-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }

  .chip {
    cursor: pointer;
    padding: 5px 12px;
    border-radius: 3px;
    border: 1px solid #ad9a7d;
    background: #dfd2bc;
    color: #4b3d2b;
    font-size: 13px;
    transition: all 0.12s;
  }
  .chip:hover { background: #e9decb; }
  .chip.active {
    background: var(--accent-red);
    color: #fff8ee;
    border-color: #7d3022;
    font-weight: 600;
  }

  .stats-text {
    color: var(--ink-muted);
    font-size: 13px;
  }

  /* 视图1：仿游戏图鉴双栏布局 */
  .codex-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.48fr) minmax(340px, 1fr);
    min-height: 620px;
  }

  .card-grid-pane {
    padding: 20px;
    border-right: 1.5px solid var(--border-soft);
    max-height: 76vh;
    overflow-y: auto;
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 13px;
  }

  .card-tile {
    cursor: pointer;
    position: relative;
    background: linear-gradient(180deg, #221d18 0%, #221d18 24%, #826e5a 24%, #6a5847 100%);
    border: 2px solid #1b1713;
    border-radius: 3px;
    overflow: hidden;
    aspect-ratio: 124 / 166;
    display: flex;
    flex-direction: column;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.22);
  }

  .card-tile:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 12px rgba(0, 0, 0, 0.32);
  }

  .card-tile.selected {
    outline: 3px solid #ffffff;
    box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.85), 0 6px 16px rgba(0, 0, 0, 0.4);
    z-index: 2;
  }

  .card-tile.locked img.full-card-img { filter: saturate(0.75); }

  .lock-ribbon {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 8px;
    margin: 0 auto;
    width: fit-content;
    background: rgba(48, 38, 28, 0.86);
    color: #f3e5c6;
    border: 1px solid #c9a96a;
    border-radius: 3px;
    font-size: 11.5px;
    padding: 1px 7px;
    letter-spacing: 1px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    pointer-events: none;
  }

  .new-badge {
    position: absolute;
    top: 4px;
    left: 50%;
    transform: translateX(-50%);
    background: #c0392b;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    padding: 0 6px;
    border-radius: 8px;
    border: 1px solid #fff2d6;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .lock-banner {
    background: #efe4cf;
    border: 1.5px dashed #a88b5c;
    color: #5a4529;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 13px;
    margin-bottom: 12px;
    line-height: 1.6;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .status-tag {
    display: inline-block;
    font-size: 12px;
    padding: 0 7px;
    border-radius: 3px;
    margin-left: 8px;
    vertical-align: middle;
    font-weight: 600;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }
  .status-tag.locked { background: #d8c9ab; color: #5b4628; border: 1px solid #a88b5c; }
  .status-tag.new { background: #c0392b; color: #fff; }

  .card-tile img.full-card-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .card-tile-fallback {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
  }

  .card-tile-title {
    background: #1f1b16;
    color: #f4ebd8;
    font-size: 13px;
    text-align: center;
    padding: 4px 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    letter-spacing: 0.5px;
  }

  .card-tile-body {
    flex: 1;
    display: grid;
    place-items: center;
    color: #efe3c8;
    font-size: 22px;
    padding: 6px;
  }

  .card-name-caption {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(transparent, rgba(18, 14, 10, 0.85));
    color: #f6eedc;
    font-size: 12px;
    text-align: center;
    padding: 12px 3px 3px;
    opacity: 0;
    transition: opacity 0.15s;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }
  .card-tile:hover .card-name-caption { opacity: 1; }

  .review-dot {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #f0ad1f;
    border: 1.5px solid #231b10;
  }

  .edited-dot {
    position: absolute;
    top: 4px;
    left: 4px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #4caf50;
    border: 1.5px solid #162817;
  }

  /* 右侧详情栏 */
  .detail-pane {
    padding: 22px 26px;
    background: linear-gradient(180deg, rgba(243, 236, 221, 0.55) 0%, rgba(229, 217, 194, 0.55) 100%);
    max-height: 76vh;
    overflow-y: auto;
  }

  .detail-hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 12px;
  }

  .detail-icon {
    max-width: 185px;
    max-height: 165px;
    border-radius: 6px;
    object-fit: contain;
    mix-blend-mode: multiply;
  }

  .detail-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding-bottom: 10px;
    margin-bottom: 14px;
    border-bottom: 2px solid #d5c3a5;
  }

  .detail-title {
    font-size: 26px;
    font-weight: 700;
    color: #fffdf7;
    letter-spacing: 2px;
    text-shadow:
      -1.5px -1.5px 0 #261e16,
       1.5px -1.5px 0 #261e16,
      -1.5px  1.5px 0 #261e16,
       1.5px  1.5px 0 #261e16,
       0 2px 4px rgba(0, 0, 0, 0.35);
  }

  .detail-meta {
    font-size: 12px;
    color: var(--ink-muted);
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .detail-body p {
    font-size: 18px;
    color: var(--ink-body);
    text-indent: 2em;
    margin-bottom: 10px;
    line-height: 1.78;
  }

  .detail-section-title {
    font-size: 19px;
    font-weight: 700;
    color: #43341f;
    margin: 16px 0 8px;
    letter-spacing: 1px;
  }

  .detail-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px dashed var(--border-soft);
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .warn-banner {
    background: var(--warn-bg);
    border: 1px solid var(--warn-border);
    color: #6b4e09;
    padding: 7px 11px;
    border-radius: 4px;
    font-size: 12.5px;
    margin-bottom: 12px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  /* 对照原图校对区 */
  .proofread-box {
    margin-top: 14px;
    padding: 14px;
    background: var(--parchment-light);
    border: 1.5px solid #b59f7e;
    border-radius: 5px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  .proofread-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .proofread-img-wrap {
    border: 1px solid #c5b394;
    border-radius: 4px;
    overflow: auto;
    max-height: 360px;
    background: #e5d8bf;
  }

  .proofread-img-wrap img {
    width: 100%;
    height: auto;
    display: block;
  }

  .proofread-box label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    color: #5b4a34;
    margin-bottom: 4px;
  }

  .proofread-box input,
  .proofread-box textarea {
    width: 100%;
    padding: 8px 10px;
    border: 1.5px solid #ab9778;
    border-radius: 4px;
    background: #fffdf8;
    color: var(--ink);
    font-size: 14px;
    line-height: 1.65;
    font-family: inherit;
    margin-bottom: 10px;
  }

  .proofread-box textarea {
    min-height: 180px;
    resize: vertical;
  }

  /* 视图2：全文列表模式（适合通读与查资料） */
  .list-view {
    padding: 20px 24px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(430px, 1fr));
    gap: 16px;
  }

  .list-card {
    background: var(--parchment-light);
    border: 1.5px solid #bfa989;
    border-radius: 5px;
    padding: 16px 18px;
    display: flex;
    gap: 15px;
    box-shadow: 0 2px 6px rgba(60, 45, 25, 0.08);
  }

  .list-card-thumb {
    width: 78px;
    flex-shrink: 0;
  }

  .list-card-thumb img {
    width: 100%;
    border-radius: 3px;
    border: 1.5px solid #262019;
    display: block;
  }

  .list-card-content {
    flex: 1;
    min-width: 0;
  }

  .list-card-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    border-bottom: 1px solid #d8c8ae;
    padding-bottom: 5px;
    margin-bottom: 8px;
  }

  .list-card-title {
    font-size: 20px;
    font-weight: 700;
    color: #2f2316;
  }

  .list-card-body p {
    font-size: 15.5px;
    color: var(--ink-body);
    margin-bottom: 6px;
    line-height: 1.65;
  }

  .list-card-sec {
    font-size: 15.5px;
    font-weight: 700;
    color: var(--accent-red);
    margin: 8px 0 4px;
  }

  mark {
    background: #f8da6d;
    color: #231a0d;
    padding: 0 2px;
    border-radius: 2px;
  }

  /* 空状态指引 */
  .empty-state {
    padding: 64px 28px;
    text-align: center;
    max-width: 680px;
    margin: 0 auto;
  }

  .empty-state h2 {
    font-size: 26px;
    color: #3a2d1e;
    margin-bottom: 14px;
  }

  .empty-steps {
    text-align: left;
    background: var(--parchment-light);
    border: 1.5px solid var(--border-soft);
    border-radius: 6px;
    padding: 20px 26px;
    margin-top: 20px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 14.5px;
    line-height: 1.9;
  }

  .empty-steps code {
    background: #e5d7be;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: 600;
  }

  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #241e18;
    color: #f8eedb;
    border: 1.5px solid var(--accent-gold);
    padding: 10px 18px;
    border-radius: 5px;
    font-size: 13.5px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    box-shadow: 0 8px 22px rgba(0,0,0,0.45);
    opacity: 0;
    pointer-events: none;
    transform: translateY(10px);
    transition: all 0.2s ease;
    z-index: 999;
  }
  .toast.show { opacity: 1; transform: translateY(0); }

  footer {
    text-align: center;
    color: #8f816d;
    font-size: 12.5px;
    margin-top: 18px;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  }

  @media (max-width: 1080px) {
    .codex-layout { grid-template-columns: 1fr; }
    .card-grid-pane { border-right: none; border-bottom: 2px solid var(--border-soft); max-height: 48vh; }
    .card-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  }
  @media (max-width: 680px) {
    .card-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .list-view { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="app-shell">
  <header class="top-header">
    <div class="brand">
      <div class="brand-seal">图鉴</div>
      <div>
        <h1>卡牌修仙传 · 图鉴攻略</h1>
        <div class="brand-sub" id="headerSub">收录图鉴资料 · 支持全文检索与 GitHub Pages 部署</div>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn active" id="btnViewCodex" onclick="setView('codex')">图鉴视图</button>
      <button class="btn" id="btnViewList" onclick="setView('list')">全文列表</button>
      <button class="btn" id="btnExportMd" onclick="downloadMarkdown()">导出 Markdown</button>
      <button class="btn" id="btnExportJson" onclick="downloadEditedJson()" style="display:none;">下载修正 JSON</button>
    </div>
  </header>

  <nav class="category-tabs" id="categoryTabs"></nav>

  <main class="scroll-frame" id="mainFrame">
    <div class="toolbar" id="toolbar" style="display:none;">
      <div class="search-wrap">
        <input type="text" class="search-input" id="searchInput" placeholder="搜索名称、效果描述、获取途径…" oninput="onSearchInput()">
        <button class="search-clear" id="searchClear" onclick="clearSearch()" title="清空">×</button>
      </div>
      <div class="filter-group" id="filterChips"></div>
      <div class="stats-text" id="statsText"></div>
    </div>
    <div id="contentRoot"></div>
  </main>

  <footer id="footerInfo">卡牌修仙传图鉴攻略 · 生成时间：__GENERATED_AT__</footer>
</div>

<div class="toast" id="toast"></div>

<script id="guide-data" type="application/json">__GUIDE_JSON__</script>
<script>
(function() {
  const PUBLISH_MODE = __PUBLISH_MODE__;
  const rawEl = document.getElementById('guide-data');
  const GUIDE = JSON.parse(rawEl.textContent || '{"categories":[]}');
  const STORAGE_KEY = 'kapai_xiuxian_edits_v1';

  let state = {
    catIdx: 0,
    selectedIndex: 0,
    view: 'codex',
    filter: 'all',
    query: '',
    proofreadOpen: false,
    edits: loadEdits()
  };

  function loadEdits() {
    if (PUBLISH_MODE) return {};
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
    catch (_) { return {}; }
  }

  function saveEdits() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.edits)); } catch (_) {}
  }

  // 应用本地校对记录
  function applySavedEdits() {
    let editCount = 0;
    for (const cat of GUIDE.categories) {
      const catEdits = state.edits[cat.slug] || {};
      for (const item of cat.items) {
        const ed = catEdits[String(item.index)];
        // 只在截图未变化时套用本地校对；卡牌重新抓取（如新获得）后旧校对自动失效
        if (ed && (ed.captured_at || '') === (item.captured_at || '')) {
          item.name = ed.name;
          item.full_text = ed.full_text;
          const parsed = parseFullText(ed.full_text);
          item.intro_paragraphs = parsed.intro_paragraphs;
          item.sections = parsed.sections;
          item.needs_review = false;
          item._edited = true;
          editCount++;
        }
      }
    }
    const btnJson = document.getElementById('btnExportJson');
    if (btnJson) {
      btnJson.style.display = (!PUBLISH_MODE && editCount > 0) ? 'inline-flex' : 'none';
      btnJson.textContent = `下载修正 JSON (${editCount})`;
    }
  }

  function parseFullText(text) {
    const intro = [];
    const sections = [];
    let curSec = null;
    const lines = String(text || '').split(/\r?\n/);
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      const m = line.match(/^【(.+?)】$/);
      if (m) {
        curSec = { title: m[1].trim(), paragraphs: [] };
        sections.push(curSec);
      } else if (curSec) {
        curSec.paragraphs.push(line);
      } else {
        intro.push(line);
      }
    }
    return { intro_paragraphs: intro, sections };
  }

  function formatEditableText(item) {
    const out = [];
    for (const p of (item.intro_paragraphs || [])) {
      if (p.trim()) out.push(p.trim());
    }
    for (const s of (item.sections || [])) {
      if (out.length) out.push('');
      out.push(`【${s.title}】`);
      for (const p of (s.paragraphs || [])) {
        if (p.trim()) out.push(p.trim());
      }
    }
    if (!out.length && item.full_text) return item.full_text;
    return out.join('\n');
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function highlight(str) {
    const safe = escapeHtml(str);
    const q = state.query.trim();
    if (!q) return safe;
    const esc = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return safe.replace(new RegExp(esc, 'gi'), m => `<mark>${m}</mark>`);
  }

  function showToast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.classList.remove('show'), 2300);
  }

  function isNew(cat, it) {
    return !!(it.unlocked_at && cat.last_run_at && it.unlocked_at === cat.last_run_at);
  }

  function getCurrentCat() {
    return GUIDE.categories[state.catIdx] || null;
  }

  function getFilteredItems(cat) {
    if (!cat) return [];
    const q = state.query.trim().toLowerCase();
    return cat.items.filter(it => {
      if (state.filter === 'unlocked' && it.locked) return false;
      if (state.filter === 'locked' && !it.locked) return false;
      if (state.filter === 'review' && !it.needs_review) return false;
      if (state.filter === 'new' && !isNew(cat, it)) return false;
      if (!q) return true;
      const hay = [
        it.name || '',
        it.full_text || '',
        ...(it.intro_paragraphs || []),
        ...((it.sections || []).flatMap(s => [s.title, ...(s.paragraphs || [])]))
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function render() {
    applySavedEdits();
    const cats = GUIDE.categories || [];
    const tabsEl = document.getElementById('categoryTabs');
    const toolbar = document.getElementById('toolbar');
    const root = document.getElementById('contentRoot');

    if (!cats.length) {
      tabsEl.innerHTML = '';
      toolbar.style.display = 'none';
      document.getElementById('btnExportMd').style.display = 'none';
      root.innerHTML = `
        <div class="empty-state">
          <h2>图鉴攻略框架已就绪，等待抓取数据</h2>
          <p style="color:#6d5c45;font-size:17px;">运行自动抓取脚本后，【感悟&amp;心法】及后续所有分类的卡牌图标与完整文案会自动填入此页面。</p>
          <div class="empty-steps">
            <div>1. 首次使用先双击运行 <code>一键安装依赖.bat</code>（自动安装截图与离线中文 OCR 库）。</div>
            <div>2. 打开《卡牌修仙传》（1920×1080 全屏），进入 <code>【图鉴】→【卡牌】→【感悟&amp;心法】</code>。</div>
            <div>3. 双击运行 <code>开始抓取.bat</code>，在 5 秒倒计时内切回游戏画面，等待脚本自动点击、滑动并识别全部资料（按 <code>F9</code> 暂停/继续，<code>F10</code> 随时停止并保存）。</div>
            <div>4. 抓取完成后会自动刷新并打开本页面！未获得的卡牌也会收录并标记 🔒，以后获得了运行 <code>开始抓取.bat</code> → <code>4</code> 即可只补抓这些卡。</div>
          </div>
        </div>`;
      return;
    }

    document.getElementById('btnExportMd').style.display = 'inline-flex';
    toolbar.style.display = 'flex';

    const totalItems = cats.reduce((s, c) => s + c.items.length, 0);
    const totalLocked = cats.reduce((s, c) => s + c.items.filter(x => x.locked).length, 0);
    document.getElementById('headerSub').textContent =
      `已收录 ${cats.length} 个分类 · 共 ${totalItems} 条图鉴资料（已获得 ${totalItems - totalLocked} / 未获得 ${totalLocked}）`;

    tabsEl.innerHTML = cats.map((c, i) => {
      const label = escapeHtml(c.category || c.full_category || `分类${i+1}`);
      return `<button class="cat-tab ${i === state.catIdx ? 'active' : ''}" onclick="selectCat(${i})">${label}<span class="count">(${c.items.length})</span></button>`;
    }).join('');

    const cat = getCurrentCat();
    const filtered = getFilteredItems(cat);
    const reviewCount = cat.items.filter(x => x.needs_review).length;
    const lockedCount = cat.items.filter(x => x.locked).length;
    const newCount = cat.items.filter(x => isNew(cat, x)).length;

    let chipsHtml = `<button class="chip ${state.filter === 'all' ? 'active' : ''}" onclick="setFilter('all')">全部 (${cat.items.length})</button>`;
    if (lockedCount > 0) {
      chipsHtml += `<button class="chip ${state.filter === 'unlocked' ? 'active' : ''}" onclick="setFilter('unlocked')">已获得 (${cat.items.length - lockedCount})</button>`;
      chipsHtml += `<button class="chip ${state.filter === 'locked' ? 'active' : ''}" onclick="setFilter('locked')">🔒 未获得 (${lockedCount})</button>`;
    }
    if (newCount > 0) {
      chipsHtml += `<button class="chip ${state.filter === 'new' ? 'active' : ''}" onclick="setFilter('new')">★ 新获得 (${newCount})</button>`;
    }
    if (!PUBLISH_MODE && reviewCount > 0) {
      chipsHtml += `<button class="chip ${state.filter === 'review' ? 'active' : ''}" onclick="setFilter('review')">建议核对 (${reviewCount})</button>`;
    }
    document.getElementById('filterChips').innerHTML = chipsHtml;
    document.getElementById('statsText').textContent =
      `当前显示 ${filtered.length} / ${cat.items.length} 条`;

    if (!filtered.length) {
      root.innerHTML = `<div class="empty-state"><h2>没有匹配的图鉴条目</h2><p style="color:#6d5c45;">试试更换搜索关键词或切换筛选条件。</p></div>`;
      return;
    }

    if (!filtered.some(x => x.index === state.selectedIndex)) {
      state.selectedIndex = filtered[0].index;
    }

    if (state.view === 'codex') {
      renderCodexView(cat, filtered, root);
    } else {
      renderListView(cat, filtered, root);
    }
  }

  function renderCodexView(cat, filtered, root) {
    const sel = cat.items.find(x => x.index === state.selectedIndex) || filtered[0];
    const cardsHtml = filtered.map(it => {
      const cls = [
        'card-tile',
        it.index === sel.index ? 'selected' : '',
        it.locked ? 'locked' : ''
      ].filter(Boolean).join(' ');
      const title = escapeHtml(it.name || `#${it.index + 1}`);
      const imgHtml = it.card_image
        ? `<img class="full-card-img" src="./${escapeHtml(it.card_image)}" alt="${title}" loading="lazy">`
        : `<div class="card-tile-fallback"><div class="card-tile-title">${title}</div><div class="card-tile-body">${title.slice(0,2)}</div></div>`;
      const revDot = (!PUBLISH_MODE && it.needs_review) ? `<span class="review-dot" title="OCR 置信度略低，建议对照原图核对"></span>` : '';
      const edDot = (!PUBLISH_MODE && it._edited) ? `<span class="edited-dot" title="已手动校对"></span>` : '';
      const lockTag = it.locked ? `<span class="lock-ribbon">🔒 未获得</span>` : '';
      const newTag = isNew(cat, it) ? `<span class="new-badge">新</span>` : '';
      return `<div class="${cls}" onclick="selectItem(${it.index})" title="${title}${it.locked ? '（未获得）' : ''}">${imgHtml}${revDot}${edDot}${lockTag}${newTag}<div class="card-name-caption">${title}</div></div>`;
    }).join('');

    let bodyHtml = '';
    {
      for (const p of (sel.intro_paragraphs || [])) {
        bodyHtml += `<p>${highlight(p)}</p>`;
      }
      for (const sec of (sel.sections || [])) {
        bodyHtml += `<div class="detail-section-title">【${highlight(sec.title)}】</div>`;
        for (const p of (sec.paragraphs || [])) {
          bodyHtml += `<p>${highlight(p)}</p>`;
        }
      }
      if (!bodyHtml && sel.full_text) {
        bodyHtml = sel.full_text.split(/\n+/).map(p => `<p>${highlight(p)}</p>`).join('');
      }
      if (!bodyHtml) {
        bodyHtml = `<p style="color:#8b7b65;">（暂无详细说明）</p>`;
      }
    }
    const lockBanner = sel.locked
      ? `<div class="lock-banner">🔒 <b>尚未获得此卡牌</b>${PUBLISH_MODE ? '：以下为游戏图鉴中可见的部分信息，获得后可查看完整内容。' : '：以下为未获得状态下图鉴中可见的信息。获得后在游戏里打开此分类，运行「开始抓取.bat」→ 选 <b>4 补全未获得卡牌</b>，会自动更新这一条。'}</div>`
      : '';
    const newBanner = isNew(cat, sel)
      ? `<div class="lock-banner" style="border-color:#c0392b;background:#fbe9e4;">★ 本次补全新获得的卡牌（${escapeHtml(sel.unlocked_at || '')}）</div>`
      : '';

    const iconSrc = sel.icon_image || sel.card_image;
    const iconHtml = iconSrc
      ? `<div class="detail-hero"><img class="detail-icon" src="./${escapeHtml(iconSrc)}" alt="${escapeHtml(sel.name)}"></div>`
      : '';

    const warnHtml = (!PUBLISH_MODE && sel.needs_review)
      ? `<div class="warn-banner">提示：此条目有个别字 OCR 置信度低于 96%（或已自动修正楷体形近字），可点击下方「对照原图校对」快速核验。</div>`
      : '';

    let proofHtml = '';
    if (!PUBLISH_MODE && state.proofreadOpen) {
      const detailImg = sel.detail_image
        ? `<label>游戏原图（自动无缝拼接全文）：</label><div class="proofread-img-wrap"><img src="./${escapeHtml(sel.detail_image)}" alt="原图"></div>`
        : '';
      proofHtml = `
        <div class="proofread-box">
          <div class="proofread-grid">
            ${detailImg}
            <div>
              <label>卡牌名称：</label>
              <input type="text" id="editName" value="${escapeHtml(sel.name || '')}">
              <label>正文内容（每行一段，小标题用【获取途径】格式）：</label>
              <textarea id="editBody">${escapeHtml(formatEditableText(sel))}</textarea>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="saveCurrentEdit()">保存本条修改</button>
                <button class="btn btn-light" onclick="downloadEditedJson()">导出修正后的 ${escapeHtml(cat.file_name || 'data.json')}</button>
              </div>
            </div>
          </div>
        </div>`;
    }

    const proofBtn = (!PUBLISH_MODE)
      ? `<button class="btn btn-light" onclick="toggleProofread()">${state.proofreadOpen ? '收起校对' : '对照原图校对'}</button>`
      : '';

    const confText = (!PUBLISH_MODE && sel.avg_confidence)
      ? ` · OCR ${(sel.avg_confidence * 100).toFixed(1)}%`
      : '';

    root.innerHTML = `
      <div class="codex-layout">
        <section class="card-grid-pane">
          <div class="card-grid">${cardsHtml}</div>
        </section>
        <aside class="detail-pane">
          ${iconHtml}
          <div class="detail-title-row">
            <h2 class="detail-title">${highlight(sel.name || '未命名')}${sel.locked ? '<span class="status-tag locked">🔒 未获得</span>' : ''}${isNew(cat, sel) ? '<span class="status-tag new">新获得</span>' : ''}</h2>
            <span class="detail-meta">#${sel.index + 1}${confText}</span>
          </div>
          ${lockBanner}${newBanner}
          ${warnHtml}
          <div class="detail-body">${bodyHtml}</div>
          <div class="detail-toolbar">
            <button class="btn btn-light" onclick="copyItemText(${sel.index})">复制本条文字</button>
            ${proofBtn}
          </div>
          ${proofHtml}
        </aside>
      </div>`;
  }

  function renderListView(cat, filtered, root) {
    const cards = filtered.map(it => {
      const thumb = it.card_image || it.icon_image;
      const thumbHtml = thumb
        ? `<div class="list-card-thumb"><img src="./${escapeHtml(thumb)}" alt="${escapeHtml(it.name)}" loading="lazy"></div>`
        : '';
      let b = '';
      for (const p of (it.intro_paragraphs || [])) b += `<p>${highlight(p)}</p>`;
      for (const s of (it.sections || [])) {
        b += `<div class="list-card-sec">【${highlight(s.title)}】</div>`;
        for (const p of (s.paragraphs || [])) b += `<p>${highlight(p)}</p>`;
      }
      if (!b) b = `<p style="color:#8b7b65;">（暂无详细说明）</p>`;
      return `
        <article class="list-card">
          ${thumbHtml}
          <div class="list-card-content">
            <div class="list-card-header">
              <span class="list-card-title">${highlight(it.name || `#${it.index+1}`)}${it.locked ? '<span class="status-tag locked">🔒 未获得</span>' : ''}${isNew(cat, it) ? '<span class="status-tag new">新获得</span>' : ''}</span>
              <span class="detail-meta" style="cursor:pointer;" onclick="jumpToCodex(${it.index})">#${it.index + 1} 查看详情 →</span>
            </div>
            <div class="list-card-body">${b}</div>
          </div>
        </article>`;
    }).join('');
    root.innerHTML = `<div class="list-view">${cards}</div>`;
  }

  window.selectCat = function(idx) {
    state.catIdx = idx;
    state.selectedIndex = 0;
    state.filter = 'all';
    render();
  };

  window.selectItem = function(idx) {
    state.selectedIndex = idx;
    render();
  };

  window.jumpToCodex = function(idx) {
    state.selectedIndex = idx;
    setView('codex');
  };

  window.setView = function(v) {
    state.view = v;
    document.getElementById('btnViewCodex').classList.toggle('active', v === 'codex');
    document.getElementById('btnViewList').classList.toggle('active', v === 'list');
    render();
  };

  window.setFilter = function(f) {
    state.filter = f;
    render();
  };

  window.onSearchInput = function() {
    const val = document.getElementById('searchInput').value;
    state.query = val;
    document.getElementById('searchClear').style.display = val ? 'block' : 'none';
    render();
  };

  window.clearSearch = function() {
    document.getElementById('searchInput').value = '';
    state.query = '';
    document.getElementById('searchClear').style.display = 'none';
    render();
  };

  window.toggleProofread = function() {
    state.proofreadOpen = !state.proofreadOpen;
    render();
  };

  window.saveCurrentEdit = function() {
    const cat = getCurrentCat();
    if (!cat) return;
    const name = document.getElementById('editName').value.trim();
    const body = document.getElementById('editBody').value.trim();
    if (!state.edits[cat.slug]) state.edits[cat.slug] = {};
    const curItem = cat.items.find(x => x.index === state.selectedIndex) || {};
    state.edits[cat.slug][String(state.selectedIndex)] = { name, full_text: body, captured_at: curItem.captured_at || '' };
    saveEdits();
    render();
    showToast(`已保存「${name}」的校对内容（可点击右上角导出修正 JSON）`);
  };

  window.copyItemText = function(idx) {
    const cat = getCurrentCat();
    const it = cat && cat.items.find(x => x.index === idx);
    if (!it) return;
    const text = `【${it.name}】\n${formatEditableText(it)}`;
    navigator.clipboard.writeText(text).then(
      () => showToast(`已复制「${it.name}」的完整文字`),
      () => showToast('复制失败，请手动选中复制')
    );
  };

  function triggerDownload(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.downloadEditedJson = function() {
    const cat = getCurrentCat();
    if (!cat) return;
    applySavedEdits();
    const clean = JSON.parse(JSON.stringify(cat));
    for (const it of clean.items) delete it._edited;
    triggerDownload(
      cat.file_name || `${cat.slug}.json`,
      JSON.stringify(clean, null, 2),
      'application/json;charset=utf-8'
    );
    showToast(`已导出 ${cat.file_name}，放入 docs/data/ 后运行「重新生成HTML攻略.bat」即可永久生效`);
  };

  window.downloadMarkdown = function() {
    const cat = getCurrentCat();
    if (!cat) return;
    const lines = [`# 【卡牌修仙传】图鉴攻略 — ${cat.full_category || cat.category}`, ''];
    for (const it of cat.items) {
      lines.push(`## ${it.index + 1}. ${it.name}${it.locked ? '（🔒 未获得）' : ''}`, '');
      if (it.locked) lines.push('> 尚未获得此卡牌，以下为图鉴中可见的部分信息。', '');
      for (const p of (it.intro_paragraphs || [])) lines.push(p, '');
      for (const s of (it.sections || [])) {
        lines.push(`### 【${s.title}】`, '');
        for (const p of (s.paragraphs || [])) lines.push(p, '');
      }
      lines.push('---', '');
    }
    triggerDownload(`${cat.slug || 'guide'}.md`, lines.join('\n'), 'text/markdown;charset=utf-8');
    showToast('已导出 Markdown 攻略文件');
  };

  // 支持键盘左右方向键快速翻看卡牌
  document.addEventListener('keydown', function(e) {
    if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
    if (state.view !== 'codex') return;
    const cat = getCurrentCat();
    if (!cat) return;
    const filtered = getFilteredItems(cat);
    const pos = filtered.findIndex(x => x.index === state.selectedIndex);
    if (pos < 0) return;
    if (e.key === 'ArrowRight' && pos + 1 < filtered.length) {
      state.selectedIndex = filtered[pos + 1].index;
      render();
    } else if (e.key === 'ArrowLeft' && pos > 0) {
      state.selectedIndex = filtered[pos - 1].index;
      render();
    }
  });

  render();
})();
</script>
</body>
</html>
"""


def build_site(publish_mode: bool = False) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 添加 .nojekyll，方便直接部署到 GitHub Pages
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    categories = load_categories(DATA_DIR)
    write_markdown_files(categories)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    manifest = {
        "title": "卡牌修仙传 · 图鉴攻略",
        "generated_at": now_str,
        "categories": [
            {
                "slug": c.get("slug"),
                "category": c.get("category"),
                "full_category": c.get("full_category"),
                "file_name": c.get("file_name"),
                "count": len(c.get("items", [])),
            }
            for c in categories
        ],
    }
    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    guide_payload = {"generated_at": now_str, "categories": categories}
    # 防止 </script> 意外截断 HTML 内联 JSON
    safe_json = json.dumps(guide_payload, ensure_ascii=False).replace("</", "<\\/")

    html = (
        HTML_TEMPLATE.replace("__GENERATED_AT__", now_str)
        .replace("__PUBLISH_MODE__", "true" if publish_mode else "false")
        .replace("__GUIDE_JSON__", safe_json)
    )
    index_path = DOCS_DIR / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser(description="生成【卡牌修仙传】图鉴攻略 HTML 与 Markdown")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="发布模式（隐藏本地 OCR 校对工具栏，适合最终上传 GitHub Pages）",
    )
    args = parser.parse_args()
    out = build_site(publish_mode=args.publish)
    cats = load_categories(DATA_DIR)
    total = sum(len(c.get("items", [])) for c in cats)
    print(f"[完成] 已生成攻略网页：{out}")
    print(f"       当前共包含 {len(cats)} 个分类、{total} 条图鉴资料。")
    if cats:
        print(f"       Markdown 文档目录：{MD_DIR}")


if __name__ == "__main__":
    main()
