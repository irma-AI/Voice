// Turn: the landing page's example call. A ring on wide screens, a rail on phones (the switch is in CSS).
// The call itself lives in the page as #turn-script, which screen readers read; this file only draws it.
// Pause stops the motion (WCAG 2.2.2); reduced motion starts paused on one complete still frame.
(() => {
  const script = document.getElementById("turn-script");
  if (!script) return;
  const SVG = "http://www.w3.org/2000/svg";
  const LOOP = Number(script.dataset.loop);
  const STILL = 30; // the booking moved and confirmed: what works today with a Module, never the planned Hand-off as live speech
  const num = (v) => Number(v);
  const LINES = [...script.querySelectorAll("[data-line]")].map((li) => ({
    t: num(li.dataset.t), end: num(li.dataset.end), who: li.dataset.who, planned: li.hasAttribute("data-planned"),
    say: li.textContent.slice(li.dataset.who.length + 2),
  }));
  const STEPS = [...script.querySelectorAll("[data-step]")].map((li) => ({
    t: num(li.dataset.t), name: li.dataset.name, note: li.dataset.note, planned: li.hasAttribute("data-planned"),
  }));
  const el = (name) => document.querySelector(`[data-turn="${name}"]`);
  const make = (tag, attrs) => {
    const node = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  };

  // The ring: 120 ticks, the progress arc, a dot per step with its label.
  const R = 230, C = 2 * Math.PI * R, FILL = LOOP - 3;
  const angleAt = (t) => (t / LOOP) * 2 * Math.PI - Math.PI / 2;
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * 2 * Math.PI - Math.PI / 2, major = i % 10 === 0, r1 = major ? 244 : 248;
    el("ticks").appendChild(make("line", {
      x1: Math.cos(a) * r1, y1: Math.sin(a) * r1, x2: Math.cos(a) * 256, y2: Math.sin(a) * 256,
      class: major ? "turn-tick major" : "turn-tick",
    }));
  }
  const progress = el("progress");
  const stepEls = STEPS.map((s) => {
    const a = angleAt(s.t), x = Math.cos(a) * R, y = Math.sin(a) * R;
    const right = Math.cos(a) >= -0.05, anchor = right ? "start" : "end";
    // A planned step leaves the ring by a dashed exit; its label sits past the exit's end, clear of the line.
    const out = s.planned ? R + 78 : R + 40, lift = s.planned ? -18 : 0;
    const lx = Math.cos(a) * out, ly = Math.sin(a) * out + lift;
    const g = make("g", { class: "turn-step" + (s.planned ? " planned" : "") });
    g.appendChild(make("circle", { class: "turn-dot", cx: x, cy: y, r: 6 }));
    const name = make("text", { class: "turn-step-name", x: lx, y: ly - 5, "text-anchor": anchor });
    name.textContent = s.name;
    const note = make("text", { class: "turn-step-note", x: lx, y: ly + 15, "text-anchor": anchor });
    note.textContent = s.note;
    g.append(name, note);
    el("steps").appendChild(g);
    if (s.planned) {
      const exit = el("exit");
      exit.setAttribute("x1", x); exit.setAttribute("y1", y);
      exit.setAttribute("x2", Math.cos(a) * (R + 66)); exit.setAttribute("y2", Math.sin(a) * (R + 66));
    }
    return g;
  });
  const railEls = STEPS.map((s) => {
    const dot = make("ellipse", {
      cx: 20, cy: (s.t / LOOP) * 1000, rx: 6, ry: 6, "vector-effect": "non-scaling-stroke",
      class: "turn-rail-dot" + (s.planned ? " planned" : ""),
    });
    el("rail-dots").appendChild(dot);
    return dot;
  });

  // A spoken line wraps inside the ring at about 24 characters, on a word boundary.
  function setLine(g, line) {
    const [who, say] = g.querySelectorAll("text");
    who.textContent = line ? line.who : "";
    say.textContent = "";
    // Only what is live is warm: never the previous line, and never words from a Planned step, which nothing does yet.
    g.classList.toggle("agent", g === cur && !!line && line.who === "Agent" && !line.planned);
    g.classList.toggle("planned", !!line && line.planned);
    g.classList.toggle("on", !!line);
    if (!line) return;
    const rows = [""];
    for (const word of line.say.split(" ")) {
      const last = rows.length - 1;
      if (rows[last] && (rows[last] + " " + word).length > 24) rows.push(word);
      else rows[last] = rows[last] ? rows[last] + " " + word : word;
    }
    rows.forEach((row, i) => {
      const span = make("tspan", { x: say.getAttribute("x"), dy: i ? "1.1em" : "0" });
      span.textContent = row;
      say.appendChild(span);
    });
  }

  // The speaker line: flat in silence, moving with the voice, warm when the Agent speaks.
  function wavePath(path, t, half, amp, tight) {
    let d = "";
    for (let x = -half; x <= half; x += 4) {
      const env = Math.cos((x / half) * (Math.PI / 2)) ** 2;
      const y = env * amp * (Math.sin(x * 0.045 * tight + t * 6) * 0.6 + Math.sin(x * 0.11 * tight - t * 9) * 0.3 + Math.sin(x * 0.023 + t * 2.3) * 0.4);
      d += (x === -half ? "M" : "L") + x + " " + y.toFixed(2) + " ";
    }
    path.setAttribute("d", d);
    const line = amp && speaking(t);
    path.setAttribute("class", "turn-wave " + (!line ? "quiet" : line.planned ? "planned" : line.who === "Agent" ? "agent" : "caller"));
  }
  const speaking = (t) => LINES.find((l) => t >= l.t && t <= l.end);
  const lastIndex = (t) => LINES.reduce((acc, l, i) => (t >= l.t ? i : acc), -1);
  const envelope = (t, line, size) => (line ? size * Math.min(1, (t - line.t) * 3, (line.end - t) * 3) : 0);

  const ringLive = el("live"), cur = el("cur"), prev = el("prev"), exit = el("exit");
  const rail = document.querySelector(".turn-rail"), railFill = el("rail-fill");
  const live = {
    name: el("step-name"), note: el("step-note"), who: el("live-who"), say: el("live-say"), wave: el("wave-small"),
  };
  let shown = null;

  // `stepsAt` lets the still frame draw every step (the Hand-off included) while its words stay at `t`.
  function render(t, stepsAt = t) {
    const frac = Math.min(t / FILL, 1), line = speaking(t), idx = lastIndex(t);
    // Ring
    progress.style.strokeDasharray = `${frac * C} ${C}`;
    STEPS.forEach((s, i) => stepEls[i].classList.toggle("on", stepsAt >= s.t));
    exit.classList.toggle("on", STEPS.some((s) => s.planned && stepsAt >= s.t));
    if (idx !== shown) {
      shown = idx;
      setLine(prev, LINES[idx - 1]);
      setLine(cur, LINES[idx]);
      const l = LINES[idx];
      live.who.textContent = l ? l.who : "";
      live.say.textContent = l ? l.say : "";
      live.say.classList.toggle("agent", !!l && l.who === "Agent" && !l.planned);
      live.say.classList.toggle("planned", !!l && l.planned);
    }
    wavePath(el("wave"), t, 210, envelope(t, line, 26), 1);
    ringLive.style.opacity = t > LOOP - 2 ? Math.max(0, (LOOP - t) / 2) : Math.min(1, t * 2 + 0.2);
    // Rail
    // The rail stretches to the hero's height, so each dot is drawn back to a 5px circle on screen.
    const box = rail.getBoundingClientRect(), kx = 40 / (box.width || 40), ky = 1000 / (box.height || 1000);
    railEls.forEach((dot, i) => {
      dot.classList.toggle("on", stepsAt >= STEPS[i].t);
      dot.setAttribute("rx", 5 * kx); dot.setAttribute("ry", 5 * ky);
    });
    railFill.setAttribute("y2", frac * 1000);
    const step = [...STEPS].reverse().find((s) => t >= s.t);
    live.name.textContent = step ? step.name : "";
    live.note.textContent = step ? step.note : "";
    live.note.classList.toggle("planned", !!step && step.planned);
    wavePath(live.wave, t, 160, envelope(t, line, 18), 1.3);
  }

  const toggles = document.querySelectorAll(".turn-toggle");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let paused = reduce, held = reduce ? STILL : 0, start = performance.now(), raf = 0;
  function frame(now) {
    held = ((now - start) / 1000) % LOOP;
    render(held);
    raf = requestAnimationFrame(frame);
  }
  function setPaused(value) {
    paused = value;
    toggles.forEach((b) => { b.textContent = paused ? "Play" : "Pause"; });
    cancelAnimationFrame(raf);
    if (paused) still();
    else { start = performance.now() - held * 1000; raf = requestAnimationFrame(frame); }
  }
  // The reduced-motion frame is complete: every step on the ring, the words where the booking was moved.
  const still = () => render(held, reduce && held === STILL ? LOOP : held);
  toggles.forEach((b) => { b.hidden = false; b.addEventListener("click", () => setPaused(!paused)); });
  addEventListener("resize", () => paused && still());
  setPaused(paused);
})();
