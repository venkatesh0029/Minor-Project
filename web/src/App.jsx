import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
} from "recharts";

// ── Color palette ─────────────────────────────────────────────────────────────
const C = {
  bg:       "#060B14",
  panel:    "#0C1424",
  border:   "#1A2540",
  accent:   "#00D4FF",
  green:    "#00FF9D",
  orange:   "#FF8C42",
  red:      "#FF3B5C",
  purple:   "#A855F7",
  text:     "#E2EAF4",
  muted:    "#5A7090",
};

// ── API Helper ───────────────────────────────────────────────────────────────
async function fetchAPI(endpoint) {
  try {
    const res = await fetch(`http://localhost:8000${endpoint}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("API fetch failed", endpoint, err);
    return null;
  }
}

// ── Inventory WS / Simulation hook ──────────────────────────────────────────
function useInventoryWS(mode = "live") {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const intervalRef = useRef(null);
  const frameRef = useRef(0);
  const productsRef = useRef(null);

  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

  const buildSummary = (products) => {
    const total = products.length;
    const inStock = products.filter(p => p.status === "IN_STOCK").length;
    const lowStock = products.filter(p => p.status === "LOW_STOCK").length;
    const outOfStock = products.filter(p => p.status === "OUT_OF_STOCK").length;
    const overall = Math.round((inStock / total) * 100);
    return {
      total_products: total,
      in_stock: inStock,
      low_stock: lowStock,
      out_of_stock: outOfStock,
      overall_health: overall,
    };
  };

  const generateSimProducts = () => {
    const base = productsRef.current || [
      { name: "Cereal Box", category: "Breakfast", max: 12 },
      { name: "Orange Juice", category: "Beverages", max: 10 },
      { name: "Energy Bar", category: "Snacks", max: 16 },
      { name: "Coffee Pods", category: "Beverages", max: 14 },
      { name: "Protein Shake", category: "Drinks", max: 10 },
      { name: "Chips", category: "Snacks", max: 18 },
      { name: "Soda Can", category: "Beverages", max: 24 },
      { name: "Granola", category: "Snacks", max: 10 },
      { name: "Water Bottle", category: "Beverages", max: 20 },
      { name: "Tea Bags", category: "Beverages", max: 12 },
      { name: "Yogurt", category: "Dairy", max: 12 },
      { name: "Instant Noodles", category: "Pantry", max: 16 },
    ];

    const products = base.map((p) => {
      const prevCount = (p.count ?? p.max);
      const delta = Math.floor((Math.random() - 0.4) * 5);
      const count = clamp(prevCount + delta, 0, p.max);
      const pct = Math.round((count / p.max) * 100);
      const status = count === 0 ? "OUT_OF_STOCK" : pct < 25 ? "LOW_STOCK" : "IN_STOCK";
      return { ...p, max: p.max, count, pct, status };
    });

    productsRef.current = products;
    return products;
  };

  useEffect(() => {
    const stop = () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    stop();
    frameRef.current = 0;

    if (mode === "simulation") {
      setConnected(true);
      // Seed with an initial snapshot
      const tick = () => {
        frameRef.current += 1;
        const products = generateSimProducts();
        const summary = buildSummary(products);

        const newAlerts = [];
        if (Math.random() < 0.22) {
          const p = products[Math.floor(Math.random() * products.length)];
          if (p.status !== "IN_STOCK") {
            newAlerts.push({
              id: Math.random().toString(16).slice(2),
              message: `${p.name} is ${p.status === "OUT_OF_STOCK" ? "out of stock" : "running low"}!`,
              severity: p.status === "OUT_OF_STOCK" ? "critical" : "warning",
              alert_type: p.status === "OUT_OF_STOCK" ? "OUT_OF_STOCK" : "LOW_STOCK",
              timestamp: new Date().toISOString(),
            });
          }
        }

        setData({
          inventory: { products, summary },
          fps: 24,
          frame_count: frameRef.current,
          new_alerts: newAlerts,
        });
      };

      tick();
      intervalRef.current = setInterval(tick, 2000);
      return stop;
    }

    // Live mode: attempt WebSocket and fallback to API polling
    const loadInitialData = async () => {
      const inventory = await fetchAPI("/api/inventory");
      const alerts = await fetchAPI("/api/alerts?limit=20");
      if (inventory) {
        setData(prev => ({ ...prev, inventory, alerts: alerts?.alerts || [] }));
      }
    };

    loadInitialData();

    let ws;
    try {
      ws = new WebSocket("ws://localhost:8000/ws/monitor");
      ws.onopen = () => {
        setConnected(true);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
      ws.onmessage = (e) => setData(JSON.parse(e.data));
      ws.onclose = () => {
        setConnected(false);
        intervalRef.current = setInterval(async () => {
          const inventory = await fetchAPI("/api/inventory");
          const alerts = await fetchAPI("/api/alerts?limit=20");
          if (inventory) {
            setData(prev => ({ ...prev, inventory, alerts: alerts?.alerts || [] }));
          }
        }, 2000);
      };
      ws.onerror = () => {
        ws.close();
        setConnected(false);
      };
    } catch {
      setConnected(false);
      intervalRef.current = setInterval(async () => {
        const inventory = await fetchAPI("/api/inventory");
        const alerts = await fetchAPI("/api/alerts?limit=20");
        if (inventory) {
          setData(prev => ({ ...prev, inventory, alerts: alerts?.alerts || [] }));
        }
      }, 2000);
    }

    wsRef.current = ws;
    return stop;
  }, [mode]);

  return { data, connected };
}

// ── Metric Card ───────────────────────────────────────────────────────────────
function MetricCard({ label, value, sub, color, icon }) {
  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`,
      borderRadius: 16, padding: "20px 24px",
      borderTop: `2px solid ${color}`,
      flex: 1, minWidth: 160,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ color: C.muted, fontSize: 11, textTransform: "uppercase",
            letterSpacing: "0.1em", marginBottom: 8 }}>{label}</div>
          <div style={{ color, fontSize: 36, fontWeight: 800,
            fontFamily: "'DM Mono', monospace", lineHeight: 1 }}>{value}</div>
          {sub && <div style={{ color: C.muted, fontSize: 12, marginTop: 6 }}>{sub}</div>}
        </div>
        <div style={{ fontSize: 28, opacity: 0.6 }}>{icon}</div>
      </div>
    </div>
  );
}

// ── Status Badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = {
    IN_STOCK:     { bg: "#00FF9D22", color: C.green,  label: "IN STOCK" },
    LOW_STOCK:    { bg: "#FF8C4222", color: C.orange, label: "LOW STOCK" },
    OUT_OF_STOCK: { bg: "#FF3B5C22", color: C.red,    label: "OUT OF STOCK" },
  }[status] || {};
  return (
    <span style={{
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}40`,
      borderRadius: 6, padding: "2px 8px", fontSize: 10,
      fontWeight: 700, letterSpacing: "0.08em", fontFamily: "'DM Mono', monospace"
    }}>{cfg.label}</span>
  );
}

// ── Camera Feed Simulation ────────────────────────────────────────────────────
function CameraFeed({ products }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;

    // Define shelf regions
    const shelves = [
      { y: 60,  h: 100, label: "Shelf A" },
      { y: 185, h: 100, label: "Shelf B" },
      { y: 310, h: 100, label: "Shelf C" },
    ];

    function draw() {
      frameRef.current++;
      const t = frameRef.current;

      // Dark background with subtle noise
      ctx.fillStyle = "#050A12";
      ctx.fillRect(0, 0, W, H);

      // Scan line effect
      const scanY = (t * 2) % H;
      const grad = ctx.createLinearGradient(0, scanY - 20, 0, scanY + 20);
      grad.addColorStop(0, "transparent");
      grad.addColorStop(0.5, "rgba(0,212,255,0.04)");
      grad.addColorStop(1, "transparent");
      ctx.fillStyle = grad;
      ctx.fillRect(0, scanY - 20, W, 40);

      // Draw shelf racks
      shelves.forEach((shelf, si) => {
        // Shelf back panel
        ctx.fillStyle = "#0A1628";
        ctx.fillRect(20, shelf.y, W - 40, shelf.h);
        ctx.strokeStyle = "#1A3050";
        ctx.lineWidth = 1;
        ctx.strokeRect(20, shelf.y, W - 40, shelf.h);

        // Shelf label
        ctx.fillStyle = "#2A4070";
        ctx.font = "bold 10px 'DM Mono', monospace";
        ctx.fillText(shelf.label, 28, shelf.y + 14);

        // Shelf floor line
        ctx.strokeStyle = "#2A4878";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(20, shelf.y + shelf.h - 2);
        ctx.lineTo(W - 20, shelf.y + shelf.h - 2);
        ctx.stroke();

        // Draw products on this shelf
        const shelfProducts = (products || []).filter((_, idx) =>
          Math.floor(idx / 4) === si && idx < 12
        ).slice(0, 4);

        shelfProducts.forEach((p, pi) => {
          const cols = 4;
          const colW = (W - 60) / cols;
          const x = 30 + pi * colW;
          const y = shelf.y + 20;
          const pw = colW - 10, ph = shelf.h - 30;
          const count = p.count || 0;

          // Draw stacked items
          const maxItems = Math.min(count, 4);
          for (let i = 0; i < maxItems; i++) {
            const itemX = x + (i % 2) * (pw / 2 + 2);
            const itemY = y + Math.floor(i / 2) * (ph / 2 + 2);
            const itemW = pw / 2 - 2, itemH = ph / 2 - 2;

            // Item body
            ctx.fillStyle = p.status === "OUT_OF_STOCK" ? "#111" :
                            p.status === "LOW_STOCK" ? "#2A1800" : "#0A2040";
            ctx.fillRect(itemX, itemY, itemW, itemH);

            // Item border
            ctx.strokeStyle = p.status === "OUT_OF_STOCK" ? "#222" :
                              p.status === "LOW_STOCK" ? `rgba(255,140,66,0.5)` :
                              `rgba(0,212,255,0.3)`;
            ctx.lineWidth = 1;
            ctx.strokeRect(itemX, itemY, itemW, itemH);
          }

          // Bounding box if has items
          if (count > 0) {
            const pulse = 0.6 + Math.sin(t * 0.05 + pi) * 0.3;
            ctx.strokeStyle = p.status === "LOW_STOCK"
              ? `rgba(255,140,66,${pulse})`
              : p.status === "OUT_OF_STOCK"
              ? `rgba(255,59,92,${pulse})`
              : `rgba(0,212,255,${pulse * 0.6})`;
            ctx.lineWidth = 1.5;
            ctx.strokeRect(x - 2, y - 2, pw + 4, ph + 4);

            // Corner decorations
            const corners = [[x-2,y-2], [x+pw+2,y-2], [x-2,y+ph+2], [x+pw+2,y+ph+2]];
            corners.forEach(([cx, cy]) => {
              ctx.strokeStyle = ctx.strokeStyle;
              ctx.beginPath();
              ctx.moveTo(cx - 4, cy); ctx.lineTo(cx + 4, cy);
              ctx.moveTo(cx, cy - 4); ctx.lineTo(cx, cy + 4);
              ctx.stroke();
            });

            // Label
            ctx.fillStyle = p.status === "LOW_STOCK" ? C.orange :
                            p.status === "OUT_OF_STOCK" ? C.red : C.accent;
            ctx.font = "8px 'DM Mono', monospace";
            ctx.fillText(p.name.substring(0, 10), x, y - 4);
            ctx.font = "bold 9px monospace";
            ctx.fillText(`×${count}`, x + pw - 14, y + ph + 10);
          } else {
            // Empty slot
            ctx.strokeStyle = "#FF3B5C33";
            ctx.setLineDash([3, 3]);
            ctx.strokeRect(x, y, pw, ph);
            ctx.setLineDash([]);
            ctx.fillStyle = "#FF3B5C60";
            ctx.font = "bold 9px monospace";
            ctx.fillText("EMPTY", x + 6, y + ph/2 + 3);
          }
        });
      });

      // HUD Overlay
      ctx.fillStyle = C.accent + "CC";
      ctx.font = "bold 9px 'DM Mono', monospace";
      ctx.fillText("● REC", W - 48, 18);

      ctx.fillStyle = C.muted;
      ctx.font = "9px monospace";
      ctx.fillText(`CAM_001  |  1280×720  |  ${24}fps`, 10, H - 8);

      // Timestamp
      ctx.fillStyle = C.accent + "99";
      ctx.textAlign = "right";
      ctx.fillText(new Date().toLocaleTimeString(), W - 10, H - 8);
      ctx.textAlign = "left";

      animRef.current = requestAnimationFrame(draw);
    }

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [products]);

  return (
    <canvas ref={canvasRef} width={520} height={430}
      style={{ width: "100%", borderRadius: 12, display: "block" }} />
  );
}

// ── Shelf Heatmap ─────────────────────────────────────────────────────────────
function ShelfHeatmap({ products }) {
  const shelves = ["Shelf A", "Shelf B", "Shelf C"];
  const rows = ["Row 1", "Row 2"];
  const chunks = [];
  const all = products || [];
  for (let i = 0; i < 6; i++) {
    chunks.push(all.slice(i * 2, i * 2 + 2));
  }

  const getColor = (pct) => {
    if (pct === 0) return C.red;
    if (pct < 30) return C.orange;
    if (pct < 60) return "#FFE066";
    return C.green;
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "80px repeat(2, 1fr)", gap: 2 }}>
        <div />
        {rows.map(r => (
          <div key={r} style={{ color: C.muted, fontSize: 10, textAlign: "center",
            textTransform: "uppercase", letterSpacing: "0.05em", paddingBottom: 4 }}>{r}</div>
        ))}
        {shelves.map((shelf, si) => (
          <React.Fragment key={shelf}>
            <div style={{ color: C.muted, fontSize: 10, display: "flex",
              alignItems: "center", paddingRight: 8 }}>{shelf}</div>
            {[0, 1].map(ri => {
              const chunkIdx = si * 2 + ri;
              const chunk = chunks[chunkIdx] || [];
              const avg = chunk.length
                ? Math.round(chunk.reduce((a, p) => a + p.pct, 0) / chunk.length)
                : 0;
              const color = getColor(avg);
              return (
                <div key={ri} style={{
                  background: color + "22", border: `1px solid ${color}44`,
                  borderRadius: 8, padding: "10px 8px", textAlign: "center",
                  transition: "all 0.5s"
                }}>
                  <div style={{ color, fontWeight: 800,
                    fontFamily: "'DM Mono', monospace", fontSize: 20 }}>{avg}%</div>
                  <div style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>
                    {chunk.map(p => p.name.split(" ")[0]).join(", ") || "—"}
                  </div>
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [mode, setMode] = useState("live");
  const { data, connected } = useInventoryWS(mode);
  const [alerts, setAlerts] = useState([]);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [hourlyData, setHourlyData] = useState([]);

  const products = data?.inventory?.products || [];
  const summary = data?.inventory?.summary || {};

  // Accumulate alerts
  useEffect(() => {
    if (data?.new_alerts?.length > 0) {
      setAlerts(prev => {
        const newOnes = data.new_alerts.map(a => ({ ...a, id: Math.random() }));
        return [...newOnes, ...prev].slice(0, 25);
      });
    }
  }, [data]);

  // Build hourly trend data
  useEffect(() => {
    const now = new Date();
    const hours = Array.from({ length: 12 }, (_, i) => {
      const h = new Date(now - (11 - i) * 3600000);
      return {
        time: h.getHours() + ":00",
        detected: Math.floor(Math.random() * 30 + 50),
        low_stock: Math.floor(Math.random() * 8),
        out_of_stock: Math.floor(Math.random() * 3),
      };
    });
    setHourlyData(hours);
  }, []);

  const categoryData = (() => {
    const cats = {};
    products.forEach(p => {
      if (!cats[p.category]) cats[p.category] = { total: 0, max: 0 };
      cats[p.category].total += p.count || 0;
      cats[p.category].max += p.max || 12;
    });
    return Object.entries(cats).map(([name, v]) => ({
      name, value: Math.round((v.total / v.max) * 100)
    }));
  })();

  const PIE_COLORS = [C.green, C.accent, C.orange, C.purple, C.red, "#F9C74F"];

  return (
    <div style={{
      minHeight: "100vh", background: C.bg, color: C.text,
      fontFamily: "'DM Sans', 'Segoe UI', sans-serif", fontSize: 14,
    }}>
      {/* Google Fonts */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 2px; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes slideIn { from{opacity:0;transform:translateY(-10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes glow { 0%,100%{box-shadow:0 0 8px ${C.accent}44} 50%{box-shadow:0 0 20px ${C.accent}88} }
      `}</style>

      {/* ── TOP NAV ── */}
      <header style={{
        background: C.panel, borderBottom: `1px solid ${C.border}`,
        padding: "0 32px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 60, position: "sticky", top: 0, zIndex: 100
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: `linear-gradient(135deg, ${C.accent}, ${C.purple})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18
          }}>🔍</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 15, letterSpacing: "-0.02em" }}>
              ShelfAI Monitor
            </div>
            <div style={{ color: C.muted, fontSize: 10, letterSpacing: "0.05em" }}>
              AI-POWERED INVENTORY INTELLIGENCE
            </div>
          </div>
        </div>

        <nav style={{ display: "flex", gap: 4 }}>
          {["dashboard", "analytics", "alerts", "shelves"].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              background: activeTab === tab ? C.accent + "22" : "transparent",
              color: activeTab === tab ? C.accent : C.muted,
              border: activeTab === tab ? `1px solid ${C.accent}44` : "1px solid transparent",
              borderRadius: 8, padding: "6px 16px", cursor: "pointer",
              fontSize: 12, fontWeight: 600, textTransform: "uppercase",
              letterSpacing: "0.06em", transition: "all 0.2s"
            }}>{tab}</button>
          ))}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            background: mode === "simulation" ? C.orange + "15" : (connected ? C.green + "15" : C.red + "15"),
            border: `1px solid ${mode === "simulation" ? C.orange : (connected ? C.green : C.red)}44`,
            borderRadius: 20, padding: "4px 12px"
          }}>
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: mode === "simulation" ? C.orange : (connected ? C.green : C.red),
              animation: mode === "simulation" ? "pulse 2s infinite" : (connected ? "pulse 2s infinite" : "none")
            }} />
            <span style={{
              color: mode === "simulation" ? C.orange : (connected ? C.green : C.red),
              fontSize: 11, fontWeight: 600
            }}>
              {mode === "simulation" ? "SIMULATION" : connected ? "LIVE" : "OFFLINE"}
            </span>
          </div>

          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button onClick={() => setMode("live")} style={{
              background: mode === "live" ? C.accent + "22" : "transparent",
              color: mode === "live" ? C.accent : C.muted,
              border: mode === "live" ? `1px solid ${C.accent}44` : `1px solid ${C.border}`,
              borderRadius: 8, padding: "6px 12px", cursor: "pointer",
              fontSize: 11, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: "0.06em", transition: "all 0.2s"
            }}>Live</button>
            <button onClick={() => setMode("simulation")} style={{
              background: mode === "simulation" ? C.accent + "22" : "transparent",
              color: mode === "simulation" ? C.accent : C.muted,
              border: mode === "simulation" ? `1px solid ${C.accent}44` : `1px solid ${C.border}`,
              borderRadius: 8, padding: "6px 12px", cursor: "pointer",
              fontSize: 11, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: "0.06em", transition: "all 0.2s"
            }}>Sim</button>
          </div>

          <div style={{ color: C.muted, fontSize: 11 }}>
            {new Date().toLocaleTimeString()}
          </div>
        </div>
      </header>

      <main style={{ padding: "24px 32px", maxWidth: 1600, margin: "0 auto" }}>

        {/* ── DASHBOARD TAB ── */}
        {activeTab === "dashboard" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

            {/* Metric Cards */}
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <MetricCard label="Products Monitored" value={summary.total_products || 12}
                sub="Across 6 shelves" color={C.accent} icon="📦" />
              <MetricCard label="In Stock" value={summary.in_stock || "—"}
                sub="Healthy stock level" color={C.green} icon="✅" />
              <MetricCard label="Low Stock" value={summary.low_stock || "—"}
                sub="Needs attention" color={C.orange} icon="⚠️" />
              <MetricCard label="Out of Stock" value={summary.out_of_stock || "—"}
                sub="Immediate restock needed" color={C.red} icon="🚨" />
              <MetricCard label="Shelf Health" value={`${summary.overall_health || 0}%`}
                sub="Overall occupancy" color={C.purple} icon="📊" />
              <MetricCard label="FPS" value={data?.fps || 0}
                sub="Detection speed" color={C.muted} icon="🎥" />
            </div>

            {/* Main Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20 }}>

              {/* Camera Feed */}
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 16, overflow: "hidden"
              }}>
                <div style={{
                  padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  display: "flex", justifyContent: "space-between", alignItems: "center"
                }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>📹 Live Camera Feed — CAM_001</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <span style={{ background: C.red + "22", color: C.red,
                      border: `1px solid ${C.red}44`, borderRadius: 6, padding: "2px 8px",
                      fontSize: 10, fontWeight: 700, animation: "pulse 2s infinite" }}>● REC</span>
                    <span style={{ color: C.muted, fontSize: 11 }}>
                      Frame #{(data?.frame_count || 0).toLocaleString()}
                    </span>
                  </div>
                </div>
                <div style={{ padding: 16 }}>
                  <CameraFeed products={products} />
                </div>
              </div>

              {/* Alerts Panel */}
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 16, display: "flex", flexDirection: "column"
              }}>
                <div style={{
                  padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  display: "flex", justifyContent: "space-between", alignItems: "center"
                }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>🔔 Live Alerts</div>
                  <span style={{
                    background: C.red + "22", color: C.red,
                    border: `1px solid ${C.red}44`, borderRadius: 10,
                    padding: "1px 8px", fontSize: 11, fontWeight: 700
                  }}>{alerts.length}</span>
                </div>
                <div style={{ flex: 1, overflowY: "auto", padding: "8px 0", maxHeight: 430 }}>
                  {alerts.length === 0 ? (
                    <div style={{ padding: 24, textAlign: "center", color: C.muted }}>
                      All shelves fully stocked ✓
                    </div>
                  ) : alerts.map((a, i) => (
                    <div key={a.id} style={{
                      padding: "10px 16px",
                      borderLeft: `3px solid ${a.severity === "critical" ? C.red : C.orange}`,
                      marginBottom: 2,
                      background: i === 0 ? (a.severity === "critical" ? C.red + "08" : C.orange + "08") : "transparent",
                      animation: i === 0 ? "slideIn 0.3s ease" : "none"
                    }}>
                      <div style={{
                        color: a.severity === "critical" ? C.red : C.orange,
                        fontSize: 12, fontWeight: 600, marginBottom: 2
                      }}>{a.message}</div>
                      <div style={{ color: C.muted, fontSize: 10 }}>
                        {new Date(a.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Product Grid */}
            <div style={{
              background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16
            }}>
              <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                fontWeight: 700, fontSize: 13 }}>📋 Product Stock Status</div>
              <div style={{ padding: 16 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
                  {products.map((p, i) => (
                    <div key={i} style={{
                      background: C.bg, border: `1px solid ${C.border}`,
                      borderRadius: 12, padding: 14,
                      borderTop: `2px solid ${p.status === "OUT_OF_STOCK" ? C.red :
                        p.status === "LOW_STOCK" ? C.orange : C.green}`,
                      transition: "all 0.4s"
                    }}>
                      <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</div>
                      <div style={{ color: C.muted, fontSize: 10, marginBottom: 8 }}>{p.category}</div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <span style={{ fontFamily: "'DM Mono', monospace", fontWeight: 800, fontSize: 22,
                          color: p.status === "OUT_OF_STOCK" ? C.red :
                            p.status === "LOW_STOCK" ? C.orange : C.text }}>{p.count}</span>
                        <StatusBadge status={p.status} />
                      </div>
                      {/* Stock bar */}
                      <div style={{ background: "#1A2540", borderRadius: 4, height: 4 }}>
                        <div style={{
                          height: 4, borderRadius: 4, transition: "width 0.5s ease",
                          width: `${p.pct}%`,
                          background: p.status === "OUT_OF_STOCK" ? C.red :
                            p.status === "LOW_STOCK" ? C.orange : C.green
                        }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── ANALYTICS TAB ── */}
        {activeTab === "analytics" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              {/* Hourly Trend */}
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16 }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  fontWeight: 700, fontSize: 13 }}>📈 Detections per Hour (Last 12h)</div>
                <div style={{ padding: "20px 16px" }}>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={hourlyData}>
                      <defs>
                        <linearGradient id="gDetected" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={C.accent} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={C.accent} stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="gLow" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={C.orange} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={C.orange} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                      <XAxis dataKey="time" tick={{ fill: C.muted, fontSize: 10 }} />
                      <YAxis tick={{ fill: C.muted, fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8 }} />
                      <Area type="monotone" dataKey="detected" stroke={C.accent} fill="url(#gDetected)" strokeWidth={2} />
                      <Area type="monotone" dataKey="low_stock" stroke={C.orange} fill="url(#gLow)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Category Pie */}
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16 }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  fontWeight: 700, fontSize: 13 }}>🥧 Stock Level by Category</div>
                <div style={{ padding: "20px 16px" }}>
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie data={categoryData} dataKey="value" nameKey="name"
                        cx="50%" cy="50%" outerRadius={90} innerRadius={50}
                        paddingAngle={3}>
                        {categoryData.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v) => `${v}%`}
                        contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8 }} />
                      <Legend wrapperStyle={{ color: C.muted, fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Product Bar Chart */}
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16, gridColumn: "1 / -1" }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  fontWeight: 700, fontSize: 13 }}>📊 Current Stock Levels per Product</div>
                <div style={{ padding: "20px 16px" }}>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={products} margin={{ left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                      <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 9 }}
                        angle={-25} textAnchor="end" height={50} />
                      <YAxis tick={{ fill: C.muted, fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8 }} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {products.map((p, i) => (
                          <Cell key={i} fill={
                            p.status === "OUT_OF_STOCK" ? C.red :
                            p.status === "LOW_STOCK" ? C.orange : C.green
                          } />
                        ))}
                      </Bar>
                      <Bar dataKey="threshold" fill={C.muted + "44"} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── ALERTS TAB ── */}
        {activeTab === "alerts" && (
          <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16 }}>
            <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
              display: "flex", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>🔔 All Stock Alerts</div>
              <span style={{ color: C.muted, fontSize: 12 }}>{alerts.length} events</span>
            </div>
            {alerts.map((a, i) => (
              <div key={i} style={{
                padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                display: "flex", alignItems: "center", gap: 16,
                background: i % 2 === 0 ? "transparent" : "#FFFFFF03"
              }}>
                <div style={{
                  width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                  background: a.severity === "critical" ? C.red : C.orange
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{a.message}</div>
                  <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                    {new Date(a.timestamp).toLocaleString()}
                  </div>
                </div>
                <span style={{
                  background: a.severity === "critical" ? C.red + "22" : C.orange + "22",
                  color: a.severity === "critical" ? C.red : C.orange,
                  border: `1px solid ${a.severity === "critical" ? C.red : C.orange}44`,
                  borderRadius: 6, padding: "3px 10px", fontSize: 11, fontWeight: 700
                }}>{a.alert_type?.replace("_", " ")}</span>
              </div>
            ))}
            {alerts.length === 0 && (
              <div style={{ padding: 40, textAlign: "center", color: C.muted }}>
                No alerts generated yet. All shelves are healthy ✅
              </div>
            )}
          </div>
        )}

        {/* ── SHELVES TAB ── */}
        {activeTab === "shelves" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              {/* Heatmap */}
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16 }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  fontWeight: 700, fontSize: 13 }}>🗺️ Shelf Occupancy Heatmap</div>
                <div style={{ padding: 20 }}>
                  <ShelfHeatmap products={products} />
                  <div style={{ display: "flex", gap: 16, marginTop: 16, justifyContent: "center" }}>
                    {[["Empty", C.red], ["Low", C.orange], ["Moderate", "#FFE066"], ["Full", C.green]].map(([l, c]) => (
                      <div key={l} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <div style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
                        <span style={{ color: C.muted, fontSize: 11 }}>{l}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Shelf Detail */}
              <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16 }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${C.border}`,
                  fontWeight: 700, fontSize: 13 }}>📦 Shelf Inventory Detail</div>
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                  {products.map((p, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "8px 12px", background: C.bg, borderRadius: 10,
                      border: `1px solid ${C.border}`
                    }}>
                      <div style={{ flex: 1, fontWeight: 600, fontSize: 12 }}>{p.name}</div>
                      <div style={{ width: 120, background: "#1A2540", borderRadius: 4, height: 6 }}>
                        <div style={{
                          height: 6, borderRadius: 4,
                          width: `${p.pct}%`, transition: "width 0.5s",
                          background: p.status === "OUT_OF_STOCK" ? C.red :
                            p.status === "LOW_STOCK" ? C.orange : C.green
                        }} />
                      </div>
                      <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 12,
                        color: C.muted, width: 40, textAlign: "right" }}>{p.count}/{p.max}</div>
                      <StatusBadge status={p.status} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Footer */}
      <footer style={{
        textAlign: "center", padding: "20px 32px",
        color: C.muted, fontSize: 11, borderTop: `1px solid ${C.border}`,
        display: "flex", justifyContent: "space-between"
      }}>
        <span>ShelfAI Monitor v1.0 · AI-Based Shelf-Level Inventory Monitoring System</span>
        <span>Powered by YOLOv8 + FastAPI + React</span>
      </footer>
    </div>
  );
}
