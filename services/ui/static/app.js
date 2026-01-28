const app = document.getElementById("app");
const drawer = document.getElementById("evidence-drawer");
const drawerBody = document.getElementById("drawer-body");
const drawerClose = document.getElementById("drawer-close");
const API_BASE = "/api";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.status === "error") {
    const message = payload.error?.message || "Request failed";
    throw new Error(message);
  }
  return payload.data;
}

function setView(html) {
  app.innerHTML = html;
}

function renderEvidence(field) {
  if (!field) return "";
  if (field.missing_evidence && (!field.evidence || field.evidence.length === 0)) {
    return `<span class="evidence-missing">Missing evidence</span>`;
  }
  const pills = (field.evidence || []).map((ev) => {
    const excerpt = ev.excerpt ? ev.excerpt : "Evidence";
    return `<span class="evidence-pill" data-evidence-id="${ev.evidence_id}">${excerpt}</span>`;
  });
  if (!pills.length) {
    return `<span class="evidence-missing">Missing evidence</span>`;
  }
  return pills.join("");
}

function formatValue(value) {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value;
}

function showError(message) {
  setView(`<div class="panel error">${message}</div>`);
}

function showNotice(message) {
  setView(`<div class="panel notice">${message}</div>`);
}

async function renderList() {
  try {
    const data = await fetchJson("/listings");
    const cards = data.listings
      .map((listing) => {
        const fields = Object.entries(listing.fields || {})
          .map(
            ([name, field]) => `
              <div class="field">
                <strong>${name}</strong>
                <span>${formatValue(field.value)}</span>
              </div>
              <div class="evidence-list">${renderEvidence(field)}</div>
            `
          )
          .join("");
        return `
          <div class="card" data-listing-id="${listing.listing_id}">
            <h3>${listing.title}</h3>
            <div class="field"><strong>Neighborhood</strong><span>${listing.neighborhood}</span></div>
            ${fields}
            <button class="ghost" data-detail-id="${listing.listing_id}">View details</button>
          </div>
        `;
      })
      .join("");

    setView(`
      <section class="panel">
        <h2>Listings</h2>
        <p class="notice">Evidence is shown for every displayed field. Missing evidence is flagged explicitly.</p>
        <div class="card-grid">${cards}</div>
      </section>
    `);
  } catch (error) {
    showError(error.message);
  }
}

async function renderDetail(listingId) {
  if (!listingId) {
    showNotice("Choose a listing from the list or enter an ID in the compare view.");
    return;
  }
  try {
    const data = await fetchJson(`/listings/${listingId}`);
    const listing = data.listing;
    const fields = Object.entries(listing.fields || {})
      .map(
        ([name, field]) => `
          <div class="field">
            <strong>${name}</strong>
            <span>${formatValue(field.value)}</span>
          </div>
          <div class="evidence-list">${renderEvidence(field)}</div>
        `
      )
      .join("");

    const historyData = await fetchJson(`/listings/${listingId}/history`);
    const historyRows = (historyData.history || [])
      .map(
        (entry) => `
          <tr>
            <td>${entry.field_path}</td>
            <td>${formatValue(entry.old_value)}</td>
            <td>${formatValue(entry.new_value)}</td>
            <td>${new Date(entry.changed_at).toLocaleDateString()}</td>
            <td><div class="evidence-list">${renderEvidence({ evidence: entry.evidence })}</div></td>
          </tr>
        `
      )
      .join("");

    setView(`
      <section class="panel">
        <h2>${listing.title}</h2>
        <p><strong>Listing ID:</strong> ${listing.listing_id}</p>
        <div class="field"><strong>Neighborhood</strong><span>${listing.neighborhood}</span></div>
        <div class="field"><strong>Snapshot</strong><span>${listing.snapshot_id}</span></div>
        ${fields}
      </section>
      <section class="panel">
        <h2>Change History</h2>
        <table class="table">
          <thead>
            <tr><th>Field</th><th>Old</th><th>New</th><th>Changed</th><th>Evidence</th></tr>
          </thead>
          <tbody>
            ${historyRows}
          </tbody>
        </table>
      </section>
    `);
  } catch (error) {
    showError(error.message);
  }
}

async function renderCompare() {
  setView(`
    <section class="panel">
      <h2>Compare Listings</h2>
      <p class="notice">Provide two listing IDs and optional snapshot IDs to verify cross-snapshot comparisons.</p>
      <div class="form-row">
        <div>
          <label>Listing ID (Left)</label>
          <input id="left-id" placeholder="uuid" />
        </div>
        <div>
          <label>Snapshot ID (Left)</label>
          <input id="left-snap" placeholder="optional" />
        </div>
        <div>
          <label>Listing ID (Right)</label>
          <input id="right-id" placeholder="uuid" />
        </div>
        <div>
          <label>Snapshot ID (Right)</label>
          <input id="right-snap" placeholder="optional" />
        </div>
      </div>
      <div style="margin-top:16px; display:flex; gap:12px; align-items:center;">
        <button id="compare-btn">Run compare</button>
        <span id="compare-error" class="error" style="display:none;"></span>
      </div>
      <div id="compare-results" style="margin-top:20px;"></div>
    </section>
  `);

  const button = document.getElementById("compare-btn");
  const errorEl = document.getElementById("compare-error");
  const resultsEl = document.getElementById("compare-results");

  button.addEventListener("click", async () => {
    errorEl.style.display = "none";
    resultsEl.innerHTML = "";
    const leftId = document.getElementById("left-id").value.trim();
    const rightId = document.getElementById("right-id").value.trim();
    const leftSnap = document.getElementById("left-snap").value.trim();
    const rightSnap = document.getElementById("right-snap").value.trim();

    if (!leftId || !rightId) {
      errorEl.textContent = "Both listing IDs are required.";
      errorEl.style.display = "inline-flex";
      return;
    }
    if (!uuidPattern.test(leftId) || !uuidPattern.test(rightId)) {
      errorEl.textContent = "Listing IDs must be valid UUIDs.";
      errorEl.style.display = "inline-flex";
      return;
    }

    try {
      const payload = {
        schema_version: "v1",
        listing_id_left: leftId,
        listing_id_right: rightId,
        snapshot_id_left: leftSnap || null,
        snapshot_id_right: rightSnap || null,
      };
      const data = await fetchJson("/compare", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const rows = data.comparison.fields
        .map(
          (row) => `
            <tr>
              <td>${row.field}</td>
              <td>${formatValue(row.left?.value)}</td>
              <td>${formatValue(row.right?.value)}</td>
              <td>${row.different ? "Yes" : "No"}</td>
              <td><div class="evidence-list">${renderEvidence(row.left)}</div></td>
              <td><div class="evidence-list">${renderEvidence(row.right)}</div></td>
            </tr>
          `
        )
        .join("");
      resultsEl.innerHTML = `
        <table class="table">
          <thead>
            <tr><th>Field</th><th>Left</th><th>Right</th><th>Different</th><th>Left Evidence</th><th>Right Evidence</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.style.display = "inline-flex";
    }
  });
}

async function renderNearMiss() {
  setView(`
    <section class="panel">
      <h2>Near-Miss Explorer</h2>
      <p class="notice">Review listings that narrowly miss a hard constraint.</p>
      <div class="form-row">
        <div>
          <label>SearchSpec ID</label>
          <input id="spec-id" placeholder="uuid" />
        </div>
        <div>
          <label>Threshold (0-1)</label>
          <input id="threshold" type="number" step="0.01" placeholder="0.1" />
        </div>
      </div>
      <div style="margin-top:16px; display:flex; gap:12px; align-items:center;">
        <button id="near-btn">Find near-miss</button>
        <span id="near-error" class="error" style="display:none;"></span>
      </div>
      <div id="near-results" style="margin-top:20px;"></div>
    </section>
  `);

  const button = document.getElementById("near-btn");
  const errorEl = document.getElementById("near-error");
  const resultsEl = document.getElementById("near-results");

  button.addEventListener("click", async () => {
    errorEl.style.display = "none";
    resultsEl.innerHTML = "";
    const specId = document.getElementById("spec-id").value.trim();
    const thresholdValue = document.getElementById("threshold").value.trim();
    const threshold = Number(thresholdValue);

    if (!specId) {
      errorEl.textContent = "SearchSpec ID is required.";
      errorEl.style.display = "inline-flex";
      return;
    }
    if (!uuidPattern.test(specId)) {
      errorEl.textContent = "SearchSpec ID must be a valid UUID.";
      errorEl.style.display = "inline-flex";
      return;
    }
    if (!thresholdValue || Number.isNaN(threshold) || threshold < 0 || threshold > 1) {
      errorEl.textContent = "Threshold must be a number between 0 and 1.";
      errorEl.style.display = "inline-flex";
      return;
    }

    try {
      const payload = { schema_version: "v1", search_spec_id: specId, threshold };
      const data = await fetchJson("/near-miss", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!data.near_miss.length) {
        resultsEl.innerHTML = "<p class=\"notice\">No near-miss listings found.</p>";
        return;
      }
      const cards = data.near_miss
        .map(
          (item) => `
          <div class="card">
            <h3>${item.title}</h3>
            <p><strong>Reason:</strong> ${item.reason}</p>
            <div class="field"><strong>Price</strong><span>${formatValue(item.price.value)}</span></div>
            <div class="evidence-list">${renderEvidence(item.price)}</div>
          </div>
        `
        )
        .join("");
      resultsEl.innerHTML = `<div class="card-grid">${cards}</div>`;
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.style.display = "inline-flex";
    }
  });
}

async function renderAlerts() {
  try {
    const data = await fetchJson("/alerts");
    const rows = data.alerts
      .map(
        (alert) => `
        <tr>
          <td>${alert.alert_id}</td>
          <td>${alert.listing_id}</td>
          <td>${alert.listing_change_id}</td>
          <td>${alert.status}</td>
          <td>${new Date(alert.created_at).toLocaleDateString()}</td>
        </tr>
      `
      )
      .join("");
    setView(`
      <section class="panel">
        <h2>Alerts</h2>
        <table class="table">
          <thead>
            <tr><th>Alert ID</th><th>Listing</th><th>Change</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </section>
    `);
  } catch (error) {
    showError(error.message);
  }
}

async function openEvidence(evidenceId) {
  try {
    const data = await fetchJson(`/evidence/${evidenceId}`);
    const evidence = data.evidence;
    drawerBody.innerHTML = `
      <p><strong>Evidence ID:</strong> ${evidence.evidence_id}</p>
      <p><strong>Snapshot:</strong> ${evidence.snapshot_id}</p>
      <p><strong>Excerpt:</strong> ${evidence.excerpt || "N/A"}</p>
      <button class="ghost" id="view-snapshot">View snapshot</button>
    `;
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    const viewBtn = document.getElementById("view-snapshot");
    viewBtn.addEventListener("click", async () => {
      const snapshotData = await fetchJson(`/snapshots/${evidence.snapshot_id}`);
      drawerBody.innerHTML = `
        <p><strong>Snapshot ID:</strong> ${snapshotData.snapshot.snapshot_id}</p>
        <p><strong>URL:</strong> ${snapshotData.snapshot.url}</p>
        <p><strong>Content hash:</strong> ${snapshotData.snapshot.content_hash}</p>
        <pre style="white-space:pre-wrap; font-family: var(--font-mono);">${snapshotData.snapshot.text}</pre>
      `;
    });
  } catch (error) {
    drawerBody.innerHTML = `<p class="error">${error.message}</p>`;
    drawer.classList.add("open");
  }
}

function router() {
  const hash = window.location.hash.replace("#", "") || "list";
  if (hash.startsWith("detail/")) {
    const listingId = hash.split("/")[1];
    renderDetail(listingId);
    return;
  }
  switch (hash) {
    case "list":
      renderList();
      break;
    case "compare":
      renderCompare();
      break;
    case "near-miss":
      renderNearMiss();
      break;
    case "alerts":
      renderAlerts();
      break;
    default:
      renderList();
  }
}

document.addEventListener("click", (event) => {
  const detailButton = event.target.closest("[data-detail-id]");
  if (detailButton) {
    const id = detailButton.getAttribute("data-detail-id");
    window.location.hash = `detail/${id}`;
  }

  const evidenceButton = event.target.closest("[data-evidence-id]");
  if (evidenceButton) {
    const evidenceId = evidenceButton.getAttribute("data-evidence-id");
    openEvidence(evidenceId);
  }
});

drawerClose.addEventListener("click", () => {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
});

window.addEventListener("hashchange", router);
window.addEventListener("load", router);
