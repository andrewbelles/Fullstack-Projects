/* scheduler.js — full file with “edit lock” support
   ------------------------------------------------------------
   • If grid.dataset.locked === "yes", no handlers are wired up
     and all buttons remain inert.
   • Otherwise behaves exactly like v4 (one-per-row; name display;
     ≥2-or-0 rule; red toggle; pretty errors).
   ------------------------------------------------------------ */

document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById("grid");

  /* ─── EARLY EXIT when schedule is locked ─────────────────────────── */
  if (grid.dataset.locked === "yes") {
    // Buttons are already disabled by the template; nothing else to wire.
    return;
  }

  /* ---------- helpers ------------------------------------------------ */
  const $  = sel => document.querySelector(sel);
  const $$ = sel => Array.from(document.querySelectorAll(sel));
  const post = (url, payload, method = "POST") =>
    fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

  /* ---------- DOM refs & user context -------------------------------- */
  const userName  = grid?.dataset.userName || "";
  const message   = $("#message");
  const submitBtn = $("#submit");
  const unSubBtn  = $("#unsubmit");

  /* ---------- pretty-print API errors -------------------------------- */
  const prettyError = raw => {
    try {
      const obj = JSON.parse(raw);
      if (obj && typeof obj === "object" && "error" in obj) return obj.error;
    } catch (_) { /* non-JSON */ }
    return raw;
  };

  /* ---------- client-side state -------------------------------------- */
  const picks    = new Set();   // blue → to add
  const removals = new Set();   // red  → to delete

  /* wipe any blue selections already in this row (slot) */
  const clearRowSelections = slot => {
    picks.forEach(k => {
      const [s, loc] = k.split(":");
      if (+s === slot) {
        picks.delete(k);
        const cell = $(`.slot[data-slot="${s}"][data-loc="${loc}"]`);
        cell?.classList.remove("select");
      }
    });
  };

  /* check if row already contains one of *my* saved (green) cells */
  const iAlreadyHaveRow = slot =>
    !!$(`.slot.submitted[data-slot="${slot}"]`);

  /* ---------- slot click handler ------------------------------------ */
  function handleClick(e) {
    const cell  = e.currentTarget;
    const slot  = +cell.dataset.slot;
    const loc   = cell.dataset.loc;
    const key   = `${slot}:${loc}`;

    /* green → toggle red */
    if (cell.classList.contains("submitted")) {
      cell.classList.toggle("remove");
      if (cell.classList.contains("remove")) {
        removals.add(key);
      } else {
        removals.delete(key);
      }
      return;
    }

    /* red  → back to green */
    if (cell.classList.contains("remove")) {
      cell.classList.remove("remove");
      cell.classList.add("submitted");
      removals.delete(key);
      return;
    }

    /* blue selection, but enforce one-per-row */
    if (!cell.classList.contains("select")) {
      if (iAlreadyHaveRow(slot)) return;
      clearRowSelections(slot);
      cell.classList.add("select");
      picks.add(key);
    } else {
      cell.classList.remove("select");
      picks.delete(key);
    }
  }

  /* attach handler to every pickable cell once */
  $$(".slot.available").forEach(c => c.addEventListener("click", handleClick));

  /* ---------- SUBMIT ------------------------------------------------- */
  submitBtn.addEventListener("click", () => {
    message.textContent = "";

    if (picks.size && picks.size < 2) {
      message.textContent = "❌ Select at least 2 shifts";
      return;
    }
    if (!picks.size) {
      message.textContent = "❌ No new shifts selected";
      return;
    }

    const shifts = Array.from(picks).map(k => {
      const [slot, loc] = k.split(":");
      return { slot:+slot, location:loc };
    });

    post("/submit", { shifts })
      .then(r => (r.ok ? r.json() : r.text().then(Promise.reject.bind(Promise))))
      .then(() => {
        picks.forEach(k => {
          const [slot, loc] = k.split(":");
          const cell = $(`.slot[data-slot="${slot}"][data-loc="${loc}"]`);
          if (cell) {
            cell.classList.remove("select");
            cell.classList.add("submitted");
            cell.textContent = userName;
          }
        });
        picks.clear();
        message.textContent = "✅ Shifts saved!";
      })
      .catch(err => (message.textContent = "❌ " + prettyError(err)));
  });

  /* ---------- UNSUBMIT / DELETE ------------------------------------- */
  unSubBtn.addEventListener("click", () => {
    message.textContent = "";

    if (!removals.size) {
      message.textContent = "❌ No red squares to delete";
      return;
    }

    const remainingGreens = document.querySelectorAll(".slot.submitted").length;
    if (remainingGreens === 1) {
      message.textContent =
        "❌ You must keep at least 2 shifts or delete all";
      return;
    }

    const shifts = Array.from(removals).map(k => {
      const [slot, loc] = k.split(":");
      return { slot:+slot, location:loc };
    });

    post("/delete", { shifts }, "POST")
      .then(r => (r.ok ? r.json() : r.text().then(Promise.reject.bind(Promise))))
      .then(() => {
        removals.forEach(k => {
          const [slot, loc] = k.split(":");
          const cell = $(`.slot[data-slot="${slot}"][data-loc="${loc}"]`);
          if (cell) {
            cell.classList.remove("remove", "submitted", "select");
            cell.classList.add("available");
            cell.textContent = "";
          }
        });
        removals.clear();
        message.textContent = "🗑️  Deleted selected shifts";
      })
      .catch(err => (message.textContent = "❌ " + prettyError(err)));
  });
});
