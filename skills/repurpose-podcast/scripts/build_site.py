#!/usr/bin/env python3
"""Build a switchable local podcast library from one or more project JSON files."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path


LIBRARY_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__LIBRARY_TITLE__</title>
<style>
:root{--ink:#17191c;--muted:#73726d;--paper:#eeeae1;--panel:#fffdf8;--accent:#df3a2f;--line:#d8d1c6}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"PingFang SC",system-ui,sans-serif}.app{min-height:100vh;display:grid;grid-template-columns:340px minmax(0,1fr)}aside{height:100vh;overflow:auto;padding:30px 24px;border-right:1px solid var(--line);background:#f5f1e8}.brand{font:800 24px Georgia,serif}.brand b{color:var(--accent)}.repo-link{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:14px 0 28px;padding:11px 13px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.62);color:var(--ink);font-size:13px;font-weight:750;text-decoration:none;transition:background .18s,border-color .18s,transform .18s}.repo-link:hover{background:#fff;border-color:#aaa096;transform:translateY(-1px)}.repo-link span:last-child{color:var(--accent);font-size:16px}label{display:block;font-size:12px;font-weight:800;letter-spacing:.14em;color:var(--muted);margin-bottom:8px}select{width:100%;padding:12px;border:1px solid var(--line);border-radius:10px;background:#fff;font:inherit}.episodes{display:grid;gap:10px;margin-top:20px}.episode{width:100%;padding:14px;display:grid;grid-template-columns:58px 1fr;gap:12px;text-align:left;border:1px solid transparent;border-radius:12px;background:transparent;color:inherit;cursor:pointer}.episode:hover,.episode.active{background:#fff;border-color:var(--line)}.thumb{width:58px;height:58px;border-radius:8px;background:#1c1d20;color:#fff;display:grid;place-items:center;overflow:hidden;font:700 18px Georgia}.thumb img{width:100%;height:100%;object-fit:cover}.episode strong{display:block;line-height:1.35}.episode small{display:block;color:var(--muted);margin-top:6px}.stage{height:100vh;padding:14px}.stage iframe{display:block;width:100%;height:100%;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 20px 70px rgba(42,35,27,.1)}@media(max-width:820px){.app{grid-template-columns:1fr}aside{height:auto;border-right:0;border-bottom:1px solid var(--line)}.episodes{display:none}.stage{height:calc(100vh - 244px);padding:8px}}
</style>
</head>
<body><div class="app"><aside><div class="brand">Penny<b>Scribe</b> Library</div><a class="repo-link" href="https://github.com/YeDaxia/pennyscribe-skills/tree/main/skills/repurpose-podcast" target="_blank" rel="noreferrer"><span>在 GitHub 获取 Skill</span><span aria-hidden="true">↗</span></a><label for="episodeSelect">切换播客</label><select id="episodeSelect"></select><div class="episodes" id="episodes"></div></aside><main class="stage"><iframe id="studio" title="Podcast publishing workspace"></iframe></main></div>
<script id="library-data" type="application/json">__LIBRARY_DATA__</script>
<script>
const items=JSON.parse(document.getElementById('library-data').textContent),select=document.getElementById('episodeSelect'),list=document.getElementById('episodes'),frame=document.getElementById('studio');
function thumb(item){const box=document.createElement('span');box.className='thumb';if(item.cover){const image=document.createElement('img');image.src=item.cover;image.alt='';box.appendChild(image)}else box.textContent='PS';return box}
function show(index){const item=items[index];if(!item)return;select.value=String(index);frame.src=item.file;document.querySelectorAll('.episode').forEach((button,i)=>button.classList.toggle('active',i===index));document.title=`${item.title} · PennyScribe Library`}
items.forEach((item,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=item.title;select.appendChild(option);const button=document.createElement('button');button.className='episode';button.type='button';button.appendChild(thumb(item));const copy=document.createElement('span');const title=document.createElement('strong');title.textContent=item.title;const meta=document.createElement('small');meta.textContent=[item.creator,item.platform].filter(Boolean).join(' · ');copy.append(title,meta);button.appendChild(copy);button.onclick=()=>show(index);list.appendChild(button)});select.onchange=()=>show(Number(select.value));show(0);
</script></body></html>"""


def episode_slug(project: dict) -> str:
    source = project.get("source") or {}
    platform = re.sub(r"[^a-z0-9]+", "-", str(source.get("platform") or "episode").lower()).strip("-") or "episode"
    identity = str(source.get("url") or source.get("title") or json.dumps(source, ensure_ascii=False, sort_keys=True))
    return f"{platform}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"


def write_workspace(project: dict, output: Path, template: str) -> None:
    payload = json.dumps(project, ensure_ascii=False).replace("</", "<\\/")
    output.write_text(template.replace("__PROJECT_DATA__", payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", help="One or more repurpose-podcast project JSON files")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--title", default="我的播客资料库")
    args = parser.parse_args()

    output = Path(args.output_dir).expanduser().resolve()
    episodes = output / "episodes"
    episodes.mkdir(parents=True, exist_ok=True)
    workspace_template = (Path(__file__).resolve().parent.parent / "assets" / "workspace.html").read_text(encoding="utf-8")
    manifest: list[dict[str, object]] = []
    seen: set[str] = set()

    for value in args.projects:
        project_path = Path(value).expanduser().resolve()
        project = json.loads(project_path.read_text(encoding="utf-8"))
        slug = episode_slug(project)
        if slug in seen:
            continue
        seen.add(slug)
        target = episodes / f"{slug}.html"
        write_workspace(project, target, workspace_template)
        source = project.get("source") or {}
        manifest.append({
            "id": slug,
            "title": source.get("title") or "Untitled episode",
            "creator": source.get("creator"),
            "platform": source.get("platform"),
            "cover": source.get("cover"),
            "file": f"episodes/{target.name}",
        })

    if not manifest:
        parser.error("no projects were loaded")
    payload = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    index = LIBRARY_TEMPLATE.replace("__LIBRARY_TITLE__", html.escape(args.title)).replace("__LIBRARY_DATA__", payload)
    (output / "index.html").write_text(index, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"site": str(output / "index.html"), "episodes": len(manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
