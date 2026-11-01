from collections import Counter
from src.data_loader import load_all_data
from src.supply_chain_graph import get_supply_chain_graph

data = load_all_data(verbose=False)

for name, df in data.items():
    print("\n==", name, df.shape)
    print(df.dtypes.to_string())
    print(df.head(3).to_string())

g = get_supply_chain_graph(data)

print("\nNODE TYPES:")
print(Counter(d.get("node_type") for _, d in g.nodes(data=True)))

print("\nEDGE TYPES:")
print(Counter(
    (g.nodes[u].get("node_type"),
     g.nodes[v].get("node_type"),
     tuple(sorted(d)))
    for u, v, d in g.edges(data=True)
))