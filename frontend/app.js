// RetailPulse AI — UI Application Scripts

// Active configuration
const CONFIG = {
  API_BASE_URL: (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:8000/api/v1"
    : window.location.origin.replace("-frontend", "-backend") + "/api/v1",
  POLL_INTERVAL_MS: 3000,
  DEFAULT_STORE_ID: "store-7ef38ab2-1456-42d4-a0fb-365922e3914a"
};

let activeStoreId = CONFIG.DEFAULT_STORE_ID;
let systemConnected = false;
let fallbackMode = false;
let knownEventIds = new Set();

// Active historical occupancy queue for the SVG sparkline plot
let occupancyHistory = [6, 8, 5, 9, 11, 10, 8, 12, 14, 11, 9, 13, 10, 11];

// Maximum capacities for each zone to calculate utilization percentages
const ZONE_CAPACITIES = {
  main_entrance_exit: 8,
  mid_left_fragrance: 4,
  mid_left_nail_unit: 4,
  top_shelf_eb_korean: 3,
  top_shelf_the_face_shop: 3,
  top_shelf_minimalist: 3,
  top_shelf_aqualogica: 3,
  makeup_unit: 8,
  foh_open_floor: 10,
  checkout_queue: 6,
  checkout_counter: 3
};

// Zone description mapping for localized clicks
const ZONE_METADATA = {
  main_entrance_exit: {
    name: "Entrance & Exit Lobby",
    desc: "Main ingress/egress foyer. Tracks customer capture rate, initial path direction, and re-entry counts.",
    holdPower: "15%",
    stops: 142
  },
  mid_left_fragrance: {
    name: "Fragrance Display",
    desc: "Premium selection of designer fragrances. Shelf engagement sensors record attractive stops and deep brand evaluation.",
    holdPower: "48%",
    stops: 298
  },
  mid_left_nail_unit: {
    name: "Nail Cosmetics Unit",
    desc: "Self-service nail lacquers and treatments. Monitored for attractive stops and cross-category engagement.",
    holdPower: "35%",
    stops: 184
  },
  top_shelf_eb_korean: {
    name: "EB Korean Brand Shelf",
    desc: "Exclusive Korean beauty row. Highly attractive promotional spot with peak dwell times and attractive stopping power.",
    holdPower: "78%",
    stops: 642
  },
  top_shelf_the_face_shop: {
    name: "The Face Shop Shelf",
    desc: "Natural skincare products shelf. Highly correlated with clean-beauty shopping funnels.",
    holdPower: "65%",
    stops: 490
  },
  top_shelf_minimalist: {
    name: "Minimalist Brand Shelf",
    desc: "Active skincare brand section. Features high conversion conversion scores from spatial correlation.",
    holdPower: "72%",
    stops: 512
  },
  top_shelf_aqualogica: {
    name: "Aqualogica Shelf",
    desc: "Gel sunscreens and moisturizers unit. Attracts high summer-season footfall and dwell logs.",
    holdPower: "55%",
    stops: 320
  },
  makeup_unit: {
    name: "Promotional Makeup Unit",
    desc: "Circular center-floor promotional unit. A prime circulation anchor that drives secondary brand browsing journeys.",
    holdPower: "85%",
    stops: 894
  },
  foh_open_floor: {
    name: "Front of House Walkway",
    desc: "Primary customer circulation corridor. Measures flow density, speed, and path splits across product rows.",
    holdPower: "8%",
    stops: 42
  },
  checkout_queue: {
    name: "Checkout Waiting Queue",
    desc: "Shoppers waiting in POS line. Real-time length triggers crowding alerts when wait exceeds 120 seconds.",
    holdPower: "92%",
    stops: 1102
  },
  checkout_counter: {
    name: "Checkout POS Counter",
    desc: "Point of Sale terminal. Transactions are temporally joined to shopper exits for conversion metric.",
    holdPower: "98%",
    stops: 1205
  }
};

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  startMonitoring();
  drawSparkline();
});

// Event Listeners Setup
function setupEventListeners() {
  const storeSelect = document.getElementById("storeSelect");
  storeSelect.addEventListener("change", (e) => {
    activeStoreId = e.target.value;
    logTerminal("SYSTEM", "Hub Context Shift", `Switched active monitoring context to hub profile: ${activeStoreId}`);
    fetchData();
  });
}

// Main Polling Loop
function startMonitoring() {
  fetchData();
  setInterval(fetchData, CONFIG.POLL_INTERVAL_MS);
}

// Fetch metrics, alerts, and events
async function fetchData() {
  try {
    // 1. Fetch Metrics
    const metricsResponse = await fetch(`${CONFIG.API_BASE_URL}/metrics?store_id=${activeStoreId}`);
    if (!metricsResponse.ok) throw new Error("Backend degraded");
    const metrics = await metricsResponse.json();
    updateMetrics(metrics);
    
    // 2. Fetch Alerts
    const alertsResponse = await fetch(`${CONFIG.API_BASE_URL}/alerts?store_id=${activeStoreId}&limit=10`);
    if (alertsResponse.ok) {
      const alertsData = await alertsResponse.json();
      updateAlerts(alertsData.data || []);
    }

    // 3. Fetch Event Logs
    const eventsResponse = await fetch(`${CONFIG.API_BASE_URL}/telemetry/events?limit=20`);
    if (eventsResponse.ok) {
      const events = await eventsResponse.json();
      updateEventStream(events);
    }

    setConnectionStatus(true);
    fallbackMode = false;
  } catch (error) {
    if (!fallbackMode) {
      console.warn("FastAPI backend unreachable, launching high-fidelity simulation fallback...");
      logTerminal("SYSTEM", "Simulation Online", `RetailPulse AI backend unreachable at ${CONFIG.API_BASE_URL}. Active offline visual simulation initialized.`);
      fallbackMode = true;
    }
    setConnectionStatus(false);
    runSimulation();
  }
}

// Set Connection status pill
function setConnectionStatus(connected) {
  const statusIndicator = document.getElementById("systemStatus");
  if (connected) {
    statusIndicator.className = "system-status";
    statusIndicator.innerHTML = `
      <span class="status-dot green pulse"></span>
      <span class="status-label">Ingestion Active</span>
    `;
    statusIndicator.style.background = "rgba(16, 185, 129, 0.05)";
    statusIndicator.style.borderColor = "rgba(16, 185, 129, 0.15)";
    statusIndicator.style.color = "var(--emerald)";
  } else {
    statusIndicator.className = "system-status degraded";
    statusIndicator.innerHTML = `
      <span class="status-dot red pulse"></span>
      <span class="status-label">Simulation Active</span>
    `;
    statusIndicator.style.background = "rgba(249, 115, 22, 0.08)";
    statusIndicator.style.borderColor = "rgba(249, 115, 22, 0.2)";
    statusIndicator.style.color = "var(--orange)";
  }
}

// Update primary aggregate metrics and funnel
function updateMetrics(data) {
  document.getElementById("currentOccupancy").innerText = data.current_occupancy;
  document.getElementById("totalVisitors").innerText = data.total_visitors;
  document.getElementById("avgDwellTime").innerText = data.avg_dwell_time.toFixed(1);
  document.getElementById("conversionRate").innerText = data.conversion_rate.toFixed(1);
  document.getElementById("peakHour").innerText = data.peak_hour || "17:00-18:00";

  // Dynamic Occupancy Badge
  const badge = document.getElementById("occupancyTrend");
  if (data.current_occupancy > 12) {
    badge.className = "metric-badge red";
    badge.innerText = "CROWDED";
  } else if (data.current_occupancy > 5) {
    badge.className = "metric-badge green";
    badge.innerText = "OPTIMAL";
  } else {
    badge.className = "metric-badge green";
    badge.innerText = "LIGHT";
  }

  // Push live occupancy point to graph accumulator
  occupancyHistory.push(data.current_occupancy);
  drawSparkline();

  // Update middle-section Conversion Funnel metrics based on dynamic values
  const conversionRate = data.conversion_rate || 38.6;
  const capturePct = 100;
  const browsePct = Math.max(78, 92 - (data.current_occupancy * 0.8));
  const evaluatePct = Math.max(54, browsePct - 15);
  const queuePct = Math.max(38, evaluatePct - 12);
  
  document.getElementById("funnel_capture").style.width = capturePct + "%";
  document.getElementById("funnel_val_capture").innerText = capturePct + "%";
  
  document.getElementById("funnel_browse").style.width = browsePct.toFixed(0) + "%";
  document.getElementById("funnel_val_browse").innerText = browsePct.toFixed(0) + "%";
  
  document.getElementById("funnel_evaluate").style.width = evaluatePct.toFixed(0) + "%";
  document.getElementById("funnel_val_evaluate").innerText = evaluatePct.toFixed(0) + "%";
  
  document.getElementById("funnel_queue").style.width = queuePct.toFixed(0) + "%";
  document.getElementById("funnel_val_queue").innerText = queuePct.toFixed(0) + "%";
  
  document.getElementById("funnel_purchase").style.width = conversionRate.toFixed(1) + "%";
  document.getElementById("funnel_val_purchase").innerText = conversionRate.toFixed(1) + "%";
}

// Draw the dynamic real-time SVG sparkline timeline plot
function drawSparkline() {
  const pathEl = document.getElementById("sparklinePath");
  const areaEl = document.getElementById("sparklineArea");
  if (!pathEl || !areaEl) return;
  
  const width = 800;
  const height = 180;
  const maxPoints = 20;
  
  while (occupancyHistory.length > maxPoints) {
    occupancyHistory.shift();
  }
  
  const pointsCount = occupancyHistory.length;
  if (pointsCount < 2) return;
  
  const maxVal = Math.max(...occupancyHistory, 12);
  const minVal = 0;
  const valRange = maxVal - minVal;
  
  let pathD = "";
  let areaD = "";
  const dx = width / (pointsCount - 1);
  
  for (let i = 0; i < pointsCount; i++) {
    const x = i * dx;
    const normY = (occupancyHistory[i] - minVal) / valRange;
    const y = height - (normY * (height - 30)) - 10;
    
    if (i === 0) {
      pathD = `M ${x} ${y}`;
      areaD = `M ${x} ${height} L ${x} ${y}`;
    } else {
      pathD += ` L ${x} ${y}`;
      areaD += ` L ${x} ${y}`;
    }
    
    if (i === pointsCount - 1) {
      areaD += ` L ${x} ${height} Z`;
    }
  }
  
  pathEl.setAttribute("d", pathD);
  areaEl.setAttribute("d", areaD);
}

// Update Active Alerts Panel (Operations Command Center)
function updateAlerts(alerts) {
  const alertsList = document.getElementById("alertsList");
  const alertCountBadge = document.getElementById("activeAlertCount");
  
  alertCountBadge.innerText = `${alerts.length} ACTIVE`;
  if (alerts.length > 0) {
    alertCountBadge.className = "active-alerts-badge alert";
    alertsList.innerHTML = "";
    alerts.forEach(alert => {
      const alertItem = document.createElement("div");
      alertItem.className = `ops-alert-card ${alert.severity}`;
      alertItem.innerHTML = `
        <span class="ops-severity-badge ${alert.severity}">${alert.severity}</span>
        <div class="ops-alert-details">
          <span class="ops-alert-msg">${alert.message}</span>
          <span class="ops-alert-meta">${new Date(alert.timestamp).toLocaleTimeString()} | Category: ${alert.alert_type}</span>
        </div>
      `;
      alertsList.appendChild(alertItem);
    });
  } else {
    alertCountBadge.className = "active-alerts-badge";
    alertsList.innerHTML = `
      <div class="empty-alerts-card">
        <span>🔔</span>
        <p>Operational zones are fully clear. Telemetry buffers show all metrics performing within baseline limits.</p>
      </div>
    `;
  }
}

// Update Live CCTV Event Stream (Chronological Activity Cards)
function updateEventStream(events) {
  events.forEach(event => {
    if (!knownEventIds.has(event.event_id || event.id)) {
      knownEventIds.add(event.event_id || event.id);
      
      let title = "";
      let message = "";
      let typeClass = "SYSTEM";
      const timestamp = new Date(event.timestamp).toLocaleTimeString();

      switch (event.event_type) {
        case "ENTRY":
        case "PersonEntryEvent":
          title = "Shopper Entry";
          message = `Shopper #${event.track_id} entered entrance lobby segment. (conf=${(event.confidence || 0.95).toFixed(2)})`;
          typeClass = "ENTRY";
          incrementZoneCount("main_entrance_exit");
          break;
        case "EXIT":
        case "PersonExitEvent":
          title = "Shopper Exit";
          message = `Shopper #${event.track_id} cleared store checkout gate.`;
          typeClass = "EXIT";
          decrementZoneCount("main_entrance_exit");
          break;
        case "ZONE_DWELL":
        case "ZoneDwellEvent":
          const zMeta = ZONE_METADATA[event.zone_id] || { name: event.zone_id };
          title = "Aisle Dwell Complete";
          message = `Shopper #${event.track_id} completed evaluation at '${zMeta.name}' after ${event.dwell_time_seconds.toFixed(0)}s.`;
          typeClass = "DWELL";
          decrementZoneCount(event.zone_id);
          break;
        case "QUEUE_UPDATE":
        case "QueueUpdateEvent":
          title = "Queue Metric Adjust";
          message = `POS Waiting Queue currently containing ${event.current_length} shoppers (max wait: ${event.max_wait_seconds.toFixed(0)}s).`;
          typeClass = "QUEUE";
          document.getElementById("count_checkout_queue").innerText = event.current_length;
          updateQueueIntelligence(event);
          break;
        case "OCCUPANCY_UPDATE":
        case "OccupancyUpdateEvent":
          updateZoneMapOccupants(event.zone_occupancies);
          break;
        case "ALERT":
        case "QueueAlertEvent":
          title = "Operational Alert";
          message = `Breached threshold: ${event.message}`;
          typeClass = "ALERT";
          break;
      }

      if (message) {
        logTerminal(typeClass, title, message, timestamp);
      }
    }
  });
}

// Add a high-fidelity card to the activity feed
function logTerminal(typeClass, title, message, timestamp = null) {
  const feed = document.getElementById("eventStreamLog");
  if (!feed) return;
  
  if (!timestamp) {
    timestamp = new Date().toLocaleTimeString();
  }
  
  let emoji = "⚙️";
  if (typeClass === "ENTRY") emoji = "🟢";
  else if (typeClass === "EXIT") emoji = "⚪";
  else if (typeClass === "DWELL") emoji = "⏱️";
  else if (typeClass === "QUEUE") emoji = "👥";
  else if (typeClass === "ALERT") emoji = "⚠️";
  
  const card = document.createElement("div");
  card.className = `activity-timeline-card ${typeClass}`;
  card.innerHTML = `
    <div class="timeline-marker">${emoji}</div>
    <div class="timeline-card-content">
      <span class="timeline-card-title">${title}</span>
      <span class="timeline-card-desc">${message}</span>
      <span class="timeline-card-time">${timestamp}</span>
    </div>
  `;
  
  feed.insertBefore(card, feed.firstChild);
  
  // Keep timeline list capped
  while (feed.childElementCount > 40) {
    feed.removeChild(feed.lastChild);
  }
}

// Update individual zone counters & floating utilization overlays
function updateZoneMapOccupants(zoneOccupancies) {
  if (!zoneOccupancies) return;
  for (const [zoneId, occupantCount] of Object.entries(zoneOccupancies)) {
    const counterElement = document.getElementById(`count_${zoneId}`);
    if (counterElement) {
      counterElement.innerText = occupantCount;
      
      const zoneNode = counterElement.parentElement;
      if (zoneNode && occupantCount > 0) {
        zoneNode.classList.add("active");
      } else if (zoneNode) {
        zoneNode.classList.remove("active");
      }
    }

    // Dynamic Utilization % calculate and injection
    const utilElement = document.getElementById(`util_${zoneId}`);
    if (utilElement) {
      const cap = ZONE_CAPACITIES[zoneId] || 4;
      const utilPct = Math.min(100, Math.round((occupantCount / cap) * 100));
      utilElement.innerText = `UTIL: ${utilPct}%`;
      
      // Dynamic coloring of utilization based on density
      if (utilPct >= 80) {
        utilElement.style.fill = "var(--orange)";
      } else if (utilPct > 0) {
        utilElement.style.fill = "var(--emerald)";
      } else {
        utilElement.style.fill = "var(--slate)";
      }
    }
  }
}

function incrementZoneCount(zoneId) {
  const el = document.getElementById(`count_${zoneId}`);
  if (el) {
    const nextVal = parseInt(el.innerText) + 1;
    el.innerText = nextVal;
    updateZoneMapOccupants({ [zoneId]: nextVal });
  }
}

function decrementZoneCount(zoneId) {
  const el = document.getElementById(`count_${zoneId}`);
  if (el) {
    const nextVal = Math.max(0, parseInt(el.innerText) - 1);
    el.innerText = nextVal;
    updateZoneMapOccupants({ [zoneId]: nextVal });
  }
}

// Update wait times / queue badge states
function updateQueueIntelligence(event) {
  const badge = document.getElementById("queueStatusBadge");
  if (!badge) return;
  
  if (event.current_length >= 4 || event.max_wait_seconds >= 120) {
    badge.innerText = "CONGESTED";
    badge.className = "panel-badge alert danger";
  } else if (event.current_length >= 2) {
    badge.innerText = "WARNING";
    badge.className = "panel-badge alert warning";
  } else {
    badge.innerText = "OPTIMAL";
    badge.className = "panel-badge alert";
  }
}

// Localized Zone Modal Dialog Actions
function showZoneDetails(zoneId) {
  const modal = document.getElementById("zoneModal");
  const meta = ZONE_METADATA[zoneId] || {
    name: zoneId.replace(/_/g, " ").toUpperCase(),
    desc: "Active floor location monitored by YOLOv8 model layers.",
    holdPower: "40%",
    stops: 15
  };

  const count = document.getElementById(`count_${zoneId}`)?.innerText || "0";

  document.getElementById("modalZoneTitle").innerText = meta.name;
  document.getElementById("modalZoneOccupancy").innerText = count;
  document.getElementById("modalZoneHoldPower").innerText = meta.holdPower;
  document.getElementById("modalZoneStops").innerText = meta.stops;
  document.getElementById("modalZoneDesc").innerText = meta.desc;

  modal.classList.add("active");
}

function closeModal() {
  document.getElementById("zoneModal").classList.remove("active");
}


// ─── Visual Simulation Fallback ──────────────────────────────────────────────
// Generates realistic synthetic event sequences for RetailPulse AI when offline
let simOccupants = {
  main_entrance_exit: 2,
  mid_left_fragrance: 1,
  mid_left_nail_unit: 0,
  top_shelf_eb_korean: 2,
  top_shelf_the_face_shop: 1,
  top_shelf_minimalist: 1,
  top_shelf_aqualogica: 0,
  makeup_unit: 3,
  foh_open_floor: 2,
  checkout_queue: 1,
  checkout_counter: 1
};

let simTotalVisitors = 186;
let simAvgDwell = 8.2;
let simConversion = 38.6;
let shopperCounter = 196;

function runSimulation() {
  simAvgDwell += (Math.random() - 0.5) * 0.04;
  simConversion += (Math.random() - 0.5) * 0.12;
  const currentTotalOccupancy = Object.values(simOccupants).reduce((a, b) => a + b, 0);

  updateMetrics({
    current_occupancy: currentTotalOccupancy,
    total_visitors: simTotalVisitors,
    avg_dwell_time: simAvgDwell,
    conversion_rate: simConversion,
    peak_hour: "16:00-17:00"
  });

  updateZoneMapOccupants(simOccupants);

  // Generate random simulation events
  const rand = Math.random();
  
  if (rand < 0.16) {
    // Simulate ENTRY
    shopperCounter++;
    simTotalVisitors++;
    simOccupants.main_entrance_exit++;
    logTerminal("ENTRY", "Shopper Entry Detected", `Shopper #${shopperCounter} cleared the lobby segment. (conf=${(0.86 + Math.random()*0.13).toFixed(2)})`);
  } else if (rand < 0.32) {
    // Simulate DWELL / Zone movement
    const zones = Object.keys(simOccupants);
    const fromZone = zones[Math.floor(Math.random() * zones.length)];
    const toZone = zones[Math.floor(Math.random() * zones.length)];
    
    if (simOccupants[fromZone] > 0 && fromZone !== toZone) {
      simOccupants[fromZone]--;
      simOccupants[toZone]++;
      const dwellSeconds = Math.floor(10 + Math.random() * 90);
      const zFromMeta = ZONE_METADATA[fromZone] || { name: fromZone };
      const zToMeta = ZONE_METADATA[toZone] || { name: toZone };
      logTerminal("DWELL", "Aisle Dwell Logged", `Shopper #${Math.floor(100 + Math.random()*80)} shifted from '${zFromMeta.name}' to '${zToMeta.name}' (dwell=${dwellSeconds}s).`);
    }
  } else if (rand < 0.42) {
    // Simulate EXIT
    if (simOccupants.main_entrance_exit > 0) {
      simOccupants.main_entrance_exit--;
      logTerminal("EXIT", "Shopper Exit Logged", `Shopper #${Math.floor(100 + Math.random()*80)} cleared primary threshold loop.`);
    }
  } else if (rand < 0.58) {
    // Queue updates and congestion checking
    simOccupants.checkout_queue = Math.floor(Math.random() * 5);
    const len = simOccupants.checkout_queue;
    const avgWait = len * 34.0 + (Math.random()*12);
    const maxWait = len * 45.0 + (Math.random()*20);

    updateQueueIntelligence({
      current_length: len,
      avg_wait_seconds: avgWait,
      max_wait_seconds: maxWait
    });

    logTerminal("QUEUE", "POS Waiting Queue", `Queue updated: queue_length=${len} waiting, avg_wait=${avgWait.toFixed(0)}s`);

    if (len >= 4) {
      logTerminal("ALERT", "Queue Threshold Breach", `Breached operational limit: Wait queues congested at checkoutPOS. Length=${len}; max_wait=${maxWait.toFixed(0)}s.`);
      updateAlerts([{
        severity: "HIGH",
        message: `Checkout congestion: ${len} shoppers in queue, max waiting buffer exceeded.`,
        alert_type: "crowding",
        timestamp: new Date().toISOString()
      }]);
    } else {
      updateAlerts([]);
    }
  }
}
