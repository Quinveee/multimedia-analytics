"""Add-triple popup for the KG Grounding Studio.

Owns the modal layout and its open/close behaviour. The subject/predicate/object
form plus optional new-node fields are collected here; persisting and
regenerating happen in later stages.
"""

import base64
from urllib.parse import quote

import dash_bootstrap_components as dbc
from dash import Input, Output, State, ctx, dcc, html, no_update

_BLUE = "#228be6"

_INPUT = {"width": "100%", "border": "1px solid #e3e6ea", "borderRadius": "9px",
          "padding": "8px 11px", "fontFamily": "inherit", "fontSize": "13px",
          "color": "#212529", "outline": "none", "background": "#fff"}
_LABEL = {"fontSize": "11px", "fontWeight": 700, "textTransform": "uppercase",
          "letterSpacing": ".4px", "color": "#adb5bd", "marginBottom": "5px", "display": "block"}

_PLUS = '<path d="M12 5v14M5 12h14"/>'

# Predicate options are loaded once from the KG and reused across opens.
_PRED_CACHE = None


def _icon(path_svg, size=16, stroke="#868e96", width=2):
    """Inline SVG icon as a data-URI img, matching the studio's icon helper."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
           f'viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="{width}" '
           f'stroke-linecap="round" stroke-linejoin="round">{path_svg}</svg>')
    return html.Img(src="data:image/svg+xml;utf8," + quote(svg),
                    style={"display": "block", "flex": "0 0 auto"})


def trigger_button():
    """Drawer-header icon button that opens the modal."""
    return html.Button(_icon(_PLUS, 14, "currentColor", 2), id="ut-open", n_clicks=0,
                       className="gl-hoverbg", title="Add a missing triple",
                       style={"display": "flex", "alignItems": "center", "justifyContent": "center",
                              "width": "30px", "height": "30px", "border": "1px solid #e9ecef",
                              "background": "#fff", "borderRadius": "8px", "color": "#868e96",
                              "cursor": "pointer"})


def _field(label, comp, hint=None):
    kids = [html.Label(label, style=_LABEL), comp]
    if hint:
        kids.append(html.Div(hint, style={"fontSize": "10.5px", "color": "#adb5bd", "marginTop": "4px"}))
    return html.Div(kids, style={"marginBottom": "14px"})


def _new_node_section():
    """Optional fields applied to whichever endpoint is a new node."""
    return html.Div([
        html.Div([
            html.Div("New entity details", style={"fontSize": "12px", "fontWeight": 700, "color": "#495057"}),
            html.Div("used when the subject or object is a new node",
                     style={"fontSize": "10.5px", "color": "#adb5bd", "marginTop": "1px"}),
        ], style={"marginBottom": "11px"}),
        _field("Label", dcc.Input(id="ut-node-label", placeholder="e.g. Radioactivity", style=_INPUT)),
        _field("Abstract", dcc.Textarea(id="ut-node-abstract", placeholder="short description (optional)",
               style={**_INPUT, "height": "62px", "resize": "vertical"})),
        _field("Types", dcc.Input(id="ut-node-types", placeholder="comma-separated, e.g. Concept, Field",
               style=_INPUT)),
        _field("Image", html.Div([
            dcc.Upload(id="ut-node-image", accept="image/*", multiple=False,
                       children=html.Div(["Drop an image or ",
                                          html.Span("browse", style={"color": _BLUE, "fontWeight": 700})],
                                         style={"fontSize": "12px", "color": "#868e96"}),
                       style={"border": "1.5px dashed #d0d7de", "borderRadius": "9px", "padding": "14px",
                              "textAlign": "center", "cursor": "pointer", "background": "#fff"}),
            html.Div(id="ut-node-image-preview", style={"marginTop": "8px"}),
        ])),
    ], style={"border": "1px solid #eef0f2", "background": "#f8f9fb", "borderRadius": "12px",
              "padding": "13px 14px", "marginTop": "4px"})


def modal():
    """The add-triple modal, hidden until opened."""
    body = html.Div([
        html.P("Add a fact that's missing from the graph. The triple must touch at least one "
               "existing entity so the system can retrieve it.",
               style={"fontSize": "12.5px", "color": "#868e96", "margin": "0 0 16px", "lineHeight": "1.5"}),
        _field("Subject", dcc.Input(id="ut-subject",
               placeholder="existing id or new label, e.g. dbr:Marie_Curie", style=_INPUT)),
        _field("Predicate",
               html.Div([
                   dcc.Dropdown(id="ut-predicate", options=[], searchable=True, clearable=True,
                                placeholder="search existing predicates…", style={"fontSize": "13px"}),
                   dcc.Input(id="ut-predicate-custom",
                             placeholder="…or type a custom predicate, e.g. dbo:collaboratedWith",
                             style={**_INPUT, "marginTop": "7px"}),
               ]),
               hint="Pick an existing predicate, or type a custom one as a fallback."),
        _field("Predicate label", dcc.Input(id="ut-predicate-label",
               placeholder="human-readable, e.g. discovered", style=_INPUT)),
        _field("Object", dcc.Input(id="ut-object",
               placeholder="existing id or new label, e.g. Polonium", style=_INPUT)),
        _new_node_section(),
        html.Div(id="ut-status", style={"marginTop": "13px"}),
    ])
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add a missing triple")),
        dbc.ModalBody(body),
        dbc.ModalFooter(html.Div([
            dcc.ConfirmDialogProvider(
                html.Button("Clear all user additions", id="ut-reset-btn", n_clicks=0,
                            className="gl-hoverbg",
                            style={"border": "1px solid #ffd9d4", "background": "#fff", "color": "#e03131",
                                   "borderRadius": "9px", "padding": "8px 13px", "fontFamily": "inherit",
                                   "fontSize": "12px", "fontWeight": 600, "cursor": "pointer"}),
                id="ut-reset",
                message="Remove ALL user-added triples and uploaded images and revert to the base graph? This cannot be undone."),
            html.Div(style={"flex": 1}),
            html.Button("Cancel", id="ut-cancel", n_clicks=0, className="gl-hoverbg",
                        style={"border": "1px solid #e9ecef", "background": "#fff", "color": "#495057",
                               "borderRadius": "9px", "padding": "8px 14px", "fontFamily": "inherit",
                               "fontSize": "12.5px", "fontWeight": 600, "cursor": "pointer"}),
            html.Button([_icon(_PLUS, 15, "#fff", 2.2),
                         html.Span("Add triple", style={"marginLeft": "6px"})],
                        id="ut-submit", n_clicks=0, className="gl-submit",
                        style={"display": "inline-flex", "alignItems": "center", "background": _BLUE,
                               "color": "#fff", "border": "none", "borderRadius": "9px", "padding": "8px 15px",
                               "fontFamily": "inherit", "fontSize": "12.5px", "fontWeight": 700, "cursor": "pointer"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "width": "100%"})),
    ], id="ut-modal", is_open=False, centered=True, scrollable=True)


def _predicate_options():
    """Dropdown options for the predicates present in the KG, cached after first load."""
    global _PRED_CACHE
    if _PRED_CACHE is not None:
        return _PRED_CACHE
    try:
        from src.services.kg import KG
        rows = KG.predicates()
    except Exception as exc:
        print(f"[add-triple] could not load predicates: {exc}")
        return []
    seen = {}
    for r in rows:
        pid = r["predicate"]
        seen.setdefault(pid, r.get("predicate_label") or pid)
    opts = sorted(({"label": f"{lbl}  ({pid})", "value": pid} for pid, lbl in seen.items()),
                  key=lambda o: o["label"].lower())
    _PRED_CACHE = opts
    return opts


def _decode_upload(contents):
    """Decode a dcc.Upload data-URI to raw bytes, or None."""
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:
        return None


def parse_form(subject, pred_value, pred_custom, pred_label, obj,
               node_label, node_abstract, node_types, node_image=None):
    """Validate the popup form and return kwargs for user_kg.add_triple.

    A custom predicate overrides the dropdown selection. The new-node fields are
    passed for both endpoints; add_triple applies them only to the one that is
    actually new. Raises ValueError on missing required fields.
    """
    subject = (subject or "").strip()
    obj = (obj or "").strip()
    predicate = (pred_custom or "").strip() or (pred_value or "").strip()
    if not subject or not obj:
        raise ValueError("Subject and object are both required.")
    if not predicate:
        raise ValueError("Pick a predicate or type a custom one.")
    node = {}
    if (node_label or "").strip():
        node["label"] = node_label.strip()
    if (node_abstract or "").strip():
        node["abstract"] = node_abstract.strip()
    if (node_types or "").strip():
        node["types"] = node_types
    image_bytes = _decode_upload(node_image)
    if image_bytes:
        node["image_bytes"] = image_bytes
    return {"subject": subject, "predicate": predicate, "object": obj,
            "predicate_label": (pred_label or "").strip() or None,
            "subject_node": node or None, "object_node": node or None}


def _status(msg, color, bg, border):
    return html.Div(msg, style={"fontSize": "12px", "fontWeight": 600, "color": color,
                                "background": bg, "border": f"1px solid {border}",
                                "borderRadius": "9px", "padding": "9px 11px"})


def status_error(msg):
    return _status(msg, "#e03131", "#fff5f4", "#ffd9d4")


def status_success(msg):
    return _status(msg, "#0c7a5b", "#e6fcf5", "#c3fae8")


def status_busy(msg):
    """A spinner + message, shown while the triple is saved and the answer regenerates."""
    return html.Div([html.Span(className="gl-spin"),
                     html.Span(msg, style={"marginLeft": "9px"})],
                    style={"display": "flex", "alignItems": "center", "fontSize": "12px",
                           "fontWeight": 600, "color": "#1971c2", "background": "#e7f5ff",
                           "border": "1px solid #d0ebff", "borderRadius": "9px", "padding": "9px 11px"})


def register(app):
    """Register the popup's open/close, predicate loading, and label autofill."""

    @app.callback(
        Output("ut-modal", "is_open"),
        Input("ut-open", "n_clicks"), Input("ut-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def _toggle(_open, _cancel):
        return ctx.triggered_id == "ut-open"

    @app.callback(
        Output("ut-predicate", "options"),
        Input("ut-modal", "is_open"), State("ut-predicate", "options"),
        prevent_initial_call=True,
    )
    def _load_predicates(is_open, existing):
        if not is_open or existing:
            return no_update
        return _predicate_options()

    @app.callback(
        Output("ut-predicate-label", "value"),
        Input("ut-predicate", "value"),
        prevent_initial_call=True,
    )
    def _fill_label(pid):
        if not pid:
            return no_update
        for o in (_PRED_CACHE or []):
            if o["value"] == pid:
                return o["label"].split("  (")[0]
        return pid.split(":")[-1]

    @app.callback(
        Output("ut-node-image-preview", "children"),
        Input("ut-node-image", "contents"),
        State("ut-node-image", "filename"),
        prevent_initial_call=True,
    )
    def _preview(contents, filename):
        if not contents:
            return None
        return html.Div([
            html.Img(src=contents, style={"width": "44px", "height": "44px", "borderRadius": "8px",
                                          "objectFit": "cover", "flex": "0 0 auto"}),
            html.Span(filename or "image", style={"fontSize": "11.5px", "color": "#495057"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "9px"})
