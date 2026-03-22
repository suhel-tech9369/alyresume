document.addEventListener("DOMContentLoaded", function () {

  const chatBox       = document.getElementById("chatBox");
  const userInput     = document.getElementById("user-input");
  const sendBtn       = document.getElementById("send-btn");
  const newResumeBtn  = document.getElementById("newResumeBtn");
  const templateBtn   = document.getElementById("templateBtn");
  const templatePopup = document.getElementById("templatePopup");
  const closeTemplate = document.getElementById("closeTemplate");
  const templateCards = document.querySelectorAll(".template-card");
  const stepBadge     = document.getElementById("stepBadge");
  const progressFill  = document.getElementById("progressFill");

  let selectedTemplate = null;

  // ==============================
  // STEP → PROGRESS MAP
  // ==============================
  const stepProgress = {
    "language"         : { label: "Step 1/10", pct: 10  },
    "country"          : { label: "Step 2/10", pct: 20  },
    "job_role"         : { label: "Step 3/10", pct: 30  },
    "experience_type"  : { label: "Step 4/10", pct: 40  },
    "total_exp"        : { label: "Step 5/10", pct: 50  },
    "company_name"     : { label: "Step 5/10", pct: 50  },
    "company_duration" : { label: "Step 5/10", pct: 52  },
    "add_more_company" : { label: "Step 5/10", pct: 54  },
    "full_name"        : { label: "Step 6/10", pct: 60  },
    "address"          : { label: "Step 7/10", pct: 70  },
    "email"            : { label: "Step 7/10", pct: 72  },
    "phone"            : { label: "Step 7/10", pct: 74  },
    "education"        : { label: "Step 8/10", pct: 80  },
    "college"          : { label: "Step 8/10", pct: 82  },
    "completion_year"  : { label: "Step 8/10", pct: 84  },
    "languages"        : { label: "Step 9/10", pct: 90  },
    "skills"           : { label: "Step 9/10", pct: 92  },
    "extra_custom"     : { label: "Step 10/10", pct: 95 },
    "extra_notes"      : { label: "Step 10/10", pct: 97 },
    "done"             : { label: "✅ Done!",   pct: 100 }
  };

  function updateProgress(stepKey) {
    const info = stepProgress[stepKey];
    if (!info) return;
    stepBadge.textContent    = info.label;
    progressFill.style.width = info.pct + "%";
  }

  // ==============================
  // ADD MESSAGE + CHIPS + HINT
  // ==============================
  function addMsg(text, sender, chips, exampleText) {

    const msg = document.createElement("div");
    msg.classList.add("msg", sender);

    const formatted = text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");

    msg.innerHTML = formatted;

    // Example hint — inside bubble
    if (exampleText) {
      const hint       = document.createElement("div");
      hint.className   = "example-hint";
      hint.textContent = "💡 " + exampleText;
      msg.appendChild(hint);
    }

    // Chips — INSIDE bubble (same as JD)
    if (chips && chips.length) {
      const wrap     = document.createElement("div");
      wrap.className = "chips-wrap";
      chips.forEach(c => {
        const chip       = document.createElement("button");
        chip.className   = "chip";
        chip.textContent = c;
        chip.addEventListener("click", function () {
          document.querySelectorAll(".chips-wrap").forEach(w => w.remove());
          userInput.value = c;
          sendMessage();
        });
        wrap.appendChild(chip);
      });
      msg.appendChild(wrap);  // ← ANDAR — SAHI
    }

    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // ==============================
  // TYPING — 3 dots
  // ==============================
  function showTyping() {
    if (document.getElementById("typingIndicator")) return;
    const t = document.createElement("div");
    t.classList.add("msg", "ai");
    t.id = "typingIndicator";
    t.innerHTML = `
      <span class="dot-anim">●</span>
      <span class="dot-anim">●</span>
      <span class="dot-anim">●</span>`;
    chatBox.appendChild(t);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function removeTyping() {
    const t = document.getElementById("typingIndicator");
    if (t) t.remove();
  }

  // ==============================
  // GENERATING ANIMATION
  // ==============================
  function showGenerating() {
    if (document.getElementById("typingIndicator")) return;
    const t = document.createElement("div");
    t.classList.add("msg", "ai", "generating-msg");
    t.id = "typingIndicator";
    t.innerHTML = `
      <div class="gen-line">⏳ Collecting your details...</div>
      <div class="gen-line">📝 Building your resume...</div>
      <div class="gen-line">🎯 Formatting sections...</div>
      <div class="gen-line">✨ Optimizing for ATS...</div>`;
    chatBox.appendChild(t);
    chatBox.scrollTop = chatBox.scrollHeight;
    t.querySelectorAll(".gen-line").forEach((line, i) => {
      setTimeout(() => line.classList.add("done"), i * 800);
    });
  }

  // ==============================
  // FIRST MESSAGE ON LOAD
  // ==============================
  fetch("/api/chat", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ message: "__start__" })
  })
  .then(res => res.json())
  .then(data => {
    addMsg(data.reply, "ai", data.chips || [], data.example || null);
    if (data.step) updateProgress(data.step);
  });

  // ==============================
  // SEND MESSAGE
  // ==============================
  async function sendMessage() {

    const message = userInput.value.trim();
    if (!message) return;

    addMsg(message, "user", [], null);
    userInput.value = "";
    showTyping();

    try {
      const response = await fetch("/api/chat", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ message })
      });

      const data = await response.json();
      removeTyping();

      if (data.step) updateProgress(data.step);

      if (data.generating) {
        showGenerating();
        setTimeout(() => {
          removeTyping();
          addMsg(data.reply, "ai", [], null);
          updateProgress("done");
        }, 3500);
      } else {
        addMsg(
          data.reply,
          "ai",
          data.chips   || [],
          data.example || null
        );
      }

    } catch (error) {
      removeTyping();
      addMsg("❌ Error: AI response failed. Please try again.", "ai", [], null);
      console.error(error);
    }
  }

  // ==============================
  // EVENTS
  // ==============================
  sendBtn.addEventListener("click", sendMessage);

  userInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") { e.preventDefault(); sendMessage(); }
  });

  if (newResumeBtn) {
    newResumeBtn.addEventListener("click", async function () {
      if (!confirm("Start a new resume? Current data will be deleted.")) return;
      await fetch("/reset-session", { method: "POST" });
      window.location.reload();
    });
  }

  // ==============================
  // TEMPLATE POPUP
  // ==============================
  templateBtn.addEventListener("click", () => {
    templatePopup.style.display = "flex";
  });

  closeTemplate.addEventListener("click", () => {
    templatePopup.style.display = "none";
  });

  templateCards.forEach(card => {
    card.addEventListener("click", function () {

      templateCards.forEach(c => {
        c.classList.remove("selected");
        const ob = c.querySelector(".generate-btn");
        if (ob) ob.remove();
      });

      this.classList.add("selected");
      selectedTemplate = this.getAttribute("data-template");

      const btn       = document.createElement("button");
      btn.textContent = "Generate Template";
      btn.className   = "generate-btn";

      btn.onclick = async function () {
        await new Promise(r => setTimeout(r, 700));
        const res  = await fetch("/check-resume");
        const data = await res.json();
        if (!data.ready) {
          alert("Please generate your resume in chat first.");
          return;
        }
        window.location.href = "/template" + selectedTemplate + "-preview";
      };

      this.appendChild(btn);
    });
  });

  // ==============================
  // MOBILE KEYBOARD FIX
  // ==============================
  if ('visualViewport' in window) {
    window.visualViewport.addEventListener('resize', () => {
      setTimeout(() => { chatBox.scrollTop = chatBox.scrollHeight; }, 150);
    });
  } else {
    let initialHeight = window.innerHeight;
    window.addEventListener('resize', () => {
      const newHeight = window.innerHeight;
      if (newHeight < initialHeight * 0.8) {
        setTimeout(() => { chatBox.scrollTop = chatBox.scrollHeight; }, 100);
      }
      initialHeight = newHeight;
    });
  }

  userInput.addEventListener('focus', () => {
    setTimeout(() => { chatBox.scrollTop = chatBox.scrollHeight; }, 300);
  });

});