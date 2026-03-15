document.addEventListener("DOMContentLoaded", function () {

    const chatBox = document.getElementById("chatBox");
    const userInput = document.getElementById("user-input");
	const newResumeBtn = document.getElementById("newResumeBtn");

if(newResumeBtn){
    newResumeBtn.addEventListener("click", async function(){

        const confirmReset = confirm("Start a new resume? Current data will be deleted.");

        if(!confirmReset) return;

        await fetch("/reset-session", {
            method: "POST"
        });

        window.location.reload();
    });
}
    const sendBtn = document.getElementById("send-btn");

    // 🎨 Template Elements
    const templateBtn = document.getElementById("templateBtn");
    const templatePopup = document.getElementById("templatePopup");
    const closeTemplate = document.getElementById("closeTemplate");

    // ✅ Template Cards + Buttons
    const templateCards = document.querySelectorAll(".template-card");
    const generateResumeBtn = document.getElementById("generateResumeBtn");

    let selectedTemplate = null;

    // ===============================
    // ADD MESSAGE
    // ===============================
    function addMessage(text, sender) {

        const msg = document.createElement("div");
        msg.classList.add("msg", sender);

        msg.innerText = text;
        chatBox.appendChild(msg);

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // ===============================
    // 🔥 AUTO FIRST QUESTION FIX
    // ===============================
    fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "__start__" })
    })
    .then(res => res.json())
    .then(data => addMessage(data.reply, "ai"));

    // ===============================
    // Typing Indicator
    // ===============================
   function showTyping(mode = "normal") {

    if (document.getElementById("typingIndicator")) return;

    const typing = document.createElement("div");
    typing.classList.add("msg", "ai");
    typing.id = "typingIndicator";

    if (mode === "resume") {
        typing.innerText = "AI is generating your resume... Please wait ⏳";
    } else {
        typing.innerText = "AI is typing...";
    }

    chatBox.appendChild(typing);
    chatBox.scrollTop = chatBox.scrollHeight;
}

    function removeTyping() {
        const typing = document.getElementById("typingIndicator");
        if (typing) typing.remove();
    }

    // ===============================
    // SEND MESSAGE
    // ===============================
    async function sendMessage() {

        let message = userInput.value.trim();
        if (message === "") return;

        addMessage(message, "user");
        userInput.value = "";

        // Detect if final resume generation step
		showTyping();


        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message })
            });

            const data = await response.json();

removeTyping();
if(data.generating){
    showTyping("resume");
    setTimeout(() => {
        removeTyping();
        addMessage(data.reply, "ai");
    }, 1500);
} else {
    addMessage(data.reply, "ai");
}

        } catch (error) {

            removeTyping();
            addMessage("❌ Error: AI response failed.", "ai");
            console.log(error);
        }
    }

    // ===============================
    // EVENTS
    // ===============================

    // ✅ Send Button
    sendBtn.addEventListener("click", sendMessage);

    // ✅ ENTER KEY FIX (FINAL)
    userInput.addEventListener("keypress", function (e) {

        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }

    });

    // ===============================
    // 🎨 TEMPLATE POPUP
    // ===============================

    templateBtn.addEventListener("click", function () {
        templatePopup.style.display = "flex";
    });

    closeTemplate.addEventListener("click", function () {
        templatePopup.style.display = "none";
    });

    // ===============================
    // TEMPLATE SELECT
    // ===============================
    templateCards.forEach(card => {

  card.addEventListener("click", function () {

    // 🔥 Remove old selection
    templateCards.forEach(c => {
      c.classList.remove("selected");

      // Purana button remove
      let oldBtn = c.querySelector(".generate-btn");
      if(oldBtn) oldBtn.remove();
    });

    // 🔥 New selection
    this.classList.add("selected");

    selectedTemplate =
      this.getAttribute("data-template");

    // 🔥 Button create
    let btn = document.createElement("button");

    btn.innerText = "Generate Template";
    btn.className = "generate-btn";

    btn.style.marginTop = "10px";
    btn.style.width = "100%";

    // 🔥 Click event
   btn.onclick = async function(){

  const response = await fetch("/check-resume");
  const data = await response.json();

  if(!data.ready){
    alert("Please generate your resume in chat first.");
    return;
  }

  window.location.href =
    "/template" + selectedTemplate + "-preview";

};

    // 🔥 Add under selected card
    this.appendChild(btn);

  });

});

    // ===============================
    // GENERATE BUTTON CLICK
    // ===============================
    if (generateResumeBtn) {

        generateResumeBtn.addEventListener("click", function () {

            if (!selectedTemplate) {
                alert("Please select a template first!");
                return;
            }

            window.location.href =
                "/template" + selectedTemplate + "-preview";

        });

    }
           // ===============================
    // MOBILE KEYBOARD JUMP FIX (sirf yeh add karo)
    // ===============================
    if ('visualViewport' in window) {
        window.visualViewport.addEventListener('resize', () => {
            setTimeout(() => {
                chatBox.scrollTop = chatBox.scrollHeight;
            }, 150);
        });
    } else {
        let initialHeight = window.innerHeight;
        window.addEventListener('resize', () => {
            const newHeight = window.innerHeight;
            if (newHeight < initialHeight * 0.8) {
                setTimeout(() => {
                    chatBox.scrollTop = chatBox.scrollHeight;
                }, 100);
            }
            initialHeight = newHeight;
        });
    }

    // Input focus pe bhi scroll to bottom
    userInput.addEventListener('focus', () => {
        setTimeout(() => {
            chatBox.scrollTop = chatBox.scrollHeight;
        }, 300);
    });
});