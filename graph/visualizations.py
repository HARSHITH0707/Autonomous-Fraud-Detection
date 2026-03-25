# pyre-ignore-all-errors
from __future__ import annotations

"""
Visualization helpers. They render richer charts when plotting dependencies are
installed and otherwise degrade to informative no-ops.
"""

from core.compat import optional_import

matplotlib = optional_import("matplotlib")
if matplotlib is not None:
    matplotlib.use("Agg")
mpatches = optional_import("matplotlib.patches")
plt = optional_import("matplotlib.pyplot")
nx = optional_import("networkx")
pd = optional_import("pandas")
PLOTTING_AVAILABLE = all(module is not None for module in (matplotlib, mpatches, plt, nx, pd))


DARK = "#0d1117"
PANEL = "#21262d"
FRAUD = "#ff4444"
NORMAL = "#4488ff"
HUB = "#ffaa00"
DEVICE = "#aa44ff"
WHITE = "#e6edf3"
GREY = "#8b949e"


def _can_plot(label: str) -> bool:
    if PLOTTING_AVAILABLE:
        return True
    print(f"  [Viz] Plotting dependencies unavailable for {label}.")
    return False


def viz_fraud_rings(rings: list, save_path: str):
    if not rings:
        print("  [Viz] No fraud rings.")
        return
    if not _can_plot("fraud rings"):
        return

    show = min(6, len(rings))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows * 6), facecolor=DARK)
    axes = list(getattr(axes, "flat", [axes]))
    for idx, ax in enumerate(axes):
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        ring = rings[idx]
        members = ring.get("members", [])
        graph = nx.DiGraph()
        for index, member in enumerate(members):
            graph.add_edge(member, members[(index + 1) % len(members)])
        pos = nx.circular_layout(graph)
        nx.draw_networkx(graph, pos, ax=ax, node_color=FRAUD, edge_color=FRAUD, font_color=WHITE, node_size=900)
        ax.set_title(f"Ring #{idx + 1} | Total: ${ring.get('total', 0):,.0f}", color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_mule_chains(chains: list, save_path: str):
    if not chains:
        print("  [Viz] No mule chains.")
        return
    if not _can_plot("mule chains"):
        return

    show = min(5, len(chains))
    fig, axes = plt.subplots(show, 1, figsize=(20, show * 3.5), facecolor=DARK)
    if show == 1:
        axes = [axes]
    for idx, ax in enumerate(axes):
        ax.set_facecolor(PANEL)
        ax.axis("off")
        chain = chains[idx]
        nodes = chain.get("chain", [])
        graph = nx.DiGraph()
        pos = {node: (index, 0.5) for index, node in enumerate(nodes)}
        for index in range(len(nodes) - 1):
            graph.add_edge(nodes[index], nodes[index + 1])
        colors = [NORMAL if node == nodes[0] else FRAUD if node == nodes[-1] else HUB for node in nodes]
        nx.draw_networkx(graph, pos, ax=ax, node_color=colors, edge_color=FRAUD, font_color=WHITE, node_size=1200)
        ax.set_title(f"Chain #{idx + 1} | Hops: {chain.get('hops', 0)}", color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_coordinated_hubs(hubs: list, save_path: str):
    if not hubs:
        print("  [Viz] No hubs.")
        return
    if not _can_plot("coordinated hubs"):
        return

    show = min(6, len(hubs))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows * 6), facecolor=DARK)
    axes = list(getattr(axes, "flat", [axes]))
    for idx, ax in enumerate(axes):
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        hub = hubs[idx]
        graph = nx.DiGraph()
        graph.add_node(hub["hub"])
        for sender in hub.get("top_senders", []):
            graph.add_edge(sender, hub["hub"])
        pos = nx.shell_layout(graph)
        colors = [HUB if node == hub["hub"] else FRAUD for node in graph.nodes()]
        nx.draw_networkx(graph, pos, ax=ax, node_color=colors, edge_color=FRAUD, font_color=WHITE)
        ax.set_title(f"Hub #{idx + 1}: {hub['hub']}", color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_shared_devices(device_clusters: list, save_path: str):
    if not device_clusters:
        print("  [Viz] No device clusters.")
        return
    if not _can_plot("shared devices"):
        return

    show = min(6, len(device_clusters))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows * 5), facecolor=DARK)
    axes = list(getattr(axes, "flat", [axes]))
    for idx, ax in enumerate(axes):
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        cluster = device_clusters[idx]
        graph = nx.Graph()
        device_id = cluster["device"]
        graph.add_node(device_id)
        for account in cluster.get("accounts", []):
            graph.add_edge(device_id, account)
        pos = nx.shell_layout(graph)
        colors = [DEVICE if node == device_id else FRAUD for node in graph.nodes()]
        nx.draw_networkx(graph, pos, ax=ax, node_color=colors, edge_color=DEVICE, font_color=WHITE)
        ax.set_title(f"Device: {device_id[:20]}", color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_risk_scores(risk_rows: list, save_path: str):
    if not risk_rows:
        print("  [Viz] No risk scores.")
        return
    if not _can_plot("risk scores"):
        return

    frame = pd.DataFrame(risk_rows).head(20).sort_values("risk_score")
    fig, axes = plt.subplots(1, 2, figsize=(18, 8), facecolor=DARK)
    ax = axes[0]
    ax.set_facecolor(PANEL)
    ax.barh(frame["account"], frame["risk_score"], color=FRAUD)
    ax.tick_params(colors=GREY, labelsize=8)
    ax.set_title("Top Accounts by Risk Score", color=WHITE)
    ax = axes[1]
    ax.set_facecolor(PANEL)
    ax.barh(frame["account"], frame["fraud_sent"], color=FRAUD, label="Fraud Sent")
    ax.barh(frame["account"], frame["fraud_recv"], color=HUB, alpha=0.8, label="Fraud Received")
    ax.legend(facecolor=PANEL, labelcolor=WHITE)
    ax.tick_params(colors=GREY, labelsize=8)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_full_network(rings, chains, hubs, save_path: str):
    if not _can_plot("full network"):
        return

    graph = nx.DiGraph()
    node_colors = {}

    for ring in rings[:4]:
        members = ring.get("members", [])
        for index, member in enumerate(members):
            node_colors.setdefault(member, FRAUD)
            graph.add_edge(member, members[(index + 1) % len(members)])

    for chain in chains[:4]:
        nodes = chain.get("chain", [])
        for node in nodes:
            node_colors.setdefault(node, HUB)
        for index in range(len(nodes) - 1):
            graph.add_edge(nodes[index], nodes[index + 1])

    for hub in hubs[:4]:
        node_colors.setdefault(hub["hub"], HUB)
        for sender in hub.get("top_senders", [])[:5]:
            node_colors.setdefault(sender, NORMAL)
            graph.add_edge(sender, hub["hub"])

    if graph.number_of_nodes() == 0:
        print("  [Viz] Not enough data for combined network view.")
        return

    fig, ax = plt.subplots(figsize=(20, 16), facecolor=DARK)
    ax.set_facecolor(DARK)
    ax.axis("off")
    pos = nx.spring_layout(graph, seed=42, k=1.8)
    colors = [node_colors.get(node, NORMAL) for node in graph.nodes()]
    nx.draw_networkx(graph, pos, ax=ax, node_color=colors, edge_color=GREY, font_color=WHITE, node_size=700)
    legend_patches = [
        mpatches.Patch(color=FRAUD, label="Fraud Ring"),
        mpatches.Patch(color=HUB, label="Mule / Hub"),
        mpatches.Patch(color=NORMAL, label="Sender"),
    ]
    ax.legend(handles=legend_patches, loc="lower left", facecolor=PANEL, labelcolor=WHITE, fontsize=10, framealpha=0.9)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")
