import dash
import numpy
from dash import Output, Input, callback, Patch, State
from dash.exceptions import PreventUpdate

from src import config
from src.Dataset import Dataset
from src.widgets import graph, gallery, scatterplot, histogram, heatmap, wordcloud, agent


@callback(
    [Output('wordcloud', 'list'),
     Output("gallery", "children"),
     Output("scatterplot", "figure"),
     Output("graph", "elements"), 
     Output('histogram', 'figure'),
     Output("heatmap", "figure"),
     Output("characteristics-description", 'children'),
     Output("generated-image", 'src')
    ],
    [Input("grid", "selectedRows"),
     Input("grid", "rowData")],
    State('scatterplot', 'figure'),
)

def table_row_is_selected(selected_rows, added_rows, scatterplot_fig):
    if type(selected_rows) is dict:
        raise PreventUpdate()

    print('Table row selected')

    data_selected = scatterplot.get_data_selected_on_scatterplot(scatterplot_fig)
    scatterplot_fig['layout']['images'] = []

    if selected_rows:
        classes_in_scatterplot = data_selected['class_name'].unique()
        selected_classes = set(map(lambda row: row['class_id'], selected_rows))
        data_selected = data_selected[data_selected['class_id'].isin(selected_classes)]
        scatterplot.highlight_class_on_scatterplot(scatterplot_fig, selected_classes)
        count_in_section = numpy.array([row['count_in_selection'] for row in selected_rows])
        wordcloud_data = sorted([[row['class_name'], count] for row, count in zip(
            selected_rows,
            wordcloud.wordcloud_weight_rescale(
                count_in_section,
                1,
                count_in_section.max())
        )], key=lambda x: x[1], reverse=True)
        print(wordcloud_data)
        graph_elements = graph.build_elements(selected_rows)
    else:
        group_by_count = (data_selected.groupby(['class_id', 'class_name'])['class_id']
                          .agg('count')
                          .to_frame('count_in_selection')
                          .reset_index())

        group_by_count['count_in_selection'] = wordcloud.wordcloud_weight_rescale(
            group_by_count['count_in_selection'],
            1,
            Dataset.class_count().max()
        )
        wordcloud_data = group_by_count[['class_name', 'count_in_selection']].sort_values(by='count_in_selection', ascending=False).values
        scatterplot.highlight_class_on_scatterplot(scatterplot_fig, None)
        graph_input = [{"class_name": cn} for cn in data_selected["class_name"].unique()]
        graph_elements = graph.build_elements(graph_input)  
    sample_data = data_selected.sample(min(len(data_selected), config.IMAGE_GALLERY_SIZE), random_state=1)
    gallery_children = gallery.create_gallery_children(sample_data['image_path'].values, sample_data['class_name'].values)

    histogram_fig = histogram.draw_histogram(selected_data=data_selected)

    heatmap_fig = heatmap.draw_heatmap(data_selected)

    characteristics_description = agent.get_top_characteristics(data_selected)

    return wordcloud_data, gallery_children, scatterplot_fig, graph_elements, histogram_fig, heatmap_fig, characteristics_description, ''
