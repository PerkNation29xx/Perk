(function () {
  const encode = encodeURIComponent;

  function absoluteUrl(value) {
    try {
      return new URL(value || window.location.href, window.location.origin).href;
    } catch (_) {
      return window.location.href;
    }
  }

  function shareData(panel) {
    const title = panel.dataset.shareTitle || document.title || "Perk Nation";
    const text = panel.dataset.shareText || "Check this out on Perk Nation.";
    const url = absoluteUrl(panel.dataset.shareUrl || window.location.href);
    return { title, text, url };
  }

  function status(panel, message) {
    const target = panel.querySelector("[data-share-status]");
    if (target) target.textContent = message;
  }

  async function copyLink(panel, url, message) {
    try {
      await navigator.clipboard.writeText(url);
      status(panel, message || "Link copied.");
    } catch (_) {
      window.prompt("Copy this link", url);
      status(panel, "Copy the link from the prompt.");
    }
  }

  async function nativeShare(panel, data, label) {
    if (navigator.share) {
      try {
        await navigator.share(data);
        status(panel, "Share sheet opened.");
        return;
      } catch (error) {
        if (error && error.name === "AbortError") return;
      }
    }
    await copyLink(panel, data.url, `Link copied. Paste it in ${label}.`);
  }

  function openUrl(url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  document.addEventListener("click", async function (event) {
    const button = event.target.closest("[data-share-action]");
    if (!button) return;
    const panel = button.closest("[data-share-panel]");
    if (!panel) return;

    const data = shareData(panel);
    const body = `${data.text} ${data.url}`;
    const action = button.dataset.shareAction;

    if (action === "facebook") {
      openUrl(`https://www.facebook.com/sharer/sharer.php?u=${encode(data.url)}`);
      status(panel, "Facebook share window opened.");
      return;
    }

    if (action === "email") {
      window.location.href = `mailto:?subject=${encode(data.title)}&body=${encode(body)}`;
      status(panel, "Email composer opened.");
      return;
    }

    if (action === "sms" || action === "imessage") {
      window.location.href = `sms:?&body=${encode(body)}`;
      status(panel, action === "imessage" ? "Messages opened." : "SMS opened.");
      return;
    }

    if (action === "instagram") {
      await nativeShare(panel, data, "Instagram");
      return;
    }

    if (action === "tiktok") {
      await nativeShare(panel, data, "TikTok");
      return;
    }

    await copyLink(panel, data.url);
  });
})();
