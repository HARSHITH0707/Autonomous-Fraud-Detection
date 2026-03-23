"""
Fraud Visualisation Functions
Extracted from app.py — importable by MCP server and standalone scripts.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import pandas as pd

# ── palette ───────────────────────────────────────────────────────────────────
DARK   = "#0d1117"
MID    = "#161b22"
PANEL  = "#21262d"
FRAUD  = "#ff4444"
NORMAL = "#4488ff"
HUB    = "#ffaa00"
DEVICE = "#aa44ff"
IP_COL = "#44ffaa"
EDGE_F = "#ff666688"
EDGE_N = "#44448844"
WHITE  = "#e6edf3"
GREY   = "#8b949e"


def viz_fraud_rings(rings: list, save_path: str):
    if not rings:
        print("  [Viz] No fraud rings.")
        return
    show  = min(6, len(rings))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows*6), facecolor=DARK)
    fig.suptitle("FRAUD RINGS  |  Closed money-laundering loops",
                 color=WHITE, fontsize=14, fontweight="bold", y=1.01)
    axes = np.array(axes).flatten()
    for idx in range(len(axes)):
        ax = axes[idx]
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        ring    = rings[idx]
        members = ring["members"]
        n       = len(members)
        G       = nx.DiGraph()
        G.add_nodes_from(members)
        for i in range(n):
            G.add_edge(members[i], members[(i+1) % n])
        pos = nx.circular_layout(G)
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=FRAUD, width=2.5,
                               arrows=True, arrowsize=25,
                               connectionstyle="arc3,rad=0.1",
                               min_source_margin=20, min_target_margin=20)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=FRAUD, node_size=900,
                               edgecolors=WHITE, linewidths=1.5)
        nx.draw_networkx_labels(G, pos, ax=ax, font_color=WHITE, font_size=8, font_weight="bold")
        ax.set_title(f"Ring #{idx+1}  |  Size: {ring['size']}  |  Total: ${ring['total']:,.0f}",
                     color=GREY, fontsize=9, pad=8)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_mule_chains(chains: list, save_path: str):
    if not chains:
        print("  [Viz] No mule chains.")
        return
    show = min(5, len(chains))
    fig, axes = plt.subplots(show, 1, figsize=(20, show*3.5), facecolor=DARK)
    fig.suptitle("MULE ACCOUNT CHAINS  |  Stolen funds flow",
                 color=WHITE, fontsize=14, fontweight="bold")
    if show == 1:
        axes = [axes]
    for idx, ax in enumerate(axes):
        ax.set_facecolor(PANEL)
        ax.axis("off")
        if idx >= show:
            continue
        chain   = chains[idx]
        nodes   = chain["chain"]
        amounts = chain["amounts"]
        n       = len(nodes)
        G = nx.DiGraph()
        pos = {}
        for i, node in enumerate(nodes):
            G.add_node(node)
            pos[node] = (i / max(n-1, 1), 0.5)
        for i in range(n-1):
            G.add_edge(nodes[i], nodes[i+1])
        source = nodes[0] if nodes else None
        dest   = nodes[-1] if nodes else None
        colors = [NORMAL if node == source else FRAUD if node == dest else HUB for node in list(G.nodes())]
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=FRAUD, width=3,
                               arrows=True, arrowsize=30,
                               min_source_margin=25, min_target_margin=25)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors, node_size=1200,
                               edgecolors=WHITE, linewidths=1.5)
        nx.draw_networkx_labels(G, pos, ax=ax, font_color=WHITE, font_size=7, font_weight="bold")
        edge_labels = {(nodes[i], nodes[i+1]): f"${amounts[i]:,.0f}"
                       for i in range(min(len(amounts), n-1))}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=ax,
                                     font_color=HUB, font_size=8,
                                     bbox=dict(boxstyle="round,pad=0.2", facecolor=PANEL, alpha=0.8))
        ax.set_title(f"Chain #{idx+1}  |  Hops: {chain['hops']}  |  {chain['source']} → ... → {chain['dest']}",
                     color=GREY, fontsize=9)
    legend_patches = [
        mpatches.Patch(color=NORMAL, label="Victim / Source"),
        mpatches.Patch(color=HUB,   label="Intermediary Mule"),
        mpatches.Patch(color=FRAUD, label="Final Destination"),
    ]
    fig.legend(handles=legend_patches, loc="lower center", ncol=3,
               facecolor=PANEL, labelcolor=WHITE, fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, -0.01))
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_coordinated_hubs(hubs: list, save_path: str):
    if not hubs:
        print("  [Viz] No hubs.")
        return
    show  = min(6, len(hubs))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows*6), facecolor=DARK)
    fig.suptitle("COORDINATED TRANSFER HUBS  |  Many senders → one hub",
                 color=WHITE, fontsize=14, fontweight="bold", y=1.01)
    axes = np.array(axes).flatten()
    for idx in range(len(axes)):
        ax = axes[idx]
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        hub     = hubs[idx]
        hub_id  = hub["hub"]
        senders = hub["top_senders"]
        G = nx.DiGraph()
        G.add_node(hub_id)
        G.add_nodes_from(senders)
        for s in senders:
            G.add_edge(s, hub_id)
        pos    = nx.shell_layout(G, nlist=[senders, [hub_id]])
        colors = [HUB if n == hub_id else FRAUD for n in G.nodes()]
        sizes  = [1800 if n == hub_id else 700  for n in G.nodes()]
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=EDGE_F, width=2,
                               arrows=True, arrowsize=20,
                               min_source_margin=15, min_target_margin=20)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors, node_size=sizes,
                               edgecolors=WHITE, linewidths=1.2)
        nx.draw_networkx_labels(G, pos, ax=ax, font_color=WHITE, font_size=7, font_weight="bold")
        ax.set_title(f"Hub #{idx+1}: {hub_id}\nSenders: {hub['senders']}  |  Total: ${hub['total']:,.0f}",
                     color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_shared_devices(device_clusters: list, save_path: str):
    if not device_clusters:
        print("  [Viz] No device clusters.")
        return
    show  = min(6, len(device_clusters))
    ncols = 3
    nrows = (show + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows*5), facecolor=DARK)
    fig.suptitle("SHARED DEVICE CLUSTERS  |  Compromised infrastructure",
                 color=WHITE, fontsize=14, fontweight="bold", y=1.01)
    axes = np.array(axes).flatten()
    for idx in range(len(axes)):
        ax = axes[idx]
        ax.set_facecolor(PANEL if idx < show else DARK)
        ax.axis("off")
        if idx >= show:
            continue
        cluster  = device_clusters[idx]
        dev_id   = cluster["device"]
        accounts = cluster["accounts"]
        G = nx.Graph()
        G.add_node(dev_id, kind="device")
        for a in accounts:
            G.add_node(a, kind="account")
            G.add_edge(dev_id, a)
        pos    = nx.shell_layout(G, nlist=[[dev_id], accounts])
        colors = [DEVICE if G.nodes[n].get("kind") == "device" else FRAUD for n in G.nodes()]
        sizes  = [1500  if G.nodes[n].get("kind") == "device" else 600   for n in G.nodes()]
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=DEVICE+"88", width=1.8)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors, node_size=sizes,
                               edgecolors=WHITE, linewidths=1)
        nx.draw_networkx_labels(G, pos, ax=ax, font_color=WHITE, font_size=7, font_weight="bold")
        ax.set_title(f"Device: {dev_id[:20]}\nShared by {cluster['cnt']} accounts",
                     color=GREY, fontsize=9)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_risk_scores(risk_rows: list, save_path: str):
    if not risk_rows:
        print("  [Viz] No risk scores.")
        return
    df = pd.DataFrame(risk_rows).head(20).sort_values("risk_score")
    fig, axes = plt.subplots(1, 2, figsize=(18, 8), facecolor=DARK)
    fig.suptitle("HIGH-RISK ACCOUNT SCORING  |  Graph Features from Neo4j",
                 color=WHITE, fontsize=14, fontweight="bold")
    ax = axes[0]
    ax.set_facecolor(PANEL)
    q75, q50 = df["risk_score"].quantile(0.75), df["risk_score"].quantile(0.5)
    colors = [FRAUD if s >= q75 else HUB if s >= q50 else NORMAL for s in df["risk_score"]]
    bars = ax.barh(df["account"], df["risk_score"], color=colors, edgecolor="#ffffff11", height=0.7)
    for bar, val in zip(bars, df["risk_score"]):
        ax.text(val + 0.2, bar.get_y() + bar.get_height()/2,
                f"{val:.0f}", va="center", color=WHITE, fontsize=8)
    ax.set_xlabel("Composite Risk Score", color=GREY, fontsize=9)
    ax.set_title("Top Accounts by Risk Score", color=WHITE, fontsize=11)
    ax.tick_params(colors=GREY, labelsize=8)
    ax2 = axes[1]
    ax2.set_facecolor(PANEL)
    x = np.arange(len(df))
    ax2.barh(x, df["fraud_sent"], 0.6, label="Fraud Sent",     color=FRAUD,  alpha=0.9)
    ax2.barh(x, df["fraud_recv"], 0.6, left=df["fraud_sent"],  label="Fraud Received", color=HUB, alpha=0.9)
    ax2.barh(x, df["shared_dev"], 0.6,
             left=df["fraud_sent"]+df["fraud_recv"],
             label="Shared Devices", color=DEVICE, alpha=0.9)
    ax2.set_yticks(x)
    ax2.set_yticklabels(df["account"], fontsize=8, color=GREY)
    ax2.set_xlabel("Signal Counts", color=GREY, fontsize=9)
    ax2.set_title("Risk Signal Breakdown", color=WHITE, fontsize=11)
    ax2.legend(facecolor=MID, labelcolor=WHITE, fontsize=8, loc="lower right")
    ax2.tick_params(colors=GREY, labelsize=8)
    plt.tight_layout(pad=2)
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")


def viz_full_network(rings, chains, hubs, save_path: str):
    G         = nx.DiGraph()
    node_type = {}
    edge_type = {}

    for ring in rings[:4]:
        m = ring["members"]
        for node in m:
            G.add_node(node); node_type.setdefault(node, "ring")
        for i in range(len(m)):
            u, v = m[i], m[(i+1) % len(m)]
            G.add_edge(u, v); edge_type[(u, v)] = "ring"

    for chain in chains[:4]:
        c = chain["chain"]
        for node in c:
            G.add_node(node); node_type.setdefault(node, "chain")
        for i in range(len(c)-1):
            G.add_edge(c[i], c[i+1]); edge_type[(c[i], c[i+1])] = "chain"

    for hub in hubs[:4]:
        G.add_node(hub["hub"]); node_type.setdefault(hub["hub"], "hub")
        for s in hub["top_senders"][:5]:
            G.add_node(s); node_type.setdefault(s, "sender")
            G.add_edge(s, hub["hub"]); edge_type[(s, hub["hub"])] = "hub"

    if G.number_of_nodes() == 0:
        print("  [Viz] Not enough data for combined network view.")
        return

    fig, ax = plt.subplots(figsize=(20, 16), facecolor=DARK)
    ax.set_facecolor(DARK); ax.axis("off")
    fig.suptitle("COMBINED FRAUD NETWORK  |  All Patterns",
                 color=WHITE, fontsize=14, fontweight="bold")
    pos = nx.spring_layout(G, seed=42, k=1.8)
    type_color  = {"ring": FRAUD, "chain": HUB, "hub": "#ffdd00", "sender": NORMAL}
    type_size   = {"ring": 800,   "chain": 700, "hub": 1400,      "sender": 500}
    etype_color = {"ring": FRAUD, "chain": HUB+"aa", "hub": "#ffdd0088"}
    ncolors = [type_color.get(node_type.get(n, "sender"), GREY) for n in G.nodes()]
    nsizes  = [type_size .get(node_type.get(n, "sender"), 500)  for n in G.nodes()]
    ecolors = [etype_color.get(edge_type.get((u,v), "hub"), GREY) for u, v in G.edges()]
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=ecolors, width=1.8,
                           arrows=True, arrowsize=15, connectionstyle="arc3,rad=0.1",
                           min_source_margin=12, min_target_margin=12)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=ncolors, node_size=nsizes,
                           edgecolors=WHITE, linewidths=0.8)
    nx.draw_networkx_labels(G, pos, ax=ax, font_color=WHITE, font_size=6, font_weight="bold")
    legend_patches = [
        mpatches.Patch(color=FRAUD,     label="Fraud Ring node"),
        mpatches.Patch(color=HUB,       label="Mule Chain node"),
        mpatches.Patch(color="#ffdd00", label="Hub (coordinator)"),
        mpatches.Patch(color=NORMAL,    label="Sender account"),
    ]
    ax.legend(handles=legend_patches, loc="lower left",
              facecolor=PANEL, labelcolor=WHITE, fontsize=10, framealpha=0.9)
    ax.text(0.99, 0.01,
            f"Nodes: {G.number_of_nodes()}  |  Edges: {G.number_of_edges()}",
            transform=ax.transAxes, color=GREY, fontsize=9, ha="right")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print(f"  Saved  -->  {save_path}")
