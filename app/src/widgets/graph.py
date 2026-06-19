import dash_cytoscape as cyto
from collections import defaultdict
from src.Dataset import Dataset

data = Dataset.data




my_stylesheet=[
                {
                    "selector": "node",
                    "style": {
                        "label": "data(label)",
                        "width": "mapData(degree, 1, 15, 20, 60)",
                        "height": "mapData(degree, 1, 15, 20, 60)",
                        "background-color": "#0074D9",
                        "text-outline-color": "#fff",
                        "text-outline-width": 2,
                        "font-size":10,
                        "color": "#222",   
                    },
                },
                {
                    "selector": "edge",
                    "style": {
                        "width": "mapData(weight, 1, 5, 1, 6)",
                        "line-color": "#bbb",
                        "curve-style": "bezier",
                    },
                },
            ]
my_layout = {
                "name": "cose",
                "animate": False,
                "nodeRepulsion": 80000,
                "idealEdgeLength": 100,
            }



def create_graph(selected_rows=None):
    return cyto.Cytoscape(
        id="graph",
        elements=build_elements(selected_rows),
        style={"width": "100%", "height": "100%"},
        className="stretchy-widget border-widget",
        layout=my_layout,
        stylesheet=my_stylesheet,
            
    )
def build_elements(selected_rows):
    if not selected_rows:
        bird_names = set(Dataset.data["class_name"].unique())
    else:
        bird_names = {row["class_name"] for row in selected_rows}

    edge_weights = defaultdict(int)

    for bird in bird_names:
        bird_sep = bird.split()
        for i in range (len(bird_sep)):
            for j in range(i+1, len(bird_sep)):
                word1, word2 = bird_sep[i], bird_sep[j]
                word1, word2 = sorted([word1, word2])
                edge_weights[(word1, word2)] += 1


    node_degree = defaultdict(int)

    for word1, word2 in edge_weights: 
        node_degree[word1] += 1
        node_degree[word2] += 1

    elements = [] 

    for word, degree in node_degree.items():
        elements.append({"data":{"id": word, "label" : word, "degree": degree}})
    
    for (word1, word2), weight in edge_weights.items():
        elements.append({"data":{"id" : f"{word1}_{word2}", "source": word1, "target": word2, "weight": weight}})

    return elements
    

