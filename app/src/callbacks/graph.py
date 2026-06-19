from dash import Input, Output, callback, State


@callback(
    Output("grid", "selectedRows", allow_duplicate=True),
    Input("graph", "tapNodeData"),
    prevent_initial_call=True,
)
def graph_is_clicked(tap_node_data):
    print('Graph is clicked')
    
    if tap_node_data is None:
        return []
    
    word = tap_node_data['label']  
    print(word)
    return {'function': f'params.data.class_name.includes("{word}")'}

