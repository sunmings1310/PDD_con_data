const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  return res.json();
}

function fmtTime(v) {
  if (!v) return "-";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return String(v);
  }
}

function badge(status, online) {
  if (online === true) return `<span class="badge online">在线</span>`;
  if (online === false) return `<span class="badge offline">离线</span>`;
  const cls = ["pending", "running", "done", "failed", "busy", "online", "offline"].includes(status)
    ? status
    : "offline";
  return `<span class="badge ${cls}">${status || "-"}</span>`;
}

function fillPlatformSelects(list) {
  const optsAll = `<option value="">全部平台</option>` +
    list.map((p) => `<option value="${p.platform_code}">${p.platform_name}</option>`).join("");
  const optsTask = list
    .map(
      (p) =>
        `<option value="${p.platform_code}" ${p.platform_code === "pinduoduo" ? "selected" : ""}>${p.platform_name}${
          p.enabled ? "" : "（预留）"
        }</option>`
    )
    .join("");
  ["devicePlatform", "prodPlatform"].forEach((id) => {
    $(id).innerHTML = optsAll;
  });
  $("taskPlatform").innerHTML = optsTask;
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("healthMeta").textContent = h.ok ? `Oracle ${h.oracle}` : "服务异常";
  } catch {
    $("healthMeta").textContent = "服务未连接";
  }
}

async function loadDevices() {
  const p = $("devicePlatform").value;
  const q = p ? `?platform_code=${encodeURIComponent(p)}` : "";
  const res = await api(`/api/devices${q}`);
  const rows = res.data || [];
  $("deviceBody").innerHTML = rows
    .map(
      (d) => `<tr>
      <td>${badge(d.status, d.online)}</td>
      <td>${d.device_name || d.device_key}<div style="color:#5b6b7c;font-size:12px">${d.device_key}</div></td>
      <td>${d.platform_code}</td>
      <td>${d.model || "-"}</td>
      <td>${d.app_version || "-"}</td>
      <td>${d.last_ip || "-"}</td>
      <td>${fmtTime(d.last_heartbeat)}</td>
      <td>${d.current_task_id || "-"}</td>
    </tr>`
    )
    .join("");

  const online = rows.filter((d) => d.online);
  $("taskDevice").innerHTML =
    `<option value="">自动分配在线设备</option>` +
    online
      .map((d) => `<option value="${d.device_id}">${d.device_name || d.device_key}</option>`)
      .join("");
}

async function loadTasks() {
  const st = $("taskStatusFilter").value;
  const q = st ? `?status=${encodeURIComponent(st)}` : "";
  const res = await api(`/api/tasks${q}`);
  const rows = res.data || [];
  $("taskBody").innerHTML = rows
    .map(
      (t) => `<tr>
      <td>${t.task_id}</td>
      <td>${t.task_name}</td>
      <td>${t.task_type}</td>
      <td>${t.platform_code}</td>
      <td>${badge(t.status)}</td>
      <td>${t.success_count || 0}/${t.fail_count || 0}</td>
      <td>${t.device_id || "-"}</td>
      <td>${fmtTime(t.create_time)}</td>
    </tr>`
    )
    .join("");
}

async function createTask() {
  const keywords = ($("taskKeywords").value || "")
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
  const body = {
    task_name: $("taskName").value.trim() || `任务-${new Date().toLocaleString()}`,
    task_type: $("taskType").value,
    platform_code: $("taskPlatform").value,
    keywords,
    device_id: $("taskDevice").value ? Number($("taskDevice").value) : null,
    target_count: keywords.length,
  };
  const res = await api("/api/tasks", { method: "POST", body: JSON.stringify(body) });
  $("taskMsg").textContent = res.ok
    ? `已创建任务 #${res.data.task_id}`
    : res.message || "失败";
  if (res.ok) {
    $("taskKeywords").value = "";
    loadTasks();
  }
}

async function searchProducts() {
  const params = new URLSearchParams();
  if ($("prodPlatform").value) params.set("platform_code", $("prodPlatform").value);
  if ($("prodKeyword").value.trim()) params.set("keyword", $("prodKeyword").value.trim());
  if ($("prodItemId").value.trim()) params.set("item_id", $("prodItemId").value.trim());
  if ($("prodApproval").value.trim()) params.set("approval_no", $("prodApproval").value.trim());
  const res = await api(`/api/products?${params}`);
  const items = (res.data && res.data.items) || [];
  $("prodBody").innerHTML = items
    .map(
      (p) => `<tr class="clickable" data-id="${p.product_id}">
      <td>${p.product_id}</td>
      <td>${p.platform_code}</td>
      <td>${p.keyword || "-"}</td>
      <td>${p.item_id || "-"}</td>
      <td>${p.sell_name || p.product_name || "-"}</td>
      <td>${p.shop_name || "-"}</td>
      <td>${p.display_price ?? p.deal_price ?? p.price ?? "-"}</td>
      <td>${p.approval_no || "-"}</td>
      <td>${fmtTime(p.collect_time)}</td>
    </tr>`
    )
    .join("");
  $("prodDetail").classList.add("hidden");
  $("prodBody").querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => showProduct(tr.dataset.id));
  });
}

async function showProduct(id) {
  const res = await api(`/api/products/${id}`);
  if (!res.ok) return;
  const p = res.data;
  const imgs = (p.images || [])
    .map((img) => {
      const src = img.url || img.source_url;
      return src ? `<img src="${src}" alt="" />` : "";
    })
    .join("");
  $("prodDetail").classList.remove("hidden");
  $("prodDetail").innerHTML = `
    <h3>#${p.product_id} ${p.sell_name || p.product_name || ""}</h3>
    <div>链接：${p.item_url ? `<a href="${p.item_url}" target="_blank">${p.item_url}</a>` : "-"}</div>
    <div>厂家：${p.manufacturer || "-"} ｜ 规格：${p.spec_text || "-"} ｜ 准字：${p.approval_no || "-"}</div>
    <div style="margin-top:8px">${imgs || "暂无图片"}</div>
  `;
}

function bindTabs() {
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

async function boot() {
  bindTabs();
  await loadHealth();
  const plat = await api("/api/platforms");
  fillPlatformSelects(plat.data || []);
  $("btnRefreshDevices").onclick = loadDevices;
  $("devicePlatform").onchange = loadDevices;
  $("btnRefreshTasks").onclick = loadTasks;
  $("taskStatusFilter").onchange = loadTasks;
  $("btnCreateTask").onclick = createTask;
  $("btnSearchProd").onclick = searchProducts;
  await loadDevices();
  await loadTasks();
  await searchProducts();
  setInterval(loadDevices, 15000);
}

boot();
