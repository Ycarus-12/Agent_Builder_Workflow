"""Shared Posit-themed UI bits for the Shiny apps (no extra build deps).

Hand-crafted CSS matching the Posit Design System palette + Open Sans / Source
Code Pro (Bunny fonts), so we avoid the brand_yml/libsass build dependency.
"""

from __future__ import annotations

from shiny import ui

_CSS = """
:root{
  --posit-blue:#447099; --posit-orange:#ee6331; --posit-teal:#419599;
  --posit-green:#729943; --posit-burgundy:#9a4665; --ink:#151515; --muted:#6a6a6e;
  --line:#e6e8eb; --canvas:#f6f7f9; --card:#ffffff;
}
body{font-family:'Open Sans',system-ui,sans-serif;color:var(--ink);background:var(--canvas);}
.app-header{background:var(--posit-blue);color:#fff;padding:.8rem 1.3rem;display:flex;
  align-items:center;gap:.6rem;box-shadow:0 1px 3px rgba(0,0,0,.14);}
.app-header .dot{width:11px;height:11px;border-radius:50%;background:var(--posit-orange);display:inline-block;}
.app-header .title{font-weight:700;letter-spacing:.2px;}
.app-header .sub{margin-left:auto;color:#cfe0ee;font-size:.85rem;}
.wrap{max-width:860px;margin:1.6rem auto;padding:0 1rem;}
h1{font-weight:300;font-size:1.8rem;letter-spacing:-.2px;margin:.2rem 0 .5rem;}
h2{font-weight:600;font-size:1.15rem;margin:1.2rem 0 .5rem;}
h3{font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  box-shadow:0 1px 2px rgba(21,21,21,.04),0 6px 18px rgba(21,21,21,.05);padding:1.3rem 1.4rem;margin:1rem 0;}
.btn-primary{background:var(--posit-blue);border-color:var(--posit-blue);font-weight:600;border-radius:8px;}
.btn-primary:hover{filter:brightness(.94);}
.btn-outline-secondary{border-radius:8px;}
label{font-weight:600;font-size:.9rem;}
.form-control,.selectize-input,textarea{border-radius:8px!important;}
.bubble{padding:.55rem .85rem;border-radius:14px;margin:.4rem 0;max-width:80%;line-height:1.45;}
.bubble .who{display:block;font-size:.72rem;opacity:.75;margin-bottom:.12rem;}
.bubble.requestor{background:var(--posit-blue);color:#fff;margin-left:auto;border-bottom-right-radius:4px;}
.bubble.agent{background:#eef0f3;color:var(--ink);border-bottom-left-radius:4px;}
.pill{display:inline-block;padding:.13rem .6rem;border-radius:999px;font-size:.78rem;font-weight:600;
  background:#eef3f8;color:var(--posit-blue);}
.pill.awaiting_gate,.pill.awaiting_build_input{background:#fdecd9;color:#b1480f;}
.pill.awaiting_security_adjudication,.pill.awaiting_rnd_signoff,.pill.security_review{background:#f4e2e9;color:var(--posit-burgundy);}
.pill.running{background:#e3f0f0;color:var(--posit-teal);}
.pill.done,.pill.terminal{background:#e6efda;color:#4d6a1f;}
.muted{color:var(--muted);}
.urlbox{font-family:'Source Code Pro',ui-monospace,monospace;background:#f1f4f7;border:1px solid var(--line);
  border-radius:8px;padding:.55rem .7rem;font-size:.85rem;word-break:break-all;color:#2b2b2b;}
.errbox{color:#9a4665;background:#faf0f3;border:1px solid #e6c3cf;padding:.55rem .7rem;border-radius:8px;font-size:.85rem;}
pre{font-family:'Source Code Pro',ui-monospace,monospace;background:#fbfbfc;border:1px solid var(--line);
  padding:.7rem;border-radius:8px;font-size:.82rem;overflow-x:auto;}
"""


def head() -> ui.Tag:
    return ui.tags.head(
        ui.tags.link(rel="preconnect", href="https://fonts.bunny.net"),
        ui.tags.link(rel="stylesheet",
                     href="https://fonts.bunny.net/css?family=open-sans:300,400,600,700|source-code-pro:400,600"),
        ui.tags.style(_CSS),
    )


def header(subtitle: str) -> ui.Tag:
    return ui.div(
        ui.span(class_="dot"),
        ui.span("Tool-Request Workflow", class_="title"),
        ui.span(subtitle, class_="sub"),
        class_="app-header",
    )
