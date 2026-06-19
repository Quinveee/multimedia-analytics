import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, callback, dcc, html

from src.pipeline import run

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

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
        dcc.Loading(html.Div(id="output"), type="circle"),
    ],
    fluid=True,
)

_SPAN_COLORS = {
    "supported": "#d4edda",
    "inferred": "#fff3cd",
    "unverifiable": "#f8d7da",
}


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


@callback(
    Output("output", "children"),
    Input("run-btn", "n_clicks"),
    State("question-input", "value"),
    prevent_initial_call=True,
)
def on_run(n_clicks, question):
    if not question:
        return "Please enter a question."

    result = run(question)

    def claims_list(claims):
        return dbc.ListGroup([
            dbc.ListGroupItem(
                [
                    html.Strong(f"[{c['label'].upper()}] "),
                    f"{c['claim']}",
                    html.Small(f"  span: ({c['start']}, {c['end']})", className="text-muted ms-2"),
                ],
                color="success" if c["label"] == "supported"
                else "warning" if c["label"] == "inferred"
                else "danger",
            )
            for c in claims
        ])

    return html.Div(
        [
            html.H5(f"Model: {result['answer_model']}"),
            html.Hr(),
            html.H6("Triples found:"),
            html.Pre(
                result["triples"] or "(none)",
                style={"fontSize": "0.8rem", "background": "#f8f9fa", "padding": "8px"},
            ),
            html.H6("Closed-book answer (hover to see claim):"),
            _highlight_answer(result["answer_closed"], result["claims_closed"]),
            html.H6("Claims (closed-book):"),
            claims_list(result["claims_closed"]),
            html.Hr(),
            html.H6("Grounded answer (hover to see claim):"),
            _highlight_answer(result["answer_grounded"], result["claims_grounded"]),
            html.H6("Claims (grounded):"),
            claims_list(result["claims_grounded"]),
        ]
    )


if __name__ == "__main__":
    app.run(debug=True)
