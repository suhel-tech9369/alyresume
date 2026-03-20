document.addEventListener("DOMContentLoaded", function () {

  const jdScreen     = document.getElementById("jdScreen");
  const chatScreen   = document.getElementById("chatScreen");
  const analyzeBtn   = document.getElementById("analyzeBtn");
  const jdInput      = document.getElementById("jdInput");
  const langSelect   = document.getElementById("langSelect");

  const jdChatBox    = document.getElementById("jdChatBox");
  const jdUserInput  = document.getElementById("jdUserInput");
  const jdSendBtn    = document.getElementById("jdSendBtn");
  const jdNewBtn     = document.getElementById("jdNewBtn");

  const stepBadge    = document.getElementById("stepBadge");
  const progressFill = document.getElementById("progressFill");

  const jdTemplateBtn   = document.getElementById("jdTemplateBtn");
  const jdTemplatePopup = document.getElementById("jdTemplatePopup");
  const jdCloseTemplate = document.getElementById("jdCloseTemplate");
  const jdTemplateCards = document.querySelectorAll(".jd-template-card");

  let selectedTemplate = null;

  const stepMap = {
    "experience_type" : { label: "Step 1/9", pct: 11  },
    "country"         : { label: "Step 2/9", pct: 22  },
    "total_exp"       : { label: "Step 3/9", pct: 33  },
    "company_name"    : { label: "Step 4/9", pct: 44  },
    "full_name"       : { label: "Step 5/9", pct: 55  },
    "address"         : { label: "Step 6/9", pct: 66  },
    "education"       : { label: "Step 7/9", pct: 77  },
    "languages"       : { label: "Step 8/9", pct: 88  },
    "extra_notes"     : { label: "Step 9/9", pct: 95  },
    "jd_done"         : { label: "✅ Done!" , pct: 100 }
  };

  function updateProgress(stepKey) {
    const info = stepMap[stepKey];
    if (!info) return;
    stepBadge.textContent    = info.label;
    progressFill.style.width = info.pct + "%";
  }

  // ==============================
  // ADD MESSAGE
  // ==============================
  function addMsg(text, sender, chips, exampleText) {

    const msg = document.createElement("div");
    msg.classList.add("jd-msg", sender);

    const formatted = text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");

    msg.innerHTML = formatted;

    if (exampleText) {
      const hint       = document.createElement("div");
      hint.className   = "example-hint";
      hint.textContent = "💡 " + exampleText;
      msg.appendChild(hint);
    }

    if (chips && chips.length) {
      const wrap = document.createElement("div");
      wrap.className = "chips-wrap";
      chips.forEach(c => {
        const chip       = document.createElement("button");
        chip.className   = "chip";
        chip.textContent = c;
        chip.addEventListener("click", function () {
          document.querySelectorAll(".chips-wrap")
            .forEach(w => w.remove());
          jdUserInput.value = c;
          sendMessage();
        });
        wrap.appendChild(chip);
      });
      msg.appendChild(wrap);
    }

    jdChatBox.appendChild(msg);
    jdChatBox.scrollTop = jdChatBox.scrollHeight;
    return msg;
  }

  // ==============================
  // TYPING INDICATOR
  // ==============================
  function showTyping() {
    if (document.getElementById("jdTyping")) return;
    const t = document.createElement("div");
    t.classList.add("jd-msg", "ai");
    t.id = "jdTyping";
    t.innerHTML = `
      <span class="dot-anim">●</span>
      <span class="dot-anim">●</span>
      <span class="dot-anim">●</span>`;
    jdChatBox.appendChild(t);
    jdChatBox.scrollTop = jdChatBox.scrollHeight;
  }

  function removeTyping() {
    const t = document.getElementById("jdTyping");
    if (t) t.remove();
  }

  // ==============================
  // GENERATING ANIMATION
  // ==============================
  function showGenerating() {
    if (document.getElementById("jdTyping")) return;
    const t = document.createElement("div");
    t.classList.add("jd-msg", "ai", "generating-msg");
    t.id = "jdTyping";
    t.innerHTML = `
      <div class="gen-line">⏳ Analyzing JD skills...</div>
      <div class="gen-line">📝 Building your resume...</div>
      <div class="gen-line">🎯 Matching experience to role...</div>
      <div class="gen-line">✨ Optimizing for ATS...</div>`;
    jdChatBox.appendChild(t);
    jdChatBox.scrollTop = jdChatBox.scrollHeight;
    const lines = t.querySelectorAll(".gen-line");
    lines.forEach((line, i) => {
      setTimeout(() => line.classList.add("done"), i * 800);
    });
  }

  // ==============================
  // ANALYZE JD
  // ==============================
  analyzeBtn.addEventListener("click", async function () {

    const jd   = jdInput.value.trim();
    const lang = langSelect.value;

    if (!jd || jd.length < 30) {
      alert("Please paste a proper job description (at least 30 characters).");
      return;
    }

    analyzeBtn.textContent = "Analyzing JD...";
    analyzeBtn.disabled    = true;

    try {
      const res  = await fetch("/api/jd-start", {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({ jd, language: lang })
      });

      const data = await res.json();

      if (data.error) {
        alert("Error: " + data.error);
        analyzeBtn.textContent = "🚀 Analyze JD & Start Resume";
        analyzeBtn.disabled    = false;
        return;
      }

      jdScreen.style.display   = "none";
      chatScreen.style.display = "flex";

      addMsg(
        data.reply,
        "ai",
        data.chips   || [],
        data.example || null
      );

      if (data.step) updateProgress(data.step);

    } catch (e) {
      alert("Network error. Please try again.");
      analyzeBtn.textContent = "🚀 Analyze JD & Start Resume";
      analyzeBtn.disabled    = false;
    }
  });

  // ==============================
  // SEND MESSAGE
  // ==============================
  async function sendMessage() {

    document.querySelectorAll(".chips-wrap").forEach(w => w.remove());

    const message = jdUserInput.value.trim();
    if (!message) return;

    addMsg(message, "user");
    jdUserInput.value = "";
    showTyping();

    try {
      const res  = await fetch("/api/jd-chat", {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({ message })
      });

      const data = await res.json();
      removeTyping();

      if (data.step) updateProgress(data.step);

      if (data.generating) {
        showGenerating();
        setTimeout(() => {
          removeTyping();
          addMsg(data.reply, "ai");
          updateProgress("jd_done");
        }, 3500);
      } else {
        addMsg(
          data.reply,
          "ai",
          data.chips   || [],
          data.example || null
        );
      }

    } catch (e) {
      removeTyping();
      addMsg("❌ Error. Please try again.", "ai");
    }
  }

  jdSendBtn.addEventListener("click", sendMessage);
  jdUserInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") { e.preventDefault(); sendMessage(); }
  });

  // ==============================
  // NEW RESUME
  // ==============================
  jdNewBtn.addEventListener("click", async function () {
    if (!confirm("Start new resume? Current data will be deleted.")) return;
    await fetch("/reset-jd-session", { method: "POST" });
    window.location.reload();
  });

  // ==============================
  // TEMPLATE POPUP
  // ==============================
  jdTemplateBtn.addEventListener("click", () => {
    jdTemplatePopup.style.display = "flex";
  });

  jdCloseTemplate.addEventListener("click", () => {
    jdTemplatePopup.style.display = "none";
  });

  jdTemplateCards.forEach(card => {
    card.addEventListener("click", function () {

      jdTemplateCards.forEach(c => {
        c.classList.remove("selected");
        const ob = c.querySelector(".jd-generate-btn");
        if (ob) ob.remove();
      });

      this.classList.add("selected");
      selectedTemplate = this.getAttribute("data-template");

      const btn       = document.createElement("button");
      btn.textContent = "Generate Template";
      btn.className   = "jd-generate-btn";

      btn.onclick = async function () {
        const res  = await fetch("/check-jd-resume");
        const data = await res.json();
        if (!data.ready) {
          alert("Please complete the resume chat first.");
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
      setTimeout(() => { jdChatBox.scrollTop = jdChatBox.scrollHeight; }, 150);
    });
  } else {
    let initialHeight = window.innerHeight;
    window.addEventListener('resize', () => {
      const newHeight = window.innerHeight;
      if (newHeight < initialHeight * 0.8) {
        setTimeout(() => { jdChatBox.scrollTop = jdChatBox.scrollHeight; }, 100);
      }
      initialHeight = newHeight;
    });
  }

  jdUserInput.addEventListener('focus', () => {
    setTimeout(() => { jdChatBox.scrollTop = jdChatBox.scrollHeight; }, 350);
  });

});