# Design Portfolio — Md Shahidul Islam Sabbir

Interface, systems and encounter design, built and shipped inside a live multiplayer game.

A single-page portfolio collecting ten projects across four disciplines: interface and
information design, encounter and time-based design, spatial design, and web design and
development. Every project in it is commercially available and currently running.

## Contents

| | |
|---|---|
| `index.html` | The portfolio. One self-contained page — no build step, no dependencies. |
| `images/` | Screenshots and captures used by the page. |
| `studio.py` | A small local tool for adding images to the page (see below). |

## Viewing it

Open `index.html` in any browser, or serve the folder over HTTP:

```bash
python -m http.server 8777
```

Videos are click-to-play posters. Served over HTTP they expand into an inline player;
opened directly off disk they open on YouTube instead, because YouTube refuses to embed
on a `file://` origin.

## Editing it

`studio.py` serves the folder and lets images be dropped straight onto the page.

```bash
python studio.py
```

Open <http://127.0.0.1:8777/>, then drag an image onto any dashed placeholder, or click one
to browse. The file is copied into `images/` and `index.html` is rewritten on disk so the
placeholder becomes a real figure. Shift-click a placed image to undo it.

Studio mode only activates when the page is served by `studio.py` from this machine. Opened
any other way — from disk, or from a live host — it is an ordinary static page with no
editing UI and no upload code running.

## Built with

Plain HTML and CSS, no framework. Python standard library only for the editing tool.

## Elsewhere

- [Codefling](https://codefling.com/iftebinjan) — 36 published products
- [Fiverr](https://www.fiverr.com/users/iftebinjan/portfolio) — 279 delivered commissions
