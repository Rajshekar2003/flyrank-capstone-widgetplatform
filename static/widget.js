(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || !script.src) { return; }
  var src = new URL(script.src);
  var widgetId = src.searchParams.get("id");
  if (!widgetId) { return; }
  var origin = src.origin;
  var FIELD_TYPES = { text: "text", email: "email", tel: "tel", url: "url" };
  var CSS = [
    ":host{all:initial;display:block;font-family:system-ui,sans-serif;font-size:14px;color:#1a1a1a}",
    ".box{background:#fff;border:1px solid #d8d8d8;border-radius:10px;padding:16px;width:320px;max-width:100%;box-sizing:border-box}",
    "h3{margin:0 0 6px;font-size:16px}",
    "p{margin:0 0 10px;color:#555}",
    "label{display:block;margin:8px 0 2px;font-weight:600}",
    "input,textarea{width:100%;box-sizing:border-box;padding:8px;border:1px solid #bbb;border-radius:6px;font:inherit}",
    "button{margin-top:12px;padding:9px 14px;border:0;border-radius:6px;background:var(--c);color:#fff;font:inherit;cursor:pointer}",
    "button.toggle{margin:0}",
    "button[disabled]{opacity:.6;cursor:default}",
    ".msg{margin-top:10px;min-height:1em}",
    ".err{color:#b00020}.ok{color:#116611}",
    ".hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}"
  ].join("");

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    }
    if (text) { node.textContent = text; }
    return node;
  }

  function safeColor(value) {
    return /^#[0-9a-fA-F]{3,8}$/.test(value || "") ? value : "#0f3d3a";
  }

  function buildForm(cfg) {
    var form = el("form");
    var inputs = [];
    cfg.form_fields.forEach(function (f, i) {
      var id = "f" + i;
      form.appendChild(el("label", { "for": id }, f.label));
      var input = f.type === "textarea"
        ? el("textarea", { rows: "3" })
        : el("input", { type: FIELD_TYPES[f.type] || "text" });
      input.id = id;
      input.name = f.name;
      if (f.required) { input.required = true; }
      form.appendChild(input);
      inputs.push(input);
    });
    var hp = el("div", { "class": "hp", "aria-hidden": "true" });
    var hpInput = el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" });
    hp.appendChild(hpInput);
    form.appendChild(hp);
    var btn = el("button", { type: "submit" }, cfg.button_text || "Submit");
    var msg = el("div", { "class": "msg", role: "status" });
    form.appendChild(btn);
    form.appendChild(msg);

    function setMsg(text, kind) {
      msg.textContent = text;
      msg.className = "msg " + kind;
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fields = {};
      cfg.form_fields.forEach(function (f, i) {
        var v = inputs[i].value.trim();
        if (v) { fields[f.name] = v; }
      });
      var body = { widget_id: widgetId, fields: fields };
      if (hpInput.value) { body.website = hpInput.value; }
      btn.disabled = true;
      setMsg("", "");
      fetch(origin + "/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(function (r) {
        if (r.ok) {
          form.reset();
          setMsg("Thanks! Your response was received.", "ok");
          return;
        }
        if (r.status === 429) {
          var s = r.headers.get("Retry-After");
          setMsg("Too many attempts. Please try again" + (s ? " in " + s + " seconds." : " shortly."), "err");
          return;
        }
        return r.json().then(function (j) {
          setMsg(typeof j.detail === "string" ? j.detail : "Please check your answers.", "err");
        }, function () {
          setMsg("Something went wrong. Please try again.", "err");
        });
      }).catch(function () {
        setMsg("Network error. Please try again.", "err");
      }).then(function () {
        btn.disabled = false;
      });
    });
    return form;
  }

  function render(cfg) {
    var host = el("div", { "data-widget-id": widgetId });
    var root = host.attachShadow({ mode: "open" });
    host.style.setProperty("--c", safeColor(cfg.display_options && cfg.display_options.color));
    root.appendChild(el("style", null, CSS));
    var box = el("div", { "class": "box" });
    box.appendChild(el("h3", null, cfg.title));
    if (cfg.description) { box.appendChild(el("p", null, cfg.description)); }
    box.appendChild(buildForm(cfg));

    if (cfg.type === "cta_popover") {
      var pos = (cfg.display_options && cfg.display_options.position) || "bottom-right";
      var bottom = pos.indexOf("bottom") === 0;
      var right = pos.slice(-5) === "right";
      host.style.cssText += ";position:fixed;z-index:2147483000;" +
        (bottom ? "bottom:20px;" : "top:20px;") + (right ? "right:20px;" : "left:20px;");
      var wrap = el("div");
      wrap.style.cssText = "display:flex;gap:8px;flex-direction:" + (bottom ? "column-reverse" : "column") +
        ";align-items:" + (right ? "flex-end" : "flex-start");
      var toggle = el("button", { type: "button", "class": "toggle" }, cfg.title);
      box.style.display = "none";
      toggle.addEventListener("click", function () {
        box.style.display = box.style.display === "none" ? "block" : "none";
      });
      wrap.appendChild(toggle);
      wrap.appendChild(box);
      root.appendChild(wrap);
      document.body.appendChild(host);
    } else {
      root.appendChild(box);
      script.parentNode.insertBefore(host, script);
    }
  }

  fetch(origin + "/widgets/" + encodeURIComponent(widgetId) + "/config")
    .then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    })
    .then(function (cfg) {
      if (cfg && Array.isArray(cfg.form_fields)) { render(cfg); }
    })
    .catch(function (e) {
      console.warn("widget: could not load (" + e.message + ")");
    });
})();
