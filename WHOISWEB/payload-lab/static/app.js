// [J01] State giao diện (lưu localStorage) + áp dụng theme/font/title/hero
const $ = s => document.querySelector(s);
const DEFT = {title: "Payload Lab", hero: "NẠP PAYLOAD CỦA BẠN VÔ ĐI"};
const DEF = {vars: {}, font: null, title: null, hero: null, rep: []};
let st = {...DEF, ...JSON.parse(localStorage.getItem("st") || "{}")};
function applyState() {
  const r = document.documentElement.style; r.cssText = "";
  for (const [k, v] of Object.entries(st.vars))
    if (/^--(bg|card|text|accent|muted)$/.test(k)) r.setProperty(k, v);   // whitelist biến
  if (st.font) r.setProperty("--fs", st.font + "px");
  $("#site-title").textContent = st.title || DEFT.title;
  $("#hero").textContent = st.hero || DEFT.hero;
  replaceAll();
}
// [J02] Lệnh "replace": thay chữ trên mọi text node (giữ bản gốc trong WeakMap để reset được)
const orig = new WeakMap();
function replaceAll() {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (n.parentElement.closest("script,style,textarea,#console")) continue;
    if (!orig.has(n)) orig.set(n, n.nodeValue);
    n.nodeValue = st.rep.reduce((s, x) => s.split(x.a).join(x.b), orig.get(n));
  }
  document.title = st.title || DEFT.title;
}
// [J03] Nhận "hiệu ứng" từ server và cập nhật state
function applyFx(fx) {
  for (const e of fx) {
    if (e.t === "vars") Object.assign(st.vars, e.v);
    else if (e.t === "font") st.font = e.v;
    else if (e.t === "title" || e.t === "hero") st[e.t] = e.v;
    else if (e.t === "replace") st.rep.push({a: e.a, b: e.b});
    else if (e.t === "reset") st = structuredClone(DEF);
  }
  localStorage.setItem("st", JSON.stringify(st)); applyState();
}
// [J04] Form nạp payload: gửi /api/exec, in kết quả ra console
$("#exec-form").onsubmit = async ev => {
  ev.preventDefault();
  const input = $("#exec-input").value;
  const r = await fetch("/api/exec", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({input})});
  const d = await r.json().catch(() => ({ok: false, out: "Lỗi server."}));
  $("#console").textContent = `$ ${input}\n${d.out}`;
  $("#console").className = r.ok && d.ok ? "ok" : "err";
  if (d.fx) applyFx(d.fx);
};
// [J05] Render feed (chỉ dùng textContent, không innerHTML) + nút Like/Comment
const el = (t, c, txt) => { const e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; };
const post = (url, body) => fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
let filter = "all";
function card(p) {
  const c = el("article", "card " + p.kind), h = el("div", "head");
  h.append(el("strong", "", (p.kind === "image" ? "Ảnh" : "Text") + " #" + p.id), el("span", "muted", new Date(p.ts * 1000).toLocaleString("vi-VN")));
  c.append(h);
  if (p.image) { const i = el("img"); i.src = "/uploads/" + encodeURIComponent(p.image); i.alt = "Ảnh của bài " + p.id; c.append(i); }
  if (p.body) c.append(el("p", "", p.body));
  const bar = el("div", "bar"), cb = el("button", "", "Comment");
  if (p.kind === "text") {                       // bài ảnh KHÔNG có Like, chỉ có Comment
    const lb = el("button", "", "Like " + p.likes);
    lb.onclick = async () => { await post(`/api/posts/${p.id}/like`); load(); };
    bar.append(lb);
  }
  bar.append(cb); c.append(bar);
  const list = el("ul", "comments"); p.comments.forEach(t => list.append(el("li", "", t))); c.append(list);
  const f = el("form", "cform"), inp = el("input"); f.hidden = true; inp.maxLength = 200; inp.placeholder = "Viết comment";
  f.append(inp, el("button", "", "Gửi")); c.append(f);
  f.onsubmit = async ev => { ev.preventDefault(); if (inp.value.trim()) { await post(`/api/posts/${p.id}/comments`, {body: inp.value}); load(); } };
  cb.onclick = () => { f.hidden = !f.hidden; inp.focus(); };
  return c;
}
async function load() {
  const posts = await (await fetch("/api/posts?filter=" + filter)).json();
  $("#feed").replaceChildren(...(posts.length ? posts.map(card) : [el("p", "muted", "Chưa có bài nào. Hãy đăng bài đầu tiên.")]));
  replaceAll();
}
// [J06] Đăng bài (FormData) + bộ lọc + khởi động
$("#post-form").onsubmit = async ev => {
  ev.preventDefault();
  const r = await fetch("/api/posts", {method: "POST", body: new FormData(ev.target)});
  if (!r.ok) { alert((await r.json().catch(() => ({}))).error || "Không đăng được bài."); return; }
  ev.target.reset(); load();
};
document.querySelectorAll("#filters button").forEach(b => b.onclick = () => {
  filter = b.dataset.f;
  document.querySelectorAll("#filters button").forEach(x => x.classList.toggle("on", x === b));
  load();
});
applyState(); load();
