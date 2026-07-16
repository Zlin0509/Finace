const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const currency = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });
const axisNumber = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 });
const percent = value => `${(Number(value || 0) * 100).toFixed(2)}%`;
const state = { view: "home", mode: "backtest", portfolio: null, chart: null };

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).error || message; } catch (_) {}
    throw new Error(message);
  }
  return response.headers.get("content-type")?.includes("json") ? response.json() : response.text();
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.className = "toast", 2800);
}

function setView(view) {
  state.view = view;
  const titles = { home: ["WELCOME", "欢迎首页"], overview: ["PORTFOLIO", "资产总览"], quant: ["RESEARCH LAB", "量化实验室"], settings: ["LOCAL SYSTEM", "本地数据与接口"] };
  document.body.classList.toggle("home-mode", view === "home");
  $(".topbar").setAttribute("aria-hidden", String(view === "home"));
  $$(".nav-item").forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  $$(".view").forEach(section => section.classList.toggle("active", section.id === `view-${view}`));
  $("#page-eyebrow").textContent = titles[view][0];
  $("#page-title").textContent = titles[view][1];
  if (view === "settings") loadSettings();
  if (view === "overview" || view === "home") loadPortfolio();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadPortfolio() {
  try {
    const snapshot = await api("/api/portfolio");
    state.portfolio = snapshot;
    $("#total-cost").textContent = currency.format(snapshot.total_cost || 0);
    $("#holding-count").textContent = snapshot.holdings.length;
    $("#transaction-count").textContent = snapshot.transactions.length;
    $("#welcome-cost").textContent = currency.format(snapshot.total_cost || 0);
    $("#welcome-holdings").textContent = snapshot.holdings.length;
    $("#allocation-total").textContent = currency.format(snapshot.total_cost || 0);
    $("#portfolio-updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
    renderHoldings(snapshot.holdings);
    renderTransactions(snapshot.transactions);
    requestAnimationFrame(() => drawAllocation(snapshot.holdings));
  } catch (error) { toast(error.message, true); }
}

function renderHoldings(holdings) {
  const body = $("#holdings-body");
  if (!holdings.length) { body.innerHTML = `<tr><td colspan="5" class="empty-row">暂无持仓记录</td></tr>`; return; }
  body.innerHTML = holdings.map(item => `<tr><td><strong>${item.fund_code}</strong></td><td class="num">${number.format(item.shares)}</td><td class="num">${currency.format(item.cost)}</td><td class="num">${number.format(item.unit_cost)}</td><td><span class="tag">持有中</span></td></tr>`).join("");
}

function renderTransactions(transactions) {
  const body = $("#recent-transactions");
  const items = [...transactions].reverse().slice(0, 7);
  if (!items.length) { body.innerHTML = `<tr><td colspan="4" class="empty-row">暂无交易</td></tr>`; return; }
  body.innerHTML = items.map(item => `<tr><td>${item.date}</td><td>${item.fund_code}</td><td><span class="tag ${item.action === "sell" ? "sell" : ""}">${item.action === "buy" ? "买入" : "卖出"}</span></td><td class="num">${number.format(item.amount)}</td></tr>`).join("");
}

function canvasContext(canvas, height) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 320);
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  return { context, width, height };
}

function drawAllocation(holdings) {
  const canvas = $("#allocation-chart");
  if (!canvas || !canvas.clientWidth) return;
  const { context, width, height } = canvasContext(canvas, 280);
  const total = holdings.reduce((sum, item) => sum + item.cost, 0);
  const colors = ["#1f6d4d", "#285ea8", "#a86413", "#8b4d79", "#4c6d83", "#b83a3a"];
  const compact = width < 460;
  const cx = compact ? width * .31 : Math.min(width * .34, 180), cy = height / 2, radius = compact ? Math.min(78, width * .21) : Math.min(96, width * .23);
  context.lineWidth = 26;
  context.strokeStyle = "#e8ebef";
  context.beginPath(); context.arc(cx, cy, radius, 0, Math.PI * 2); context.stroke();
  if (!total) {
    context.fillStyle = "#68717f"; context.font = "12px Avenir Next"; context.textAlign = "center"; context.fillText("暂无持仓", cx, cy + 4); return;
  }
  let start = -Math.PI / 2;
  holdings.forEach((item, index) => {
    const angle = item.cost / total * Math.PI * 2;
    context.strokeStyle = colors[index % colors.length]; context.beginPath(); context.arc(cx, cy, radius, start, start + angle); context.stroke(); start += angle;
  });
  context.textAlign = "center"; context.fillStyle = "#68717f"; context.font = "10px Avenir Next"; context.fillText("累计成本", cx, cy - 7);
  context.fillStyle = "#151a22"; context.font = "600 16px Georgia"; context.fillText(currency.format(total), cx, cy + 16);
  const legendX = compact ? width * .60 : Math.max(width * .62, cx + radius + 45);
  context.textAlign = "left";
  holdings.slice(0, 6).forEach((item, index) => {
    const y = 58 + index * 32; context.fillStyle = colors[index % colors.length]; context.fillRect(legendX, y - 8, 9, 9);
    context.fillStyle = "#151a22"; context.font = "11px Avenir Next"; context.fillText(item.fund_code, legendX + 18, y);
    context.fillStyle = "#68717f"; context.fillText(`${(item.cost / total * 100).toFixed(1)}%`, legendX + (compact ? 72 : 94), y);
  });
}

function openTrade() { const dialog = $("#trade-dialog"); $("#trade-form [name=date]").value = new Date().toISOString().slice(0, 10); dialog.showModal(); }

async function submitTrade(event) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  const payload = { ...values, amount: Number(values.amount), price: Number(values.price), fees: Number(values.fees || 0) };
  try { await api("/api/transactions", { method: "POST", body: JSON.stringify(payload) }); $("#trade-dialog").close(); event.currentTarget.reset(); toast("交易已保存到 SQLite"); loadPortfolio(); }
  catch (error) { toast(error.message, true); }
}

function setMode(mode) {
  const changed = state.mode !== mode;
  state.mode = mode;
  $$(".mode-tabs button").forEach(button => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  if (changed) {
    state.chart = null;
    $("#quant-results").classList.add("hidden");
  }
  $$(".optimizer-only").forEach(element => element.classList.toggle("hidden", mode !== "optimize"));
  $("#run-quant").textContent = mode === "optimize" ? "运行 Walk-Forward" : "运行策略回测";
  const strategy = $("#quant-form [name=strategy]");
  const buyHold = strategy.querySelector('option[value="buy_hold"]');
  buyHold.disabled = mode === "optimize";
  if (mode === "optimize" && strategy.value === "buy_hold") strategy.value = "ma_cross";
  const startDate = $("#quant-form [name=start]");
  if (mode === "optimize" && startDate.value === "2020-01-01") startDate.value = "2018-01-01";
  if (mode === "backtest" && startDate.value === "2018-01-01") startDate.value = "2020-01-01";
  toggleStrategy();
}

function toggleStrategy() {
  const strategy = $("#quant-form [name=strategy]").value;
  $$(".strategy-ma").forEach(element => element.classList.toggle("hidden", strategy !== "ma_cross"));
  $$(".strategy-momentum").forEach(element => element.classList.toggle("hidden", strategy !== "momentum"));
}

async function runQuant(event) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  const payload = {
    fund_code: values.fund_code, start: values.start, end: values.end, strategy: values.strategy,
    initial_capital: Number(values.initial_capital), commission_rate: Number(values.commission) / 100,
    slippage_rate: Number(values.slippage) / 100, short_window: Number(values.short_window || 20),
    long_window: Number(values.long_window || 60), momentum_window: Number(values.momentum_window || 60),
    momentum_threshold: Number(values.momentum_threshold || 0) / 100, train_days: Number(values.train_days || 488),
    test_days: Number(values.test_days || 122), objective: values.objective || "balanced", search_depth: values.search_depth || "standard"
  };
  const status = $("#quant-status"); status.textContent = state.mode === "optimize" ? "Go Core 正在滚动搜索参数并验证样本外窗口…" : "Go Core 正在获取净值并执行单次回测…"; status.classList.remove("hidden");
  $("#run-quant").disabled = true;
  try {
    const result = await api(`/api/quant/${state.mode}`, { method: "POST", body: JSON.stringify(payload) });
    state.chart = result; renderQuant(result); status.classList.add("hidden");
  } catch (error) { status.textContent = error.message; toast(error.message, true); }
  finally { $("#run-quant").disabled = false; }
}

function renderQuant(result) {
  $("#quant-results").classList.remove("hidden");
  const metrics = state.mode === "backtest"
    ? [["期末权益", currency.format(result.metrics.final_equity)], ["累计收益", percent(result.metrics.total_return)], ["年化收益", percent(result.metrics.annual_return)], ["最大回撤", percent(result.metrics.max_drawdown)], ["夏普比率", result.metrics.sharpe_ratio.toFixed(2)], ["超额收益", percent(result.metrics.excess_return)]]
    : [["推荐参数", result.recommended_label], ["可靠性", `${result.diagnostics.reliability_score.toFixed(0)}/100 ${result.diagnostics.grade}`], ["样本外收益", percent(result.oos_return)], ["超额收益", percent(result.excess_return)], ["最大回撤", percent(result.max_drawdown)], ["夏普比率", result.sharpe.toFixed(2)]];
  $("#quant-metrics").innerHTML = metrics.map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>Go native result</small></div>`).join("");
  if (state.mode === "backtest") {
    $("#quant-diagnostics").classList.add("hidden");
    $("#chart-title").textContent = "策略权益与买入持有"; $("#quant-meta").textContent = `${result.curve.length} 个交易日 · ${result.metrics.trade_count} 次交易`;
    $("#fold-section").classList.add("hidden"); requestAnimationFrame(() => drawEquity(result.curve));
  } else {
    const diagnostics = result.diagnostics;
    $("#quant-diagnostics").classList.remove("hidden");
    $("#diagnostic-verdict").textContent = `${diagnostics.grade} · ${diagnostics.verdict}`;
    $("#diagnostic-stability").textContent = percent(diagnostics.parameter_stability);
    $("#diagnostic-positive").textContent = percent(diagnostics.positive_fold_rate);
    $("#diagnostic-outperform").textContent = percent(diagnostics.outperform_fold_rate);
    $("#diagnostic-gap").textContent = diagnostics.overfit_gap.toFixed(2);
    $("#chart-title").textContent = "验证窗口收益对比"; $("#quant-meta").textContent = `${result.fold_count} 个窗口 · ${result.candidate_count} 组参数`;
    $("#fold-section").classList.remove("hidden"); renderFolds(result.folds); requestAnimationFrame(() => drawFolds(result.folds));
  }
  $("#quant-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function chartFrame(canvas, minValue, maxValue, formatter) {
  const frame = canvasContext(canvas, 410), c = frame.context, w = frame.width, h = frame.height;
  const box = { left: 62, right: w - 24, top: 34, bottom: h - 42 };
  c.strokeStyle = "#e1e5ea"; c.lineWidth = 1; c.font = "10px Avenir Next"; c.fillStyle = "#68717f";
  for (let i = 0; i <= 4; i++) {
    const y = box.top + (box.bottom-box.top) * i / 4;
    const value = maxValue - (maxValue-minValue) * i / 4;
    c.beginPath(); c.moveTo(box.left,y); c.lineTo(box.right,y); c.stroke();
    c.textAlign = "right"; c.fillText(formatter(value), box.left-8, y+3);
  }
  c.textAlign = "left";
  return { ...frame, box };
}

function drawEquity(curve) {
  if (!curve.length) return;
  const values = curve.flatMap(point => [point.equity, point.benchmark_equity]); const minV = Math.min(...values), maxV = Math.max(...values), span = maxV-minV || 1;
  const canvas = $("#equity-chart"), { context:c, box } = chartFrame(canvas, minV, maxV, value => `¥${axisNumber.format(value)}`);
  const draw = (key, color, dash=[]) => { c.strokeStyle=color;c.lineWidth=2;c.setLineDash(dash);c.beginPath();curve.forEach((point,index)=>{const x=box.left+(box.right-box.left)*index/Math.max(curve.length-1,1);const y=box.bottom-(point[key]-minV)/span*(box.bottom-box.top);index?c.lineTo(x,y):c.moveTo(x,y)});c.stroke();c.setLineDash([]); };
  draw("equity","#1f6d4d");draw("benchmark_equity","#68717f",[5,4]);
  c.fillStyle="#1f6d4d";c.fillRect(box.left,14,18,2);c.fillStyle="#151a22";c.fillText("策略权益",box.left+25,18);c.strokeStyle="#68717f";c.setLineDash([4,3]);c.beginPath();c.moveTo(box.left+95,15);c.lineTo(box.left+113,15);c.stroke();c.setLineDash([]);c.fillText("买入持有",box.left+120,18);
  c.fillStyle="#68717f";c.font="10px Avenir Next";c.fillText(curve[0].date,box.left,box.bottom+24);c.textAlign="right";c.fillText(curve[curve.length-1].date,box.right,box.bottom+24);c.textAlign="left";
}

function drawFolds(folds) {
  if (!folds.length) return;
  const maxAbs = Math.max(.01,...folds.flatMap(item=>[Math.abs(item.test_return),Math.abs(item.benchmark_return)]));
  const canvas = $("#equity-chart"), { context:c, box } = chartFrame(canvas, -maxAbs, maxAbs, value => `${(value*100).toFixed(0)}%`);
  const zero = (box.top+box.bottom)/2;
  c.strokeStyle="#9ca6b2";c.beginPath();c.moveTo(box.left,zero);c.lineTo(box.right,zero);c.stroke();
  const group=(box.right-box.left)/folds.length; folds.forEach((fold,index)=>{const center=box.left+group*(index+.5);[[fold.test_return,"#1f6d4d",-7],[fold.benchmark_return,"#9ca6b2",7]].forEach(([value,color,offset])=>{const height=Math.abs(value)/maxAbs*(box.bottom-box.top)/2*.88;c.fillStyle=color;c.fillRect(center+offset-5,value>=0?zero-height:zero,10,height)});c.fillStyle="#68717f";c.textAlign="center";c.fillText(String(fold.fold),center,box.bottom+18)});c.textAlign="left";
  c.fillStyle="#1f6d4d";c.fillRect(box.left,14,12,8);c.fillStyle="#151a22";c.fillText("策略",box.left+18,22);c.fillStyle="#9ca6b2";c.fillRect(box.left+66,14,12,8);c.fillStyle="#151a22";c.fillText("基准",box.left+84,22);
}

function renderFolds(folds) { $("#fold-body").innerHTML = folds.map(fold => `<tr><td>${fold.fold}</td><td>${fold.test_start} – ${fold.test_end}</td><td>${fold.parameter_label}</td><td class="num">${percent(fold.test_return)}</td><td class="num">${percent(fold.benchmark_return)}</td><td class="num">${fold.sharpe.toFixed(2)}</td></tr>`).join(""); }

async function loadSettings() {
  try {
    const [storage, llm] = await Promise.all([api("/api/storage"), api("/api/settings/llm")]);
    $("#storage-stats").innerHTML = `<div><small>交易记录</small><strong>${storage.transaction_count}</strong></div><div><small>配置项</small><strong>${storage.setting_count}</strong></div><div><small>数据库</small><strong>${(storage.size_bytes/1024).toFixed(1)} KB</strong></div>`;
    $("#database-path").value = storage.database_path;
    const form = $("#llm-form"); ["provider","base_url","model","timeout_seconds","max_tokens"].forEach(name => { if (llm[name] !== undefined && form.elements[name]) form.elements[name].value = llm[name]; });
    form.elements.api_key.placeholder = llm.api_key_saved ? "已保存，留空保持不变" : "输入 API Key";
  } catch (error) { toast(error.message, true); }
}

async function saveLLM(event) { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); values.timeout_seconds=Number(values.timeout_seconds);values.max_tokens=Number(values.max_tokens);try{await api("/api/settings/llm",{method:"PUT",body:JSON.stringify(values)});toast("模型配置已保存到 SQLite");loadSettings()}catch(error){toast(error.message,true)} }
async function backupDatabase() { try { const result=await api("/api/storage/backup",{method:"POST",body:"{}"});toast(`备份完成：${result.path}`);loadSettings(); } catch(error){toast(error.message,true)} }

function initialize() {
  $("#clock").textContent = new Date().toLocaleDateString("zh-CN", { year:"numeric", month:"2-digit", day:"2-digit" });
  const today = new Date().toISOString().slice(0,10); $("#quant-form [name=end]").value=today; $("#trade-form [name=date]").value=today;
  $$(".nav-item").forEach(button => button.addEventListener("click",()=>setView(button.dataset.view)));
  $("#enter-workbench").addEventListener("click",()=>setView("overview")); $("#enter-quant").addEventListener("click",()=>setView("quant"));
  [$("#open-trade"),$("#open-trade-inline")].forEach(button=>button.addEventListener("click",openTrade));
  $("#trade-form").addEventListener("submit",submitTrade); $("#refresh").addEventListener("click",()=>setView(state.view));
  $$(".mode-tabs button").forEach(button=>button.addEventListener("click",()=>setMode(button.dataset.mode)));
  $("#quant-form [name=strategy]").addEventListener("change",toggleStrategy); $("#quant-form").addEventListener("submit",runQuant);
  $("#llm-form").addEventListener("submit",saveLLM); $("#backup-db").addEventListener("click",backupDatabase);
  window.addEventListener("resize",()=>{if(state.view==="overview"&&state.portfolio)drawAllocation(state.portfolio.holdings);if(state.view==="quant"&&state.chart){state.mode==="backtest"?drawEquity(state.chart.curve):drawFolds(state.chart.folds)}});
  loadPortfolio(); api("/api/version").then(value=>$("#runtime-version").textContent=`v${value.version}`).catch(()=>{});
}
document.addEventListener("DOMContentLoaded",initialize);
