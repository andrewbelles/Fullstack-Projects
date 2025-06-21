document.addEventListener("DOMContentLoaded", () => {
  // Prevent any slot from ever receiving focus (so no mobile keyboard pops)
  document.querySelectorAll(".slot").forEach(el => {
    // make sure it's not focusable
    el.tabIndex = -1;

    // intercept pointer/touch/focus before click
    ["pointerdown", "touchstart", "focus"].forEach(evt =>
      el.addEventListener(evt, e => {
        e.preventDefault();
        el.blur();
      })
    );
  });

  // Now the normal toggle & submit logic
  const userId = Number(document.body.dataset.userId);
  let selection = [];

  // toggle logic
  document.querySelectorAll(".slot").forEach(cell => {
    if (cell.classList.contains("inactive")) return;

    cell.addEventListener("click", () => {
      const slot = +cell.dataset.slot;
      const loc  = cell.dataset.loc;
      const idx  = selection.findIndex(s => s.slot === slot);

      // clear other locs for that slot
      document
        .querySelectorAll(`.slot[data-slot="${slot}"]`)
        .forEach(c => c.classList.remove("active"));

      if (idx >= 0) {
        if (selection[idx].location === loc) {
          selection.splice(idx, 1);
        } else {
          selection[idx].location = loc;
          cell.classList.add("active");
        }
      } else {
        selection.push({ slot, location: loc });
        cell.classList.add("active");
      }
    });
  });

  const msg = document.getElementById("message");

  // submit logic
  document.getElementById("submit").addEventListener("click", () => {
    msg.textContent = "";

    fetch("/submit", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ user_id: userId, shifts: selection })
    })
    .then(res => {
      if (res.ok) {
        msg.textContent = "✅ Shifts submitted!";
        setTimeout(() => window.location.reload(), 800);
      } else {
        return res.json().then(j => { throw j.error });
      }
    })
    .catch(err => {
      msg.textContent = "❌ Error: " + err;
    });
  });
});
