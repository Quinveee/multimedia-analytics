"""KG Grounding Studio — Dash port of the design mockup.

Run:  cd app && python -m src.studio   (→ http://127.0.0.1:8050)

Renders against the live ``run_pipeline`` when the KG / Spotlight / LLM are
reachable, and falls back to canned demo data otherwise (see studio_data).
"""

from urllib.parse import quote

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html, no_update
from flask import send_from_directory

from src import config
from src import studio_data as data

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], title="KG Grounding Studio",
           suppress_callback_exceptions=True)
server = app.server

# serve KG node thumbnails (offline/data/images/*) for the live pipeline.
# Must be absolute: Flask's send_from_directory resolves a relative dir against
# the app root_path (app/src), not the CWD.
_IMAGES_ROOT = config.KG_PATH.parent.resolve()


@server.route("/kg-images/<path:fname>")
def _kg_image(fname):
    return send_from_directory(_IMAGES_ROOT, fname)


# ── tiny SVG icon helper (dash-html has no <svg>, so inline as data-URI img) ────
def icon(path_svg: str, size=16, stroke="#868e96", width=2, fill="none", style=None):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
           f'viewBox="0 0 24 24" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
           f'stroke-linecap="round" stroke-linejoin="round">{path_svg}</svg>')
    st = {"display": "block", "flex": "0 0 auto"}
    if style:
        st.update(style)
    return html.Img(src="data:image/svg+xml;utf8," + quote(svg), style=st)


GRAPH_GLYPH = ('<circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/>'
               '<circle cx="12" cy="18" r="2.2"/><path d="M6.6 7.4 10.5 16M17.4 7.4 13.5 16M7 6h10"/>')
SEARCH_GLYPH = '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>'
BACK_GLYPH = '<path d="M19 12H5M11 6l-6 6 6 6"/>'
CHECK_GLYPH = '<path d="m5 12 5 5L20 7"/>'
WARN_GLYPH = '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
LINK_GLYPH = ('<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/>'
              '<path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>')
FIT_GLYPH = '<path d="M3 8V5a2 2 0 0 1 2-2h3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M21 16v3a2 2 0 0 1-2 2h-3"/>'
CHEV_GLYPH = '<path d="M9 6l6 6-6 6"/>'
ARROW_GLYPH = '<path d="M5 12h13M13 6l6 6-6 6"/>'

# verification label → visual style (3-color: supported / inferred / unverifiable)
LABEL_STYLE = {
    "supported":    {"color": "#0ca678", "bg": "#ffffff", "border": "#eef0f2",
                     "under": "#63e6be", "chip": "#0ca678", "chipbg": "#e6fcf5", "tag": None},
    "inferred":     {"color": "#f08c00", "bg": "#fffaf0", "border": "#ffe8b3",
                     "under": "#ffd43b", "chip": "#e8590c", "chipbg": "#fff3bf", "tag": "inferred"},
    "unverifiable": {"color": "#e03131", "bg": "#fff6f5", "border": "#ffd9d4",
                     "under": "#ffa8a8", "chip": "#e03131", "chipbg": "#ffe3e0", "tag": "unsupported"},
}


def _lstyle(label):
    return LABEL_STYLE.get(label, LABEL_STYLE["unverifiable"])


def label_icon(label, size=15):
    st = _lstyle(label)
    glyph, width = (CHECK_GLYPH, 2.6) if label == "supported" else (WARN_GLYPH, 2)
    return icon(glyph, size, st["color"], width)

# ── node thumbnail (SVG data-URI) ──────────────────────────────────────────────
def thumb(node, size=64):
    glyph = node.get("glyph", "?")
    fs = size * (.3 if len(glyph) > 2 else .4)
    if not node.get("has_image"):
        # clean "no photo" tile: soft neutral gradient + the entity's initials,
        # tinted faintly by its kind colour (signals the type without a photo).
        tint = data.NODE_BORDER.get(node.get("kind"), "#868e96")
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
               f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
               f'<stop offset="0" stop-color="#f5f7f9"/><stop offset="1" stop-color="#e4e8ec"/></linearGradient></defs>'
               f'<rect width="{size}" height="{size}" rx="10" fill="url(#g)"/>'
               f'<text x="50%" y="54%" font-family="Open Sans,sans-serif" font-size="{fs}" font-weight="800" '
               f'fill="{tint}" fill-opacity=".55" text-anchor="middle" dominant-baseline="middle">{glyph}</text></svg>')
        return "data:image/svg+xml;utf8," + quote(svg)
    a, b = data.KIND_COLORS.get(node.get("kind"), data.KIND_COLORS["concept"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
           f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
           f'<rect width="{size}" height="{size}" rx="10" fill="url(#g)"/>'
           f'<text x="50%" y="54%" font-family="Open Sans,sans-serif" font-size="{fs}" font-weight="800" '
           f'fill="#fff" text-anchor="middle" dominant-baseline="middle" opacity=".95">{glyph}</text></svg>')
    return "data:image/svg+xml;utf8," + quote(svg)


def node_img_src(node):
    if node.get("has_image") and node.get("image"):
        return "/kg-images/" + node["image"]
    return thumb(node)


# ── cytoscape elements / stylesheet ────────────────────────────────────────────
CYTO_STYLESHEET = [
    {"selector": "node", "style": {
        "background-image": "data(img)", "background-fit": "cover", "background-color": "#fff",
        "border-width": 2.5, "border-color": "data(col)", "label": "data(label)",
        "font-family": "Open Sans, sans-serif", "font-size": 9.5, "font-weight": 600, "color": "#495057",
        "text-valign": "bottom", "text-margin-y": 5, "text-max-width": 86, "text-wrap": "wrap",
        "width": 44, "height": 44, "overlay-opacity": 0}},
    {"selector": "node.big", "style": {"width": 62, "height": 62, "border-width": 3.5,
                                       "font-size": 11, "font-weight": 800, "color": "#212529"}},
    {"selector": "node[gap = 1]", "style": {"border-style": "dashed", "border-color": "#ced4da", "border-width": 2}},
    {"selector": "edge", "style": {
        "width": 1.5, "line-color": "#dee2e6", "curve-style": "bezier", "label": "data(label)",
        "font-family": "Open Sans, sans-serif", "font-size": 8, "color": "#adb5bd",
        "text-background-color": "#fff", "text-background-opacity": .85, "text-background-padding": 2}},
    {"selector": ".sel-node", "style": {"border-color": "#228be6", "border-width": 4.5}},
    {"selector": ".hi-edge", "style": {"line-color": "#f59f00", "width": 3.4, "color": "#e8590c",
                                       "font-weight": 700, "text-background-opacity": 1, "z-index": 9}},
    {"selector": ".dim", "style": {"opacity": .22}},
]


def graph_meta(vm, only_used):
    if only_used:
        ue, un = used_keys(vm)
        return f"{len(un)} entities · {len(ue)} relations used"
    return f"{vm['counts']['entities']} entities · {len(vm['edges'])} relations"


def used_keys(vm):
    """Edges + nodes that actually back the answer (union of cited triples)."""
    edges, nodes = set(), set()
    for cit in (vm.get("citations") or {}).values():
        for pair in cit.get("edges", []):
            edges.add(frozenset(pair))
            nodes.update(pair)
        for k in ("node", "node2"):
            if cit.get(k):
                nodes.add(cit[k])
    return edges, nodes


def build_elements(vm, selected=None, hi_edges=None, only_used=False):
    """selected: node id(s) to mark sel-node. hi_edges: (source, target) pairs to light up.
    only_used: keep only the relations (and their nodes) that backed the answer."""
    sel = ({selected} if isinstance(selected, str) else set(selected)) if selected else set()
    hi = {frozenset(p) for p in (hi_edges or [])}
    u_edges, u_nodes = used_keys(vm) if only_used else (None, None)
    els = []
    for n in vm["nodes"]:
        if only_used and n["id"] not in u_nodes:
            continue
        classes = []
        if n.get("big"):
            classes.append("big")
        if n["id"] in sel:
            classes.append("sel-node")
        d = {"data": {"id": n["id"], "label": n["label"], "img": node_img_src(n),
                      "col": data.NODE_BORDER.get(n.get("kind"), "#868e96"),
                      "gap": 0 if n.get("has_image") else 1},
             "classes": " ".join(classes)}
        if vm.get("source") == "mock" and "x" in n:
            d["position"] = {"x": n["x"], "y": n["y"]}
        els.append(d)
    for i, e in enumerate(vm["edges"]):
        key = frozenset((e["source"], e["target"]))
        if only_used and key not in u_edges:
            continue
        cls = "hi-edge" if key in hi else ""
        els.append({"data": {"id": f"e{i}", "source": e["source"], "target": e["target"], "label": e["label"]},
                    "classes": cls})
    return els


# ── render helpers ─────────────────────────────────────────────────────────────
def step_icon(state):
    if state == "done":
        return html.Span(icon(CHECK_GLYPH, 10, "#fff", 3.2), style={
            "display": "inline-flex", "width": "16px", "height": "16px", "borderRadius": "50%",
            "background": "#37b24d", "alignItems": "center", "justifyContent": "center", "flex": "0 0 auto"})
    if state == "active":
        return html.Span(className="gl-spin gl-spin-lg", style={"flex": "0 0 auto"})
    return html.Span(style={"display": "inline-block", "width": "16px", "height": "16px",
                            "border": "2px solid #dee2e6", "borderRadius": "50%", "flex": "0 0 auto"})


def link_chip(c):
    return html.Span([c["label"], " ", html.Span(c["qid"], className="mono",
                     style={"fontSize": "9px", "color": "#74a9d8", "fontWeight": 500})],
                     className="gl-pop", style={
        "display": "inline-flex", "alignItems": "center", "gap": "6px", "background": "#e7f5ff",
        "border": "1px solid #d0ebff", "borderRadius": "7px", "padding": "2px 8px",
        "fontSize": "10.5px", "color": "#1971c2", "fontWeight": 600, "margin": "4px 5px 0 0"})


def retrieved_chip(vm, nid):
    node = next((n for n in vm["nodes"] if n["id"] == nid), {"label": nid, "kind": "concept", "has_image": True})
    col = data.NODE_BORDER.get(node.get("kind"), "#868e96")
    dot_style = ({"background": col} if node.get("has_image")
                 else {"background": "transparent", "border": "1.5px dashed #fa5252"})
    return html.Span([html.Span(style={"width": "8px", "height": "8px", "borderRadius": "3px", **dot_style}),
                      node["label"]], className="gl-pop", style={
        "display": "inline-flex", "alignItems": "center", "gap": "6px", "background": "#fff",
        "border": "1px solid #e9ecef", "borderRadius": "7px", "padding": "2px 8px 2px 6px",
        "fontSize": "10.5px", "color": "#495057", "margin": "4px 5px 0 0"})


def trace_running(vm, link_state, retr_state, ground_state):
    chips_link = [link_chip(c) for c in vm["link_chips"]] if link_state in ("active", "done") else []
    n_retr = len([n for n in vm["retrieved"]]) if retr_state in ("active", "done") else 0
    chips_retr = [retrieved_chip(vm, nid) for nid in vm["retrieved"]] if retr_state in ("active", "done") else []
    total = len(vm["retrieved"])
    return html.Div([
        html.Div("Grounding pipeline", style={"fontSize": "10px", "fontWeight": 700, "letterSpacing": ".5px",
                 "textTransform": "uppercase", "color": "#adb5bd", "marginBottom": "6px"}),
        _trace_row(step_icon(link_state), "Entity linking", "· question spans → KG ids",
                   html.Div(chips_link, style={"display": "flex", "flexWrap": "wrap"})),
        _trace_row(step_icon(retr_state), "Subgraph retrieval", f"· {n_retr} / {total}",
                   html.Div(chips_retr, style={"display": "flex", "flexWrap": "wrap"})),
        _trace_row(step_icon(ground_state), "Grounding answer", "· LLM conditioned on retrieved triples", None),
    ], style={"background": "#f8f9fb", "border": "1px solid #eef0f2", "borderRadius": "12px", "padding": "11px 13px"})


def _trace_row(ic, title, sub, body):
    head = [html.Span(title, style={"fontSize": "12.5px", "fontWeight": 600, "color": "#495057"}),
            html.Span(" " + sub, style={"fontWeight": 400, "color": "#adb5bd", "fontSize": "11px"})]
    inner = [html.Div(head)]
    if body is not None:
        inner.append(body)
    return html.Div([html.Span(ic, style={"flex": "0 0 auto", "marginTop": "1px"}),
                     html.Div(inner, style={"flex": "1", "minWidth": 0})],
                    style={"display": "flex", "alignItems": "flex-start", "gap": "10px", "padding": "4px 0"})


def trace_initial():
    """Pipeline trace shown the instant the button is pressed, before data exists."""
    return html.Div([
        html.Div("Grounding pipeline", style={"fontSize": "10px", "fontWeight": 700, "letterSpacing": ".5px",
                 "textTransform": "uppercase", "color": "#adb5bd", "marginBottom": "6px"}),
        _trace_row(step_icon("active"), "Entity linking", "· linking question to the knowledge graph", None),
        _trace_row(step_icon("pending"), "Subgraph retrieval", "· searching for supporting facts", None),
        _trace_row(step_icon("pending"), "Grounding answer", "· LLM conditioned on retrieved triples", None),
    ], style={"background": "#f8f9fb", "border": "1px solid #eef0f2", "borderRadius": "12px", "padding": "11px 13px"})


def render_no_grounding(vm):
    """Shown when retrieval returned no triples — a grounded answer isn't possible."""
    linked = vm.get("link_chips") or []
    if linked:
        names = ", ".join(c["label"] for c in linked)
        detail = (f"The question was linked to {names}, but the knowledge graph holds no "
                  f"supporting facts (triples) for them — so the answer cannot be grounded in evidence.")
    else:
        detail = ("No entities from your question were found in the knowledge graph, so there are "
                  "no facts to ground an answer in.")
    return html.Div([
        html.Div([
            icon(WARN_GLYPH, 18, "#e8590c", 2, style={"display": "inline-block"}),
            html.Span("No grounded answer available", style={"fontSize": "15px", "fontWeight": 700, "color": "#e8590c"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "9px", "marginBottom": "8px"}),
        html.P(detail, style={"fontSize": "14px", "lineHeight": "1.6", "color": "#495057", "margin": "0 0 6px"}),
        html.P("Switch to “Closed-book vs grounded” to see the model’s unverified answer.",
               style={"fontSize": "12.5px", "color": "#868e96", "margin": 0}),
    ], style={"border": "1px solid #ffd9a8", "background": "#fff8f0", "borderRadius": "12px", "padding": "16px 18px"})


def trace_summary(vm):
    if not vm.get("has_triples"):
        return html.Div([
            icon(WARN_GLYPH, 15, "#e8590c", 2, style={"display": "inline-block"}),
            html.Span([f"Linked {vm['counts']['mentions']} mentions · ",
                       html.B("no supporting facts retrieved")]),
        ], style={"display": "inline-flex", "alignItems": "center", "gap": "8px", "background": "#fff8f0",
                  "border": "1px solid #ffd9a8", "borderRadius": "20px", "padding": "6px 13px",
                  "fontSize": "11.5px", "color": "#b85309"})
    c = vm["counts"]
    return html.Button([
        html.Span(icon(CHECK_GLYPH, 10, "#fff", 3.2), style={
            "display": "inline-flex", "width": "16px", "height": "16px", "borderRadius": "50%",
            "background": "#37b24d", "alignItems": "center", "justifyContent": "center"}),
        html.Span([f"Retrieved {c['entities']} entities · linked {c['mentions']} mentions · grounded {c['claims']} claims"]),
        html.Span(["view graph ", icon(CHEV_GLYPH, 11, "#1971c2", 2.4, style={"display": "inline-block"})],
                  style={"display": "inline-flex", "alignItems": "center", "gap": "4px", "color": "#1971c2",
                         "fontWeight": 600, "background": "#fff", "borderRadius": "14px", "padding": "2px 9px"}),
    ], id="gl-trace-pill", n_clicks=0, className="gl-chip", style={
        "display": "inline-flex", "alignItems": "center", "gap": "9px", "background": "#f1f3f5",
        "border": "1px solid #eef0f2", "borderRadius": "20px", "padding": "6px 8px 6px 11px",
        "fontSize": "11.5px", "color": "#495057", "cursor": "pointer"})


def render_answer(vm):
    children = []
    popovers = []
    claim_no = 0
    for tk in vm["tokens"]:
        cids = tk.get("cites")
        if not cids:
            children.append(tk["t"])
            continue
        # A sentence may draw on several facts. Instead of a pile of loose
        # superscripts, the claim text is underlined once and the citations are
        # gathered into a single tinted "evidence cluster" pill — the graph glyph
        # plus one clickable [T#] per fact. Hovering it shows one combined card
        # listing every fact the claim is built on.
        claim_no += 1
        st = _lstyle(vm["citations"].get(cids[0], {}).get("label", "supported"))
        cluster_id = f"gl-ev{claim_no}"
        cluster = _evidence_cluster(vm, cids, st, cluster_id)
        # keep the pill glued to the claim's last word so it never orphans onto a
        # line of its own — the head wraps freely, "last word + pill" stay together.
        us = {"borderBottomColor": st["under"]}
        head, _, last = tk["t"].rpartition(" ")
        if head:
            inner = [html.Span(head + " ", className="gl-claim", style=us),
                     html.Span([html.Span(last, className="gl-claim", style=us), cluster],
                               style={"whiteSpace": "nowrap"})]
        else:
            inner = [html.Span([html.Span(tk["t"], className="gl-claim", style=us), cluster],
                               style={"whiteSpace": "nowrap"})]
        children.append(html.Span(inner, className="gl-rise"))
        popovers.append(dbc.Popover(_evidence_card(vm, cids), target=cluster_id, trigger="hover focus",
                                    placement="bottom", style={"maxWidth": "324px"}))
    answer = html.Div(children, id="gl-answer", style={"fontSize": "16.5px", "lineHeight": "1.9", "color": "#343a40"})
    return html.Div([answer, *popovers])


def _evidence_cluster(vm, cids, st, cluster_id):
    """Inline evidence pill: the KG glyph + one clickable number per cited fact,
    middot-separated, tinted by the claim's verification state. Each number keeps
    its own ``gl-cite`` id so clicking it still focuses that fact in the graph."""
    inner = [icon(GRAPH_GLYPH, 12, st["chip"], 2.1,
                  style={"display": "inline-block", "marginRight": "5px", "opacity": ".9"})]
    for i, cid in enumerate(cids):
        cit = vm["citations"].get(cid, {})
        cst = _lstyle(cit.get("label", "supported"))
        if i:
            inner.append(html.Span("·", className="gl-evdot"))
        inner.append(html.Span(str(cit.get("num", "")), id={"type": "gl-cite", "cid": cid},
                               n_clicks=0, className="gl-evnum", style={"color": cst["chip"]}))
    return html.Span(inner, id=cluster_id, tabIndex=0, className="gl-evcluster",
                     style={"background": st["chipbg"], "borderColor": st["under"], "color": st["chip"]})


def _evidence_card(vm, cids):
    """The combined hover card: one row per fact (node tile · subject—pred→object ·
    [T#] · state), so a multi-citation claim is read as one body of evidence."""
    n = len(cids)
    rows = []
    for cid in cids:
        cit = vm["citations"].get(cid, {})
        st = _lstyle(cit.get("label", "supported"))
        node = next((x for x in vm["nodes"] if x["id"] == cit.get("node")), None)
        tile = html.Img(src=node_img_src(node), style={
            "width": "34px", "height": "34px", "borderRadius": "8px", "flex": "0 0 auto",
            **({} if (node or {}).get("has_image") else {"border": "1.5px dashed #ced4da"})}) if node else None
        # subject —predicate→ object (falls back to the joined triple text)
        if cit.get("p_label") or cit.get("o_label"):
            triple = html.Div([
                html.Span(cit.get("s_label", ""), style={"color": "#868e96"}),
                html.Span(f" {cit.get('p_label', '')} ", style={"color": st["chip"], "fontWeight": 600}),
                icon(ARROW_GLYPH, 9, st["chip"], 2.4, style={"display": "inline-block", "verticalAlign": "middle"}),
                html.Span(f" {cit.get('o_label', '')}", style={"color": "#212529", "fontWeight": 600}),
            ], className="mono", style={"fontSize": "10px", "lineHeight": "1.55"})
        else:
            triple = html.Div(cit.get("triple", ""), className="mono",
                              style={"fontSize": "10px", "color": "#343a40", "lineHeight": "1.55"})
        state = html.Span([label_icon(cit.get("label", "supported"), 11), " ", (st["tag"] or "supported")],
                          style={"display": "inline-flex", "alignItems": "center", "gap": "3px",
                                 "fontSize": "9.5px", "fontWeight": 700, "color": st["color"], "marginTop": "3px"})
        num = html.Span(str(cit.get("num", "")), className="mono", style={
            "fontSize": "10px", "fontWeight": 600, "color": st["chip"], "background": st["chipbg"],
            "borderRadius": "5px", "padding": "1px 5px", "flex": "0 0 auto", "alignSelf": "flex-start"})
        rows.append(html.Div([tile, html.Div([triple, state], style={"minWidth": 0, "flex": 1}), num],
                             className="gl-evrow"))
    header = html.Div([icon(GRAPH_GLYPH, 12, "#868e96", 2, style={"display": "inline-block"}),
                       html.Span(f"backs this claim · {n} fact{'s' if n != 1 else ''}",
                                 style={"marginLeft": "5px"})], className="gl-evhdr")
    footer = html.Div([icon(LINK_GLYPH, 11, "#adb5bd", 2, style={"display": "inline-block"}),
                       html.Span("Knowledge graph", style={"marginLeft": "5px"}),
                       html.Span("click a number → open graph",
                                 style={"marginLeft": "auto", "color": "#1971c2", "fontWeight": 600})],
                      className="gl-evftr")
    return html.Div([header, *rows, footer], style={"width": "302px"})


def render_actions(played):
    return [html.Button([icon(GRAPH_GLYPH, 15, "currentColor", 2, style={"display": "inline-block"}),
                         html.Span("Replay retrieval" if played else "Ground answer")],
                        id="gl-ground", n_clicks=0, style={
            "display": "flex", "alignItems": "center", "gap": "7px",
            "border": "1px solid #a5d8ff", "background": "#e7f5ff", "color": "#1971c2",
            "borderRadius": "9px", "padding": "8px 13px", "fontFamily": "inherit", "fontSize": "12.5px",
            "fontWeight": 700, "cursor": "pointer"}),
            html.Button("Toggle subgraph", id="gl-toggle-drawer", n_clicks=0, className="gl-hoverbg", style={
            "border": "1px solid #e9ecef", "background": "#fff", "color": "#495057", "borderRadius": "9px",
            "padding": "8px 12px", "fontFamily": "inherit", "fontSize": "12.5px", "fontWeight": 600, "cursor": "pointer"})]


def detail_hint():
    return html.Div([icon(LINK_GLYPH, 15, "#ced4da", 2, style={"display": "inline-block"}),
                     "Select a citation or node to inspect its evidence"],
                    style={"fontSize": "11.5px", "color": "#adb5bd", "display": "flex", "alignItems": "center",
                           "gap": "7px", "height": "72px", "justifyContent": "center", "textAlign": "center"})


def detail_for(vm, node_id, cid=None):
    node = next((x for x in vm["nodes"] if x["id"] == node_id), None)
    if not node:
        return detail_hint()
    cit = vm["citations"].get(cid) if cid else next(
        (c for c in vm["citations"].values() if c.get("node") == node_id or c.get("node2") == node_id), None)
    # clean initials tile for no-image nodes; dashed border keeps the "no photo" cue
    img = html.Img(src=node_img_src(node), style={
        "width": "54px", "height": "54px", "borderRadius": "11px", "flex": "0 0 auto",
        **({} if node.get("has_image") else {"border": "1.5px dashed #ced4da"})})
    triple = cit["triple"] if cit else node["label"]
    src = cit["src"] if cit else "Knowledge graph"
    # #3 — mask this entity and regenerate (causal intervention)
    mask_btn = html.Button([
        icon('<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.7 5.1A11 11 0 0 1 12 5c7 0 10 7 10 7a13 13 0 0 1-1.7 2.7"/>'
             '<path d="M6.6 6.6A13 13 0 0 0 2 12s3 7 10 7a11 11 0 0 0 5.4-1.4"/><line x1="2" y1="2" x2="22" y2="22"/>',
             13, "#e8590c", 2, style={"display": "inline-block"}),
        html.Span("Mask & regenerate")],
        id={"type": "gl-mask", "node": node["id"]}, n_clicks=0, title="Remove this entity and re-run", style={
        "display": "inline-flex", "alignItems": "center", "gap": "6px", "marginTop": "9px",
        "border": "1px solid #ffd9a8", "background": "#fff8f0", "color": "#b85309", "borderRadius": "8px",
        "padding": "5px 10px", "fontFamily": "inherit", "fontSize": "11.5px", "fontWeight": 700, "cursor": "pointer"})
    return html.Div([img, html.Div([
        html.Div(node["label"], style={"fontSize": "13.5px", "fontWeight": 700, "color": "#212529"}),
        html.Div(triple, className="mono", style={"fontSize": "10.5px", "color": "#495057", "marginTop": "5px",
                 "lineHeight": "1.5", "background": "#f8f9fa", "borderRadius": "7px", "padding": "6px 8px"}),
        html.Div([icon(LINK_GLYPH, 11, "#adb5bd", 2, style={"display": "inline-block"}), " ", src],
                 style={"fontSize": "10.5px", "color": "#868e96", "marginTop": "6px", "display": "flex",
                        "alignItems": "center", "gap": "5px"}),
        mask_btn,
    ], style={"minWidth": 0, "flex": 1})], style={"display": "flex", "gap": "11px", "alignItems": "flex-start"})


ALL_LABELS = ["supported", "inferred", "unverifiable"]


def _claim_stats(items):
    n = len(items)
    # Only "unverifiable" counts as unsupported — "inferred" is treated as supported.
    bad = sum(1 for x in items if x.get("label", "unverifiable") == "unverifiable")
    return bad, n, (round(bad / n * 100) if n else 0)


def compare_header(crate, grate, abstained):
    """#5 — closed→grounded hallucination rate with the Δ, abstention as its own outcome."""
    delta = crate - grate            # positive = grounding reduced unsupported %
    improved = delta >= 0
    dcol = "#0ca678" if improved else "#e03131"
    arrow = "▼" if improved else "▲"
    badge = html.Span(f"{arrow} {abs(delta)} pts", style={
        "fontSize": "11px", "fontWeight": 800, "color": "#fff", "background": dcol,
        "borderRadius": "20px", "padding": "2px 10px"})
    row = html.Div([
        html.Span("Hallucination rate", style={"fontSize": "11px", "fontWeight": 700,
                  "textTransform": "uppercase", "letterSpacing": ".5px", "color": "#adb5bd"}),
        html.Span(f"closed-book {crate}%", style={"fontWeight": 800, "color": "#e03131"}),
        html.Span("→", style={"color": "#adb5bd"}),
        html.Span(f"grounded {grate}%", style={"fontWeight": 800, "color": "#0ca678"}),
        badge,
    ], style={"display": "flex", "alignItems": "center", "gap": "10px", "flexWrap": "wrap", "fontSize": "13px"})
    children = [row]
    if abstained:
        children.append(html.Div([
            icon(WARN_GLYPH, 13, "#f08c00", 2, style={"display": "inline-block"}),
            html.Span("Grounded model abstained — declined for insufficient facts (counted separately, not as a hallucination)"),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginTop": "8px",
                  "fontSize": "11.5px", "color": "#b85309", "fontWeight": 600}))
    return html.Div(children, style={"background": "#f8f9fb", "border": "1px solid #eef0f2",
                    "borderRadius": "12px", "padding": "12px 14px", "marginBottom": "14px"})


def filter_chips(active):
    """#4 — toggle which support levels are shown."""
    def chip(label):
        on = label in active
        st = _lstyle(label)
        return html.Button([label_icon(label, 12), html.Span(label)],
            id={"type": "gl-filter", "label": label}, n_clicks=0, style={
            "display": "inline-flex", "alignItems": "center", "gap": "5px", "border": f"1px solid {st['border']}",
            "background": st["chipbg"] if on else "#fff", "color": st["color"] if on else "#adb5bd",
            "opacity": 1 if on else .55, "borderRadius": "20px", "padding": "4px 11px",
            "fontFamily": "inherit", "fontSize": "11.5px", "fontWeight": 700, "cursor": "pointer",
            "textTransform": "capitalize"})
    return html.Div([html.Span("Show", style={"fontSize": "11.5px", "color": "#adb5bd", "fontWeight": 600}),
                     *[chip(l) for l in ALL_LABELS]],
                    style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "14px"})


def render_compare(vm, active=None):
    active = set(active) if active is not None else set(ALL_LABELS)
    cbad, cn, crate = _claim_stats(vm["closed_claims"])
    gbad, gn, grate = _claim_stats(vm["grounded_claims"])

    def claim_row(x, grounded):
        label = x.get("label", "unverifiable")
        st = _lstyle(label)
        cite = (html.Sup(x["c"], className="mono", style={"fontSize": "9px", "fontWeight": 500, "color": st["chip"],
                "background": st["chipbg"], "borderRadius": "5px", "padding": "1px 4px", "marginLeft": "3px"})
                if grounded and x.get("c") else None)
        tag = (html.Span(st["tag"], style={"display": "inline-block", "fontSize": "10px", "color": st["color"],
               "fontWeight": 700, "background": st["chipbg"], "borderRadius": "5px", "padding": "1px 6px",
               "marginLeft": "6px", "whiteSpace": "nowrap"}) if st["tag"] else None)
        return html.Div([html.Span(label_icon(label), style={"flex": "0 0 auto", "marginTop": "1px"}),
                         html.Span([x["t"], cite, tag], style={"fontSize": "13.5px", "lineHeight": "1.5", "color": "#343a40"})],
                        title=x.get("why", ""), className="gl-rise",
                        style={"display": "flex", "gap": "9px", "alignItems": "flex-start", "padding": "8px 10px",
                               "border": f"1px solid {st['border']}", "background": st["bg"], "borderRadius": "9px",
                               "marginBottom": "7px", "cursor": "help" if x.get("why") else "default"})

    def column(items, grounded, bad, n, rate):
        ac = "#c3fae8" if grounded else "#ffe3e0"
        bg = "#e6fcf5" if grounded else "#fff5f4"
        title = "LLM grounded" if grounded else "LLM closed-book"
        sub = "question + KG triples" if grounded else "question only · no KG context"
        dot = "#0ca678" if grounded else "#e03131"
        rows = [claim_row(x, grounded) for x in items if x.get("label", "unverifiable") in active]
        if not rows:
            rows = [html.Div("No claims match the filter.", style={"fontSize": "12px", "color": "#adb5bd", "padding": "8px 2px"})]
        return html.Div([
            html.Div([html.Div([html.Span(style={"width": "9px", "height": "9px", "borderRadius": "3px", "background": dot}),
                                html.Div([html.Div(title, style={"fontSize": "12.5px", "fontWeight": 700}),
                                          html.Div(sub, style={"fontSize": "10px", "color": "#868e96"})])],
                               style={"display": "flex", "alignItems": "center", "gap": "8px"}),
                      html.Div(f"{bad}/{n} unsupported · {rate}%", style={"fontSize": "11px", "fontWeight": 700, "color": dot})],
                     style={"padding": "11px 14px", "background": bg, "borderBottom": f"1px solid {ac}",
                            "display": "flex", "alignItems": "center", "justifyContent": "space-between"}),
            html.Div(rows, style={"padding": "12px 13px"}),
        ], style={"border": f"1px solid {ac}", "borderRadius": "14px", "overflow": "hidden",
                  "display": "flex", "flexDirection": "column"})

    return html.Div([
        compare_header(crate, grate, vm.get("abstained")),
        filter_chips(active),
        html.Div([column(vm["closed_claims"], False, cbad, cn, crate),
                  column(vm["grounded_claims"], True, gbad, gn, grate)],
                 style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}),
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  Layout
# ══════════════════════════════════════════════════════════════════════════════
def _seg_style(active):
    return {"border": "none", "background": "#fff" if active else "transparent",
            "color": "#228be6" if active else "#868e96", "borderRadius": "6px", "padding": "6px 11px",
            "fontFamily": "inherit", "fontSize": "11.5px", "fontWeight": 700, "cursor": "pointer",
            "boxShadow": "0 1px 2px rgba(0,0,0,.06)" if active else "none"}


def _drawer_btn():
    return {"display": "flex", "alignItems": "center", "justifyContent": "center", "width": "30px", "height": "30px",
            "border": "1px solid #e9ecef", "background": "#fff", "borderRadius": "8px", "color": "#868e96", "cursor": "pointer"}


# OpenRouter model catalogue for the searchable model dropdown
MODEL_OPTIONS = data.fetch_models()
DEFAULT_MODEL_VALUE = (config.DEFAULT_MODEL
                       if any(o["value"] == config.DEFAULT_MODEL for o in MODEL_OPTIONS)
                       else (MODEL_OPTIONS[0]["value"] if MODEL_OPTIONS else config.DEFAULT_MODEL))


HEADER = html.Header([
    html.Div(icon(GRAPH_GLYPH, 16, "#fff", 2.2), style={
        "width": "28px", "height": "28px", "borderRadius": "8px",
        "background": "linear-gradient(135deg,#228be6,#4263eb)", "display": "flex",
        "alignItems": "center", "justifyContent": "center", "boxShadow": "0 2px 6px rgba(34,139,230,.32)"}),
    html.Span("KG Grounding Studio", style={"fontWeight": 800, "fontSize": "14px", "letterSpacing": "-.2px"}),
    html.Span("DBpedia · multimodal KG", style={"fontSize": "11px", "color": "#adb5bd", "fontWeight": 600,
              "padding": "2px 8px", "background": "#f8f9fa", "borderRadius": "20px"}),
    html.Div(style={"flex": 1}),
    html.Span("Multimodal KG grounding · research demo", style={"fontSize": "11px", "color": "#ced4da", "fontWeight": 600}),
], style={"flex": "0 0 auto", "height": "54px", "display": "flex", "alignItems": "center", "gap": "10px",
          "padding": "0 18px", "background": "#fff", "borderBottom": "1px solid #eef0f2", "zIndex": 30})

HERO = html.Div([html.Div([
    html.Div(icon(GRAPH_GLYPH, 28, "#fff", 2.1), style={
        "width": "54px", "height": "54px", "borderRadius": "16px",
        "background": "linear-gradient(135deg,#228be6,#4263eb)", "display": "flex", "alignItems": "center",
        "justifyContent": "center", "boxShadow": "0 10px 26px -8px rgba(34,139,230,.5)", "marginBottom": "22px"}),
    html.P("Ask a question over a multimodal KG. The system links the entities, retrieves the supporting "
           "subgraph, and shows which facts each claim is built on.",
           style={"fontSize": "15px", "color": "#868e96", "margin": "0 0 28px", "lineHeight": "1.55", "maxWidth": "470px"}),
    html.Div([
        icon(SEARCH_GLYPH, 18, "#adb5bd", 2, style={"display": "inline-block"}),
        dcc.Input(id="gl-q", value="What did Marie Curie work on?",
                  placeholder="Ask about any entity in the knowledge graph…", debounce=False,
                  style={"flex": 1, "minWidth": 0, "border": "none", "outline": "none", "background": "transparent",
                         "fontFamily": "inherit", "fontSize": "16px", "color": "#212529"}),
        html.Button([icon(GRAPH_GLYPH, 15, "#fff", 2, style={"display": "inline-block"}), "Ground answer"],
                    id="gl-submit", n_clicks=0, className="gl-submit", style={
            "flex": "0 0 auto", "height": "44px", "display": "flex", "alignItems": "center", "gap": "7px",
            "background": "#228be6", "color": "#fff", "border": "none", "borderRadius": "12px", "padding": "0 17px",
            "fontFamily": "inherit", "fontSize": "13.5px", "fontWeight": 700, "cursor": "pointer",
            "boxShadow": "0 2px 8px rgba(34,139,230,.32)"}),
    ], id="gl-hero-field", style={"width": "100%", "display": "flex", "alignItems": "center", "gap": "10px",
        "background": "#fff", "border": "1.5px solid #e3e6ea", "borderRadius": "16px",
        "boxShadow": "0 8px 30px -12px rgba(15,23,42,.18)", "padding": "7px 7px 7px 16px"}),
    html.Div([
        dcc.Dropdown(id="gl-model", clearable=False, value=DEFAULT_MODEL_VALUE,
                     options=MODEL_OPTIONS, searchable=True, placeholder="Search models…",
                     style={"width": "260px", "fontSize": "12px"}),
        dcc.Dropdown(id="gl-verifier", clearable=False, value=config.VERIFIER,
                     options=[{"label": "Verify: LLM judge", "value": "llm"},
                              {"label": "Verify: NLI model", "value": "nli"}],
                     style={"width": "170px", "fontSize": "12px"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "9px", "marginTop": "15px"}),
    html.Div([html.Span("Try", style={"fontSize": "11.5px", "color": "#adb5bd", "fontWeight": 600}),
              html.Button("What did Marie Curie work on?", id={"type": "gl-ex", "i": 0}, n_clicks=0, className="gl-ex"),
              html.Button("Where was Alan Turing born?", id={"type": "gl-ex", "i": 1}, n_clicks=0, className="gl-ex"),
              html.Button("Who did Albert Einstein work with?", id={"type": "gl-ex", "i": 2}, n_clicks=0, className="gl-ex")],
             style={"display": "flex", "alignItems": "center", "gap": "8px", "marginTop": "22px",
                    "flexWrap": "wrap", "justifyContent": "center"}),
], style={"width": "100%", "maxWidth": "620px", "display": "flex", "flexDirection": "column",
          "alignItems": "center", "textAlign": "center"})],
    id="gl-hero", className="gl-scroll", style={"flex": "1 1 auto", "minHeight": 0, "display": "flex",
        "flexDirection": "column", "alignItems": "center", "justifyContent": "center", "padding": "24px", "overflowY": "auto"})

RESULTS = html.Div([html.Div([
    html.Div([
        html.Button([icon(BACK_GLYPH, 14, "currentColor", 2.2, style={"display": "inline-block"}), "New search"],
                    id="gl-back", n_clicks=0, className="gl-hoverbg", style={
            "display": "flex", "alignItems": "center", "gap": "6px", "border": "1px solid #e9ecef",
            "background": "#fff", "borderRadius": "9px", "padding": "6px 11px", "fontFamily": "inherit",
            "fontSize": "12px", "fontWeight": 600, "color": "#495057", "cursor": "pointer"}),
        html.Span("", id="gl-mdlabel", className="mono", style={"fontSize": "11px", "color": "#adb5bd"}),
        html.Div(style={"flex": 1}),
        html.Div([
            html.Button("Grounded answer", id="gl-view-answer-btn", n_clicks=0,
                        style=_seg_style(True)),
            html.Button("Closed-book vs grounded", id="gl-view-compare-btn", n_clicks=0,
                        style=_seg_style(False)),
        ], style={"display": "flex", "gap": "2px", "background": "#f1f3f5", "border": "1px solid #eef0f2",
                  "borderRadius": "9px", "padding": "3px"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "12px", "marginBottom": "16px"}),
    html.H2("", id="gl-qheading", style={"fontSize": "21px", "fontWeight": 800, "letterSpacing": "-.3px",
            "color": "#212529", "margin": "0 0 22px", "lineHeight": "1.35"}),
    html.Div([
        html.Div(id="gl-trace", style={"marginBottom": "16px"}),
        html.Div(id="gl-answer-wrap"),
        html.Div(render_actions(False), id="gl-actions", style={"display": "flex", "alignItems": "center",
                 "gap": "8px", "marginTop": "22px"}),
    ], id="gl-view-answer"),
    html.Div(id="gl-view-compare", style={"display": "none"}),
], id="gl-results-inner", className="gl-scroll", style={"maxWidth": "780px", "width": "100%", "margin": "0 auto",
    "padding": "22px 24px 30px"})],
    id="gl-results", style={"display": "none", "flex": "1 1 auto", "minHeight": 0, "flexDirection": "column", "overflowY": "auto"})

DRAWER = html.Aside([
    html.Div([
        html.Div([icon(GRAPH_GLYPH, 16, "#7048e8", 2, style={"display": "inline-block"}),
                  html.Div([html.Div("Knowledge subgraph", style={"fontSize": "13px", "fontWeight": 700}),
                            html.Div("retrieved for this answer", id="gl-graph-meta",
                                     style={"fontSize": "10.5px", "color": "#adb5bd", "marginTop": "1px"})],
                           style={"lineHeight": "1.2", "whiteSpace": "nowrap"})],
                 style={"display": "flex", "alignItems": "center", "gap": "9px"}),
        html.Div([
            html.Button(icon('<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>', 14, "currentColor", 2, style={"display": "inline-block"}),
                        id="gl-only-used-btn", n_clicks=0, className="gl-hoverbg",
                        title="Show only the relations used to answer", style=_drawer_btn()),
            html.Button(icon(FIT_GLYPH, 14, "currentColor", 2, style={"display": "inline-block"}),
                        id="gl-fit", n_clicks=0, className="gl-hoverbg", title="Fit", style=_drawer_btn()),
            html.Button(icon(CHEV_GLYPH, 15, "currentColor", 2.2, style={"display": "inline-block"}),
                        id="gl-collapse", n_clicks=0, className="gl-hoverbg", title="Collapse", style=_drawer_btn()),
        ], style={"display": "flex", "gap": "5px"}),
    ], style={"flex": "0 0 auto", "display": "flex", "alignItems": "center", "justifyContent": "space-between",
              "padding": "13px 15px", "borderBottom": "1px solid #f1f3f5", "width": "480px"}),
    html.Div(cyto.Cytoscape(id="gl-cy", layout={"name": "preset"}, elements=[], stylesheet=CYTO_STYLESHEET,
                            style={"position": "absolute", "inset": 0}, minZoom=.3, maxZoom=2.4,
                            userZoomingEnabled=True, userPanningEnabled=True),
             style={"flex": "1 1 auto", "minHeight": 0, "position": "relative", "width": "480px",
                    "background": "radial-gradient(ellipse at 50% 38%,#fbfcfd 0%,#f3f5f7 100%)"}),
    html.Div(detail_hint(), id="gl-detail", style={"flex": "0 0 auto", "width": "480px",
             "borderTop": "1px solid #f1f3f5", "padding": "12px 15px", "minHeight": "96px"}),
], id="gl-drawer", style={"flex": "0 0 0px", "width": 0, "minWidth": 0, "overflow": "hidden", "background": "#fff",
    "borderLeft": "1px solid #eef0f2", "display": "flex", "flexDirection": "column",
    "transition": "flex-basis .4s cubic-bezier(.22,1,.36,1), width .4s cubic-bezier(.22,1,.36,1)"})

app.layout = html.Div([
    dcc.Store(id="gl-store"),          # the view model
    dcc.Store(id="gl-view", data="answer"),
    dcc.Store(id="gl-drawer-open", data=False),
    dcc.Store(id="gl-played", data=False),
    dcc.Store(id="gl-pending"),        # {q, model, ds, verifier} → triggers the heavy run
    dcc.Store(id="gl-filter", data=ALL_LABELS),   # active support levels in compare (#4)
    dcc.Store(id="gl-only-used", data=False),     # graph: show only the relations used to answer
    dcc.Interval(id="gl-interval", interval=650, disabled=True, n_intervals=0),
    HEADER,
    html.Div([html.Div([HERO, RESULTS], id="gl-chat", style={"flex": "1 1 auto", "minWidth": 0, "minHeight": 0,
              "display": "flex", "flexDirection": "column"}), DRAWER],
             id="gl-stage", style={"flex": "1 1 auto", "minHeight": 0, "display": "flex", "flexDirection": "row"}),
], style={"width": "100vw", "minWidth": "720px", "height": "100vh", "minHeight": "640px", "display": "flex",
          "flexDirection": "column", "overflow": "hidden", "background": "#fbfcfd"})


# ══════════════════════════════════════════════════════════════════════════════
#  Callbacks
# ══════════════════════════════════════════════════════════════════════════════
_DRAWER_BASE = {"overflow": "hidden", "background": "#fff", "borderLeft": "1px solid #eef0f2",
                "display": "flex", "flexDirection": "column",
                "transition": "flex-basis .4s cubic-bezier(.22,1,.36,1), width .4s cubic-bezier(.22,1,.36,1)"}

EX_TEXT = {0: "What did Marie Curie work on?",
           1: "Where was Alan Turing born?",
           2: "Who did Albert Einstein work with?"}


def drawer_style(is_open):
    w = "480px" if is_open else "0px"
    return {**_DRAWER_BASE, "flex": f"0 0 {w}", "width": (480 if is_open else 0), "minWidth": (480 if is_open else 0)}


def layout_for(vm):
    name = "preset" if vm.get("source") == "mock" else "cose"
    return {"name": name, "fit": True, "padding": 46, "animate": False}


def actions_running():
    return [html.Span([html.Span(className="gl-spin"), "Running grounding pipeline…"],
                      style={"fontSize": "12px", "color": "#868e96", "display": "flex", "alignItems": "center",
                             "gap": "8px", "fontWeight": 600})]


def first_citation(vm):
    if vm.get("citations"):
        cid = next(iter(vm["citations"]))
        return cid, vm["citations"][cid]["node"]
    return None, (vm["nodes"][0]["id"] if vm.get("nodes") else None)


# ── submit (button / Enter / example chips) ────────────────────────────────────
@callback(
    Output("gl-pending", "data"), Output("gl-store", "data"), Output("gl-interval", "disabled"),
    Output("gl-interval", "n_intervals"), Output("gl-hero", "style"), Output("gl-results", "style"),
    Output("gl-mdlabel", "children"), Output("gl-qheading", "children"), Output("gl-view", "data"),
    Output("gl-q", "value"), Output("gl-trace", "children"), Output("gl-answer-wrap", "children"),
    Output("gl-actions", "children"),
    Input("gl-submit", "n_clicks"), Input("gl-q", "n_submit"),
    Input({"type": "gl-ex", "i": ALL}, "n_clicks"),
    State("gl-q", "value"), State("gl-model", "value"),
    State("gl-verifier", "value"),
    prevent_initial_call=True,
)
def on_submit(_n, _ns, _ex, q, model, verifier):
    """Instant: jump to the results view with the pipeline shown 'running'. The
    heavy run_pipeline happens in on_run (triggered by gl-pending), so the click
    never freezes the UI."""
    trig = ctx.triggered_id
    if isinstance(trig, dict) and trig.get("type") == "gl-ex":
        q = EX_TEXT.get(trig["i"], q)
    q = (q or "").strip() or EX_TEXT[0]
    model = model or "GPT-4o"
    ds = "DBpedia"
    hero_hidden = {"display": "none"}
    results_shown = {"display": "flex", "flex": "1 1 auto", "minHeight": 0, "flexDirection": "column", "overflowY": "auto"}
    return ({"q": q, "model": model, "ds": ds, "verifier": verifier or "llm"}, None, True, 0,
            hero_hidden, results_shown, f"{model} · {ds}", f"“{q}”", "answer", q,
            trace_initial(), [], actions_running())


# ── run the pipeline (the slow part) once the UI has shown the running state ────
@callback(
    Output("gl-store", "data", allow_duplicate=True),
    Output("gl-interval", "disabled", allow_duplicate=True),
    Output("gl-interval", "n_intervals", allow_duplicate=True),
    Input("gl-pending", "data"), prevent_initial_call=True,
)
async def on_run(pending):
    if not pending:
        return no_update, no_update, no_update
    vm = await data.get_result(pending["q"], pending["model"], pending["ds"],
                               verifier=pending.get("verifier"))
    return vm, False, 0  # data ready → arm the staged reveal (on_tick)


# ── mask an entity and regenerate (#3) — re-run on the filtered subgraph ────────
@callback(
    Output("gl-store", "data", allow_duplicate=True),
    Output("gl-interval", "n_intervals", allow_duplicate=True),
    Output("gl-interval", "disabled", allow_duplicate=True),
    Input({"type": "gl-mask", "node": ALL}, "n_clicks"),
    State("gl-store", "data"), prevent_initial_call=True,
)
async def on_mask(clicks, vm):
    # ignore the spurious fire when a mask button is (re)created in the detail panel
    if not vm or not isinstance(ctx.triggered_id, dict) or not any(c for c in (clicks or [])):
        return no_update, no_update, no_update
    node_id = ctx.triggered_id["node"]
    cx = vm.get("context") or {}
    sub = cx.get("subgraph") or {"nodes": [], "edges": []}
    filtered = {
        "nodes": [n for n in sub["nodes"] if n["id"] != node_id],
        "edges": [e for e in sub["edges"] if e["subject"] != node_id and e["object"] != node_id],
    }
    new_vm = await data.get_result(cx["question"], cx["model"], cx.get("dataset", "DBpedia"),
                                   verifier=cx.get("verifier"), subgraph=filtered)
    return new_vm, 0, False  # replay the reveal with the masked result


# ── staged pipeline reveal (driven by the Interval) ────────────────────────────
@callback(
    Output("gl-interval", "disabled", allow_duplicate=True),
    Output("gl-trace", "children", allow_duplicate=True),
    Output("gl-answer-wrap", "children", allow_duplicate=True),
    Output("gl-actions", "children", allow_duplicate=True),
    Output("gl-cy", "elements"), Output("gl-cy", "layout"), Output("gl-detail", "children"),
    Output("gl-drawer", "style"), Output("gl-drawer-open", "data"), Output("gl-graph-meta", "children"),
    Output("gl-played", "data"),
    Input("gl-interval", "n_intervals"), State("gl-store", "data"), State("gl-only-used", "data"),
    prevent_initial_call=True,
)
def on_tick(n, vm, only_used):
    if not vm:
        return (True,) + (no_update,) * 10
    NU = no_update
    has_triples = vm.get("has_triples", True)
    if n <= 1:  # entity linking
        return (False, trace_running(vm, "active", "pending", "pending"), [], actions_running(),
                NU, NU, NU, NU, NU, NU, NU)
    if n == 2:  # subgraph retrieval — populate + open drawer (only if we got facts)
        if not has_triples:
            return (False, trace_running(vm, "done", "active", "pending"), [], actions_running(),
                    NU, NU, NU, NU, NU, "no facts found", NU)
        return (False, trace_running(vm, "done", "active", "pending"), [], actions_running(),
                build_elements(vm, only_used=only_used), layout_for(vm), detail_hint(),
                drawer_style(True), True, "retrieving…", NU)
    if n == 3:  # grounding the answer
        return (False, trace_running(vm, "done", "done", "active"), [], actions_running(),
                NU, NU, NU, NU, NU, NU, NU)
    # n >= 4 — done
    if not has_triples:  # no triples → no grounded answer; keep the drawer shut
        return (True, trace_summary(vm), render_no_grounding(vm), render_actions(True),
                [], layout_for(vm), detail_hint(), drawer_style(False), False,
                "no subgraph retrieved", True)
    cid, node_id = first_citation(vm)
    cit = vm["citations"].get(cid, {})
    sel = [x for x in (cit.get("node"), cit.get("node2")) if x] or ([node_id] if node_id else [])
    return (True, trace_summary(vm), render_answer(vm), render_actions(True),
            build_elements(vm, selected=sel, hi_edges=cit.get("edges"), only_used=only_used),
            layout_for(vm), detail_for(vm, node_id, cid), drawer_style(True), True, graph_meta(vm, only_used), True)


# ── grounded ↔ compare view toggle ─────────────────────────────────────────────
@callback(
    Output("gl-view", "data", allow_duplicate=True), Output("gl-view-answer", "style"),
    Output("gl-view-compare", "style"), Output("gl-view-compare", "children"),
    Output("gl-view-answer-btn", "style"), Output("gl-view-compare-btn", "style"),
    Input("gl-view-answer-btn", "n_clicks"), Input("gl-view-compare-btn", "n_clicks"),
    State("gl-store", "data"), State("gl-filter", "data"), prevent_initial_call=True,
)
def on_view(_a, _c, vm, active):
    compare = ctx.triggered_id == "gl-view-compare-btn"
    if compare and vm:
        return ("compare", {"display": "none"}, {"display": "block"}, render_compare(vm, active),
                _seg_style(False), _seg_style(True))
    return ("answer", {"display": "block"}, {"display": "none"}, no_update,
            _seg_style(True), _seg_style(False))


# ── filter compare claims by support level (#4) ────────────────────────────────
@callback(
    Output("gl-filter", "data"), Output("gl-view-compare", "children", allow_duplicate=True),
    Input({"type": "gl-filter", "label": ALL}, "n_clicks"),
    State("gl-filter", "data"), State("gl-store", "data"), prevent_initial_call=True,
)
def on_filter(clicks, active, vm):
    # ignore the spurious fire when the chips are (re)created
    if not vm or not isinstance(ctx.triggered_id, dict) or not any(c for c in (clicks or [])):
        return no_update, no_update
    label = ctx.triggered_id["label"]
    active = set(active or ALL_LABELS)
    active.discard(label) if label in active else active.add(label)
    ordered = [l for l in ALL_LABELS if l in active]
    return ordered, render_compare(vm, ordered)


# ── citation click / node tap / "view graph" pill → detail + selection ─────────
@callback(
    Output("gl-detail", "children", allow_duplicate=True), Output("gl-cy", "elements", allow_duplicate=True),
    Output("gl-drawer", "style", allow_duplicate=True), Output("gl-drawer-open", "data", allow_duplicate=True),
    Input({"type": "gl-cite", "cid": ALL}, "n_clicks"), Input("gl-cy", "tapNodeData"),
    Input("gl-trace-pill", "n_clicks"),
    State("gl-store", "data"), State("gl-drawer-open", "data"), State("gl-only-used", "data"),
    prevent_initial_call=True,
)
def on_inspect(cite_clicks, tap, _pill, vm, is_open, only_used):
    if not vm:
        return (no_update,) * 4
    trig = ctx.triggered_id
    # "view graph" summary pill → just toggle the drawer
    if trig == "gl-trace-pill":
        if not _pill:  # pill was just (re)created, not actually clicked
            return (no_update,) * 4
        nxt = not is_open
        return (no_update, no_update, drawer_style(nxt), nxt)
    # citation span clicked → select the cited node(s) + light up the backing edge(s)
    if isinstance(trig, dict) and trig.get("type") == "gl-cite":
        if not any(c for c in (cite_clicks or [])):
            return (no_update,) * 4
        cid = trig["cid"]
        cit = vm["citations"].get(cid, {})
        node_id = cit.get("node")
        sel = [x for x in (cit.get("node"), cit.get("node2")) if x]
        return (detail_for(vm, node_id, cid),
                build_elements(vm, selected=sel, hi_edges=cit.get("edges"), only_used=only_used),
                drawer_style(True), True)
    # node tapped in the graph → highlight the node and all its incident edges
    if trig == "gl-cy" and tap:
        node_id = tap["id"]
        incident = [(e["source"], e["target"]) for e in vm["edges"] if node_id in (e["source"], e["target"])]
        return (detail_for(vm, node_id),
                build_elements(vm, selected=node_id, hi_edges=incident, only_used=only_used),
                drawer_style(True), True)
    return (no_update,) * 4


# ── toggle: show only the relations used to answer (graph) ─────────────────────
@callback(
    Output("gl-only-used", "data"), Output("gl-cy", "elements", allow_duplicate=True),
    Output("gl-cy", "layout", allow_duplicate=True), Output("gl-graph-meta", "children", allow_duplicate=True),
    Output("gl-only-used-btn", "style"),
    Input("gl-only-used-btn", "n_clicks"), State("gl-only-used", "data"), State("gl-store", "data"),
    prevent_initial_call=True,
)
def on_toggle_used(_n, on, vm):
    if not vm:
        return (no_update,) * 5
    nxt = not on
    btn = {**_drawer_btn(), **({"background": "#e7f5ff", "color": "#1971c2", "borderColor": "#a5d8ff"} if nxt else {})}
    return (nxt, build_elements(vm, only_used=nxt), layout_for(vm), graph_meta(vm, nxt), btn)


# ── drawer collapse / toggle / fit ─────────────────────────────────────────────
@callback(
    Output("gl-drawer", "style", allow_duplicate=True), Output("gl-drawer-open", "data", allow_duplicate=True),
    Input("gl-collapse", "n_clicks"), Input("gl-toggle-drawer", "n_clicks"),
    State("gl-drawer-open", "data"), prevent_initial_call=True,
)
def on_drawer(_c, _t, is_open):
    # ignore the fire from these buttons being (re)created in the actions bar
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update, no_update
    nxt = False if ctx.triggered_id == "gl-collapse" else (not is_open)
    return drawer_style(nxt), nxt


@callback(Output("gl-cy", "layout", allow_duplicate=True), Input("gl-fit", "n_clicks"),
          State("gl-store", "data"), prevent_initial_call=True)
def on_fit(_n, vm):
    return layout_for(vm) if vm else no_update


# ── "Ground answer / Replay retrieval" button → replay the staged reveal ────────
@callback(
    Output("gl-interval", "n_intervals", allow_duplicate=True),
    Output("gl-interval", "disabled", allow_duplicate=True),
    Input("gl-ground", "n_clicks"), prevent_initial_call=True,
)
def on_replay(_n):
    # ignore the spurious fire when the button is (re)created with n_clicks=0;
    # only a real click (n_clicks>=1) should replay the reveal.
    if not _n:
        return no_update, no_update
    return 0, False


# ── back to hero (reset) ───────────────────────────────────────────────────────
@callback(
    Output("gl-hero", "style", allow_duplicate=True), Output("gl-results", "style", allow_duplicate=True),
    Output("gl-drawer", "style", allow_duplicate=True), Output("gl-drawer-open", "data", allow_duplicate=True),
    Output("gl-interval", "disabled", allow_duplicate=True), Output("gl-played", "data", allow_duplicate=True),
    Output("gl-view", "data", allow_duplicate=True),
    Input("gl-back", "n_clicks"), prevent_initial_call=True,
)
def on_back(_n):
    hero = {"flex": "1 1 auto", "minHeight": 0, "display": "flex", "flexDirection": "column",
            "alignItems": "center", "justifyContent": "center", "padding": "24px", "overflowY": "auto"}
    return (hero, {"display": "none"}, drawer_style(False), False, True, False, "answer")


if __name__ == "__main__":
    app.run(debug=True)
