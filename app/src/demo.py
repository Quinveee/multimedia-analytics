import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import Dash, Input, Output, State, callback, dcc, html

from src.pipeline import run_pipeline

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

_SPAN_COLORS = {
    "supported": "#d4edda",
    "inferred": "#fff3cd",
    "unverifiable": "#f8d7da",
}

_CYTO_STYLESHEET = [
    {
        "selector": "node",
        "style": {
            "label": "data(label)",
            "background-color": "#6c757d",
            "color": "#fff",
            "font-size": "10px",
            "text-valign": "center",
            "text-halign": "center",
            "width": 40,
            "height": 40,
        },
    },
    {
        "selector": "edge",
        "style": {
            "label": "data(label)",
            "font-size": "8px",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "line-color": "#adb5bd",
            "target-arrow-color": "#adb5bd",
        },
    },
    {"selector": ":selected", "style": {"background-color": "#0d6efd"}},
]

app.layout = dbc.Container(
    [
        html.H3("Pipeline Demo", className="mt-4 mb-3"),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Input(
                        id="question-input",
                        placeholder="Ask a question...",
                        type="text",
                    ),
                    width=9,
                ),
                dbc.Col(dbc.Button("Run", id="run-btn", color="primary"), width=3),
            ],
            className="mb-3",
        ),
        dcc.Store(id="store"),
        dcc.Loading(html.Div(id="output"), type="circle"),
        html.Div(
            id="graph-section",
            style={"display": "none"},
            children=[
                html.Hr(),
                html.H5("Subgraph : select nodes to filter, then re-run:"),
                cyto.Cytoscape(
                    id="cytoscape",
                    layout={"name": "cose"},
                    style={
                        "width": "100%",
                        "height": "450px",
                        "border": "1px solid #dee2e6",
                    },
                    stylesheet=_CYTO_STYLESHEET,
                    elements=[],
                ),
                dbc.Button(
                    "Re-run with selected nodes",
                    id="rerun-btn",
                    color="secondary",
                    className="mt-2",
                ),
                dcc.Loading(html.Div(id="rerun-output"), type="circle"),
            ],
        ),
    ],
    fluid=True,
)


def _highlight_answer(answer: str, claims: list[dict]):
    sorted_claims = sorted(claims, key=lambda c: c["start"])
    parts = []
    cursor = 0
    for c in sorted_claims:
        s, e = c["start"], c["end"]
        if s > cursor:
            parts.append(html.Span(answer[cursor:s]))
        parts.append(
            html.Span(
                answer[s:e],
                title=f"{c['label']}: {c['claim']}",
                style={
                    "backgroundColor": _SPAN_COLORS.get(c["label"], "#eee"),
                    "borderRadius": "3px",
                    "padding": "1px 3px",
                    "cursor": "help",
                },
            )
        )
        cursor = e
    if cursor < len(answer):
        parts.append(html.Span(answer[cursor:]))
    return html.P(parts)


def _claims_list(claims):
    return dbc.ListGroup(
        [
            dbc.ListGroupItem(
                [
                    html.Strong(f"[{c['label'].upper()}] "),
                    f"{c['claim']}",
                    html.Small(
                        f"  span: ({c['start']}, {c['end']})",
                        className="text-muted ms-2",
                    ),
                ],
                color="success"
                if c["label"] == "supported"
                else "warning"
                if c["label"] == "inferred"
                else "danger",
            )
            for c in claims
        ]
    )


def _result_layout(result):
    return html.Div(
        [
            html.H5(f"Model: {result['answer_model']}"),
            html.Hr(),
            html.H6("Triples found:"),
            html.Pre(
                result["triples_prompt"] or "(none)",
                style={"fontSize": "0.8rem", "background": "#f8f9fa", "padding": "8px"},
            ),
            html.H6("Closed-book answer:"),
            _highlight_answer(result["answer_closed"], result["claims_closed"]),
            html.H6("Claims (closed-book):"),
            _claims_list(result["claims_closed"]),
            html.Hr(),
            html.H6("Grounded answer:"),
            _highlight_answer(result["answer_grounded"], result["claims_grounded"]),
            html.H6("Claims (grounded):"),
            _claims_list(result["claims_grounded"]),
        ]
    )


def _subgraph_to_elements(subgraph):
    elements = []
    for n in subgraph["nodes"]:
        elements.append({"data": {"id": n["id"], "label": n["label"]}})
    seen = set()
    for e in subgraph["edges"]:
        key = (e["subject"], e["predicate"], e["object"])
        if key not in seen:
            seen.add(key)
            elements.append(
                {
                    "data": {
                        "source": e["subject"],
                        "target": e["object"],
                        "label": e["predicate_label"],
                    }
                }
            )
    return elements


@callback(
    Output("output", "children"),
    Output("store", "data"),
    Output("graph-section", "style"),
    Output("cytoscape", "elements"),
    Input("run-btn", "n_clicks"),
    State("question-input", "value"),
    prevent_initial_call=True,
)
def on_run(n_clicks, question):
    if not question:
        return "Please enter a question.", None, {"display": "none"}, []

    result = run_pipeline(question)
    store_data = {"question": result["question"], "subgraph": result["subgraph"]}
    return (
        _result_layout(result),
        store_data,
        {"display": "block"},
        _subgraph_to_elements(result["subgraph"]),
    )


@callback(
    Output("rerun-output", "children"),
    Input("rerun-btn", "n_clicks"),
    State("cytoscape", "selectedNodeData"),
    State("store", "data"),
    prevent_initial_call=True,
)
def on_rerun(n_clicks, selected_nodes, store_data):
    if not store_data:
        return "Run the pipeline first."
    if not selected_nodes:
        return "Select at least one node in the graph first."

    selected_ids = {n["id"] for n in selected_nodes}
    full = store_data["subgraph"]
    filtered = {
        "nodes": [n for n in full["nodes"] if n["id"] in selected_ids],
        "edges": [
            e
            for e in full["edges"]
            if e["subject"] in selected_ids and e["object"] in selected_ids
        ],
    }

    result = run_pipeline(store_data["question"], subgraph=filtered)
    return html.Div(
        [
            html.H6(f"Re-run with {len(selected_ids)} selected node(s):"),
            _result_layout(result),
        ]
    )


if __name__ == "__main__":
    app.run(debug=True)
