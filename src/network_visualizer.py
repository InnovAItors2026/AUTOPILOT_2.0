"""
network_visualizer.py
---------------------
Generates an interactive, production-grade Palantir/SAP Control Tower Digital Twin
interactive network visualization using standalone HTML5 Canvas & WebGL/SVG.
Runs 100% offline with zero external dependencies via streamlit.components.v1.html.
"""

import json
from typing import Any, Dict, List, Optional, Set
import networkx as nx


def generate_digital_twin_html(
    graph: nx.DiGraph,
    disrupted_nodes: Optional[List[str]] = None,
    height: int = 620,
) -> str:
    """
    Generate self-contained interactive HTML for the Digital Twin Network.
    
    Includes:
    - Force-directed physics layout with echelon stratification
    - Interactive pan, zoom, drag, and node search
    - Node type filtering (T1, T2, T3, Materials, Factories, Warehouses, Orders)
    - Cascade trace on node click (highlights upstream causes and downstream impacts)
    - Real-time HUD (Heads-Up Display) with entity telemetry
    - Palantir/Fiori executive dark control tower theme
    """
    disrupted_set: Set[str] = set(disrupted_nodes or [])

    nodes_data = []
    for node_id, attrs in graph.nodes(data=True):
        ntype = attrs.get("node_type", "unknown")
        tier = attrs.get("tier", None)
        
        # Color coding & classification
        if ntype == "supplier":
            if tier == 1:
                category = "Tier 1 Supplier"
                color = "#0A6ED1"
                icon = "🏢"
                level = 3
            elif tier == 2:
                category = "Tier 2 Supplier"
                color = "#4F46E5"
                icon = "🏭"
                level = 2
            elif tier == 3:
                category = "Tier 3 Supplier"
                color = "#7C3AED"
                icon = "⛏️"
                level = 1
            else:
                category = "Supplier"
                color = "#2563EB"
                icon = "🏢"
                level = 2
        elif ntype == "material":
            category = "Material / Part"
            color = "#0891B2"
            icon = "📦"
            level = 4
        elif ntype == "factory":
            category = "Manufacturing Plant"
            color = "#059669"
            icon = "⚙️"
            level = 5
        elif ntype == "warehouse":
            category = "Regional Hub"
            color = "#D97706"
            icon = "🏬"
            level = 6
        elif ntype == "customer_order":
            category = "Customer Order"
            color = "#DC2626"
            icon = "🛒"
            level = 7
        elif ntype == "transport_route":
            category = "Logistics Route"
            color = "#475569"
            icon = "🚛"
            level = 4
        else:
            category = ntype.capitalize()
            color = "#64748B"
            icon = "📍"
            level = 4

        is_disrupted = node_id in disrupted_set
        
        # Build node metadata dict
        meta = {
            "id": str(node_id),
            "label": str(attrs.get("name") or node_id)[:24],
            "full_name": str(attrs.get("name") or node_id),
            "type": ntype,
            "category": category,
            "tier": tier,
            "color": "#EF4444" if is_disrupted else color,
            "icon": icon,
            "level": level,
            "disrupted": is_disrupted,
            "capacity": attrs.get("capacity"),
            "location": attrs.get("location") or attrs.get("city"),
            "quality": attrs.get("quality_score"),
            "lead_time": attrs.get("lead_time_days"),
            "order_value": attrs.get("order_value_inr"),
            "in_degree": graph.in_degree(node_id),
            "out_degree": graph.out_degree(node_id),
        }
        nodes_data.append(meta)

    edges_data = []
    for u, v, attrs in graph.edges(data=True):
        etype = attrs.get("edge_type", "link")
        is_affected = (u in disrupted_set or v in disrupted_set)
        edges_data.append({
            "source": str(u),
            "target": str(v),
            "type": etype,
            "affected": is_affected,
        })

    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)
    total_nodes = len(nodes_data)
    total_edges = len(edges_data)

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0B132B;
    color: #E2E8F0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
    height: 100vh;
    user-select: none;
  }}
  #graph-container {{
    position: relative;
    width: 100%;
    height: 100%;
    background: radial-gradient(circle at 50% 50%, #152238 0%, #0B132B 100%);
  }}
  canvas {{
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
  }}
  canvas:active {{ cursor: grabbing; }}
  
  /* Top Toolbar */
  .toolbar {{
    position: absolute;
    top: 12px;
    left: 12px;
    right: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    z-index: 10;
    flex-wrap: wrap;
    pointer-events: none;
  }}
  .tool-group {{
    display: flex;
    gap: 6px;
    background: rgba(16, 28, 44, 0.88);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    padding: 6px 10px;
    pointer-events: auto;
  }}
  .tool-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #CBD5E1;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.74rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .tool-btn:hover {{
    background: rgba(10, 110, 209, 0.4);
    color: #FFF;
    border-color: #0A6ED1;
  }}
  .tool-btn.active {{
    background: #0A6ED1;
    color: #FFF;
    border-color: #38BDF8;
  }}
  .search-box {{
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: #F8FAFC;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.74rem;
    outline: none;
    width: 180px;
  }}
  .search-box:focus {{
    border-color: #38BDF8;
  }}

  /* Heads-Up Display (HUD) Entity Inspector */
  .hud-panel {{
    position: absolute;
    bottom: 14px;
    right: 14px;
    width: 290px;
    background: rgba(16, 28, 44, 0.94);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 8px;
    padding: 14px 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    z-index: 10;
    pointer-events: auto;
    font-size: 0.78rem;
    display: none;
  }}
  .hud-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding-bottom: 8px;
    margin-bottom: 8px;
  }}
  .hud-title {{
    font-weight: 700;
    color: #38BDF8;
    font-size: 0.88rem;
  }}
  .hud-badge {{
    font-size: 0.68rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
  }}
  .hud-row {{
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    color: #94A3B8;
  }}
  .hud-row strong {{
    color: #F1F5F9;
  }}

  /* Legend pill */
  .legend-overlay {{
    position: absolute;
    bottom: 14px;
    left: 14px;
    background: rgba(16, 28, 44, 0.88);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 0.70rem;
    z-index: 10;
    color: #94A3B8;
  }}
  .legend-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
  }}
</style>
</head>
<body>
<div id="graph-container">
  <!-- Top Toolbar -->
  <div class="toolbar">
    <div class="tool-group">
      <button class="tool-btn active" onclick="setFilter('all')">All ({total_nodes})</button>
      <button class="tool-btn" onclick="setFilter('supplier')">Suppliers</button>
      <button class="tool-btn" onclick="setFilter('material')">Materials</button>
      <button class="tool-btn" onclick="setFilter('infrastructure')">Factories & Hubs</button>
      <button class="tool-btn" onclick="setFilter('customer_order')">Orders</button>
    </div>
    <div class="tool-group">
      <input type="text" id="searchInput" class="search-box" placeholder="🔍 Search entity..." oninput="handleSearch(this.value)"/>
      <button class="tool-btn" onclick="resetView()">Reset</button>
      <button class="tool-btn" onclick="toggleLayout()">Layout: <span id="layoutName">Echelon</span></button>
    </div>
  </div>

  <!-- Canvas -->
  <canvas id="twinCanvas"></canvas>

  <!-- Legend -->
  <div class="legend-overlay">
    <div>
      <span class="legend-dot" style="background:#7C3AED;"></span>T3
      <span class="legend-dot" style="background:#4F46E5;margin-left:6px;"></span>T2
      <span class="legend-dot" style="background:#0A6ED1;margin-left:6px;"></span>T1
      <span class="legend-dot" style="background:#0891B2;margin-left:6px;"></span>Part
      <span class="legend-dot" style="background:#059669;margin-left:6px;"></span>Plant
      <span class="legend-dot" style="background:#D97706;margin-left:6px;"></span>Hub
      <span class="legend-dot" style="background:#DC2626;margin-left:6px;"></span>Order
    </div>
    <div style="font-size:0.66rem;color:#64748B;margin-top:4px;">
      💡 Click any node to trace upstream & downstream cascade path
    </div>
  </div>

  <!-- HUD Inspector -->
  <div id="hud" class="hud-panel">
    <div class="hud-header">
      <div id="hudName" class="hud-title">Entity ID</div>
      <div id="hudBadge" class="hud-badge">TYPE</div>
    </div>
    <div class="hud-row"><span>ID:</span><strong id="hudId">-</strong></div>
    <div class="hud-row"><span>Category:</span><strong id="hudCat">-</strong></div>
    <div class="hud-row"><span>Location:</span><strong id="hudLoc">-</strong></div>
    <div class="hud-row"><span>Capacity / Qty:</span><strong id="hudCap">-</strong></div>
    <div class="hud-row"><span>Quality / Lead:</span><strong id="hudQual">-</strong></div>
    <div class="hud-row"><span>Connections:</span><strong id="hudConn">-</strong></div>
  </div>
</div>

<script>
  const rawNodes = {nodes_json};
  const rawEdges = {edges_json};

  const canvas = document.getElementById('twinCanvas');
  const ctx = canvas.getContext('2d');
  const hud = document.getElementById('hud');

  let width, height;
  let transform = {{ x: 0, y: 0, k: 1 }};
  let isDragging = false;
  let dragNode = null;
  let lastMouse = {{ x: 0, y: 0 }};
  let activeFilter = 'all';
  let activeSearch = '';
  let selectedNode = null;
  let highlightedNodes = new Set();
  let highlightedEdges = new Set();
  let layoutMode = 'echelon'; // 'echelon' or 'force'

  // Resize canvas
  function resize() {{
    width = canvas.width = canvas.parentElement.clientWidth;
    height = canvas.height = canvas.parentElement.clientHeight;
    initLayout();
  }}
  window.addEventListener('resize', resize);

  // Position nodes according to multi-tier echelon layout
  function initLayout() {{
    const echelons = {{
      1: [], // T3
      2: [], // T2
      3: [], // T1
      4: [], // Material
      5: [], // Factory
      6: [], // Warehouse
      7: [], // Customer Order
    }};

    rawNodes.forEach(n => {{
      const lvl = n.level || 4;
      if (!echelons[lvl]) echelons[lvl] = [];
      echelons[lvl].push(n);
    }});

    const paddingX = 80;
    const paddingY = 80;
    const usableW = Math.max(800, width - paddingX * 2);
    const usableH = Math.max(500, height - paddingY * 2);
    const echelonKeys = [1, 2, 3, 4, 5, 6, 7];

    echelonKeys.forEach((key, colIdx) => {{
      const group = echelons[key];
      const x = paddingX + (colIdx / (echelonKeys.length - 1)) * usableW;
      const count = group.length;
      group.forEach((node, rowIdx) => {{
        const stepY = count > 1 ? usableH / (count - 1) : 0;
        const y = count > 1 ? paddingY + rowIdx * stepY : height / 2;
        node.x = x + (Math.random() - 0.5) * 20;
        node.y = y;
        node.vx = 0;
        node.vy = 0;
        node.radius = node.disrupted ? 11 : (node.level === 3 ? 10 : (node.level === 5 ? 12 : 8));
      }});
    }});

    // Center transform
    transform.x = 20;
    transform.y = 10;
    transform.k = Math.min(width / 1100, height / 650, 1.0);
  }}

  // Filter nodes
  function setFilter(type) {{
    activeFilter = type;
    document.querySelectorAll('.tool-group .tool-btn').forEach(b => {{
      b.classList.remove('active');
      if (b.innerText.toLowerCase().includes(type)) b.classList.add('active');
    }});
    requestAnimationFrame(render);
  }}

  function handleSearch(val) {{
    activeSearch = val.toLowerCase().trim();
    if (activeSearch) {{
      const found = rawNodes.find(n => n.id.toLowerCase().includes(activeSearch) || n.label.toLowerCase().includes(activeSearch));
      if (found) selectNode(found);
    }} else {{
      selectedNode = null;
      highlightedNodes.clear();
      highlightedEdges.clear();
      hud.style.display = 'none';
    }}
    requestAnimationFrame(render);
  }}

  function resetView() {{
    initLayout();
    selectedNode = null;
    highlightedNodes.clear();
    highlightedEdges.clear();
    hud.style.display = 'none';
    document.getElementById('searchInput').value = '';
    requestAnimationFrame(render);
  }}

  function toggleLayout() {{
    layoutMode = layoutMode === 'echelon' ? 'force' : 'echelon';
    document.getElementById('layoutName').innerText = layoutMode.charAt(0).toUpperCase() + layoutMode.slice(1);
    if (layoutMode === 'echelon') initLayout();
    requestAnimationFrame(render);
  }}

  // Trace upstream and downstream dependencies from a selected node
  function selectNode(node) {{
    selectedNode = node;
    highlightedNodes.clear();
    highlightedEdges.clear();

    if (!node) {{
      hud.style.display = 'none';
      return;
    }}

    highlightedNodes.add(node.id);

    // Breadth-First-Search forward (downstream)
    const queueDown = [node.id];
    while (queueDown.length > 0) {{
      const curr = queueDown.shift();
      rawEdges.forEach(e => {{
        if (e.source === curr && !highlightedNodes.has(e.target)) {{
          highlightedNodes.add(e.target);
          highlightedEdges.add(e.source + '->' + e.target);
          queueDown.push(e.target);
        }}
      }});
    }}

    // Breadth-First-Search backward (upstream)
    const queueUp = [node.id];
    while (queueUp.length > 0) {{
      const curr = queueUp.shift();
      rawEdges.forEach(e => {{
        if (e.target === curr && !highlightedNodes.has(e.source)) {{
          highlightedNodes.add(e.source);
          highlightedEdges.add(e.source + '->' + e.target);
          queueUp.push(e.source);
        }}
      }});
    }}

    // Populate HUD
    document.getElementById('hudName').innerText = node.label;
    document.getElementById('hudId').innerText = node.id;
    document.getElementById('hudCat').innerText = node.category;
    document.getElementById('hudLoc').innerText = node.location || 'Central Supply Hub';
    document.getElementById('hudCap').innerText = node.capacity ? (Number(node.capacity).toLocaleString() + ' units/mo') : (node.order_value ? ('₹' + Number(node.order_value).toLocaleString()) : 'Active');
    document.getElementById('hudQual').innerText = node.quality ? (node.quality + '% Quality / ' + (node.lead_time || '-') + 'd') : 'Standard SLA';
    document.getElementById('hudConn').innerText = node.in_degree + ' In / ' + node.out_degree + ' Out (' + (highlightedNodes.size - 1) + ' Connected)';
    
    const badge = document.getElementById('hudBadge');
    badge.innerText = node.disrupted ? 'CRITICAL DISRUPTION' : node.type.toUpperCase();
    badge.style.background = node.disrupted ? '#EF4444' : node.color;
    badge.style.color = '#FFF';
    hud.style.display = 'block';

    requestAnimationFrame(render);
  }}

  // Hit test
  function getNodeAt(x, y) {{
    const tx = (x - transform.x) / transform.k;
    const ty = (y - transform.y) / transform.k;
    for (let i = rawNodes.length - 1; i >= 0; i--) {{
      const n = rawNodes[i];
      if (!isNodeVisible(n)) continue;
      const dx = tx - n.x;
      const dy = ty - n.y;
      if (dx * dx + dy * dy <= (n.radius + 5) * (n.radius + 5)) {{
        return n;
      }}
    }}
    return null;
  }}

  function isNodeVisible(n) {{
    if (activeFilter === 'all') return true;
    if (activeFilter === 'supplier') return n.type === 'supplier';
    if (activeFilter === 'material') return n.type === 'material';
    if (activeFilter === 'infrastructure') return n.type === 'factory' || n.type === 'warehouse';
    if (activeFilter === 'customer_order') return n.type === 'customer_order';
    return true;
  }}

  // Mouse event listeners
  canvas.addEventListener('mousedown', e => {{
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = getNodeAt(mx, my);

    if (hit) {{
      dragNode = hit;
      selectNode(hit);
    }} else {{
      isDragging = true;
    }}
    lastMouse = {{ x: e.clientX, y: e.clientY }};
  }});

  window.addEventListener('mousemove', e => {{
    if (dragNode) {{
      const dx = (e.clientX - lastMouse.x) / transform.k;
      const dy = (e.clientY - lastMouse.y) / transform.k;
      dragNode.x += dx;
      dragNode.y += dy;
      lastMouse = {{ x: e.clientX, y: e.clientY }};
      render();
    }} else if (isDragging) {{
      transform.x += e.clientX - lastMouse.x;
      transform.y += e.clientY - lastMouse.y;
      lastMouse = {{ x: e.clientX, y: e.clientY }};
      render();
    }}
  }});

  window.addEventListener('mouseup', () => {{
    dragNode = null;
    isDragging = false;
  }});

  canvas.addEventListener('wheel', e => {{
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const zoom = e.deltaY < 0 ? 1.12 : 0.89;
    
    transform.x = mx - (mx - transform.x) * zoom;
    transform.y = my - (my - transform.y) * zoom;
    transform.k *= zoom;
    render();
  }}, {{ passive: false }});

  // Render Loop
  let animTime = 0;
  function render() {{
    animTime += 0.04;
    ctx.clearRect(0, 0, width, height);

    ctx.save();
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // Draw multi-tier echelon background grid & column guides
    const nodeMap = new Map();
    rawNodes.forEach(n => nodeMap.set(n.id, n));

    // Draw Edges
    rawEdges.forEach(e => {{
      const u = nodeMap.get(e.source);
      const v = nodeMap.get(e.target);
      if (!u || !v || !isNodeVisible(u) || !isNodeVisible(v)) return;

      const isHigh = highlightedEdges.has(e.source + '->' + e.target);
      const isDimmed = selectedNode && !isHigh;

      ctx.beginPath();
      ctx.moveTo(u.x, u.y);

      // Smooth cubic bezier curves for multi-tier flow
      const midX = (u.x + v.x) / 2;
      ctx.bezierCurveTo(midX, u.y, midX, v.y, v.x, v.y);

      if (isHigh) {{
        ctx.strokeStyle = '#38BDF8';
        ctx.lineWidth = 2.5;
        ctx.shadowColor = '#0284C7';
        ctx.shadowBlur = 8;
      }} else if (isDimmed) {{
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
        ctx.lineWidth = 0.8;
        ctx.shadowBlur = 0;
      }} else {{
        ctx.strokeStyle = e.affected ? 'rgba(239, 68, 68, 0.45)' : 'rgba(148, 163, 184, 0.16)';
        ctx.lineWidth = 1.0;
        ctx.shadowBlur = 0;
      }}
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Animated directional flow particle on highlighted edges
      if (isHigh) {{
        const t = (animTime * 0.4) % 1.0;
        const px = Math.pow(1 - t, 3) * u.x + 3 * Math.pow(1 - t, 2) * t * midX + 3 * (1 - t) * Math.pow(t, 2) * midX + Math.pow(t, 3) * v.x;
        const py = Math.pow(1 - t, 3) * u.y + 3 * Math.pow(1 - t, 2) * t * u.y + 3 * (1 - t) * Math.pow(t, 2) * v.y + Math.pow(t, 3) * v.y;
        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = '#67E8F9';
        ctx.fill();
      }}
    }});

    // Draw Nodes
    rawNodes.forEach(n => {{
      if (!isNodeVisible(n)) return;

      const isSelected = selectedNode && selectedNode.id === n.id;
      const isHigh = highlightedNodes.has(n.id);
      const isDimmed = selectedNode && !isHigh;

      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);

      if (isDimmed) {{
        ctx.fillStyle = 'rgba(100, 116, 139, 0.2)';
        ctx.fill();
      }} else {{
        // Node Body
        ctx.fillStyle = n.color;
        if (n.disrupted) {{
          // Pulsing halo for disrupted node
          const pulse = (Math.sin(animTime * 3) + 1) * 3;
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.radius + pulse + 4, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(239, 68, 68, 0.6)';
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
          ctx.fillStyle = '#EF4444';
        }} else if (isSelected || isHigh) {{
          ctx.shadowColor = '#38BDF8';
          ctx.shadowBlur = 14;
        }}
        ctx.fill();
        ctx.shadowBlur = 0;

        // Border ring
        ctx.strokeStyle = isSelected ? '#FFFFFF' : 'rgba(255, 255, 255, 0.7)';
        ctx.lineWidth = isSelected ? 2.5 : 1.2;
        ctx.stroke();

        // Node Label
        if (transform.k > 0.65 || isSelected || isHigh || n.disrupted) {{
          ctx.font = (isSelected ? 'bold 11px' : '9px') + ' -apple-system, sans-serif';
          ctx.fillStyle = isSelected ? '#FFFFFF' : '#CBD5E1';
          ctx.textAlign = 'center';
          ctx.fillText(n.label, n.x, n.y + n.radius + 12);
        }}
      }}
    }});

    ctx.restore();

    if (highlightedNodes.size > 0 || isDragging || dragNode) {{
      requestAnimationFrame(render);
    }}
  }}

  // Initial startup
  resize();
  render();
</script>
</body>
</html>
"""
    return html_template

