(function () {
  const products = {
    "swarovski-annual-snowflake": {
      category: "Swarovski Annual Snowflake",
      title: "Swarovski Annual Snowflake 10-year period",
      description: "Collector crystal snowflake set with individual annual pieces and display boxes.",
      retail: "Retail $2,499",
      discount: "25% off",
      price: "$1,875",
      image: "swarovski-annual-snowflake.jpg",
      video: "swarovski-annual-snowflake.mp4",
      purchasable: true,
      bullets: [
        "Ten-year Swarovski Annual Snowflake crystal collection.",
        "Includes the product boxes shown in the photos and video.",
        "Limited Perk Nation pricing while the item is available."
      ],
      note: "Secure checkout is handled by Stripe. Shipping address and phone are collected during checkout."
    },
    "swarovski-sorcerer-mickey": {
      category: "Swarovski collectible",
      title: "Swarovski Sorcerer Mickey",
      description: "Clear crystal Sorcerer Mickey figure with black and gold accent detail.",
      retail: "Retail $225",
      discount: "20% off",
      price: "$180",
      image: "swarovski-sorcerer-mickey.jpg",
      video: "swarovski-sorcerer-mickey.mp4",
      portrait: true,
      purchasable: true,
      bullets: [
        "Swarovski Sorcerer Mickey crystal figure.",
        "Product video is included so buyers can inspect the item before checkout.",
        "Limited Perk Nation pricing while the item is available."
      ],
      note: "Secure checkout is handled by Stripe. Shipping address and phone are collected during checkout."
    },
    "christian-dior-necklace": {
      category: "Designer necklace",
      title: "Christian Dior Necklace",
      description: "Designer necklace with a crystal V pendant and silver-tone chain.",
      retail: "Retail $525",
      discount: "20% off",
      price: "$420",
      image: "christian-dior-necklace.jpg",
      purchasable: true,
      bullets: [
        "Christian Dior necklace with crystal V pendant.",
        "Product image is published on the Perk Nation product page.",
        "Limited Perk Nation pricing while the item is available."
      ],
      note: "Secure checkout is handled by Stripe. Shipping address and phone are collected during checkout."
    },
    "swarovski-swan-pin-set": {
      category: "Swarovski crystal pins",
      title: "Swarovski Swan Crystal Pin Set",
      description: "Three-piece swan pin set with blue, red, and yellow crystal accents.",
      retail: "Retail price pending",
      discount: "DM to confirm",
      price: "Price by request",
      image: "swarovski-swan-pin-set.jpg",
      purchasable: false,
      bullets: [
        "Three-piece swan pin set with blue, red, and yellow stones.",
        "Pricing is not published yet, so checkout is disabled for this item.",
        "Message Perk Nation to confirm availability and pricing."
      ],
      note: "Online checkout will be enabled after the retail and discounted price are confirmed."
    }
  };

  const $ = (selector) => document.querySelector(selector);

  const assetUrl = (filename) => {
    const base = document.body.dataset.assetsBase || "/assets";
    return `${base.replace(/\/$/, "")}/products/${filename}`;
  };

  const currentSlug = () => {
    const parts = window.location.pathname.split("/").filter(Boolean);
    return parts[parts.length - 1] || "";
  };

  const setText = (selector, value) => {
    const node = $(selector);
    if (node) node.textContent = value || "";
  };

  const showAlert = (message) => {
    const alert = $("[data-jewelry-alert]");
    if (!alert || !message) return;
    alert.textContent = message;
    alert.hidden = false;
  };

  const renderMedia = (product) => {
    const host = $("[data-jewelry-media]");
    if (!host) return;
    host.classList.toggle("isPortrait", Boolean(product.portrait));
    host.innerHTML = "";

    if (product.video) {
      const video = document.createElement("video");
      video.controls = true;
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.poster = assetUrl(product.image);
      video.setAttribute("aria-label", `${product.title} product video`);

      const source = document.createElement("source");
      source.src = assetUrl(product.video);
      source.type = "video/mp4";
      video.appendChild(source);
      host.appendChild(video);
      return;
    }

    const image = document.createElement("img");
    image.src = assetUrl(product.image);
    image.alt = product.title;
    host.appendChild(image);
  };

  const renderBullets = (product) => {
    const list = $("[data-jewelry-bullets]");
    if (!list) return;
    list.innerHTML = "";
    product.bullets.forEach((bullet) => {
      const item = document.createElement("li");
      item.textContent = bullet;
      list.appendChild(item);
    });
  };

  const renderProduct = (product, slug) => {
    document.title = `${product.title} - Perk Nation`;
    setText("[data-jewelry-category]", product.category);
    setText("[data-jewelry-title]", product.title);
    setText("[data-jewelry-description]", product.description);
    setText("[data-jewelry-retail]", product.retail);
    setText("[data-jewelry-discount]", product.discount);
    setText("[data-jewelry-price]", product.price);
    setText("[data-jewelry-note]", product.note);
    renderMedia(product);
    renderBullets(product);

    const retail = $("[data-jewelry-retail]");
    if (retail) retail.classList.toggle("noStrike", !product.purchasable);

    const checkout = $("[data-jewelry-checkout]");
    if (checkout) {
      checkout.dataset.productSlug = slug;
      checkout.hidden = !product.purchasable;
      checkout.textContent = `Buy now - ${product.price}`;
    }

    const contact = $("[data-jewelry-contact]");
    if (contact && !product.purchasable) {
      contact.textContent = "Request availability";
    }
  };

  const setupCheckout = () => {
    const checkout = $("[data-jewelry-checkout]");
    if (!checkout) return;
    checkout.addEventListener("click", async () => {
      const productSlug = checkout.dataset.productSlug;
      if (!productSlug) return;
      const originalText = checkout.textContent;
      checkout.disabled = true;
      checkout.textContent = "Starting checkout...";
      try {
        const response = await fetch("/v1/web/payments/jewelry/checkout-session", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            product_slug: productSlug,
            quantity: 1,
            source_page: window.location.pathname
          })
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.detail || "Could not start checkout.");
        }
        if (!payload.checkout_url) {
          throw new Error("Checkout URL was not returned.");
        }
        window.location.assign(payload.checkout_url);
      } catch (error) {
        showAlert(error.message || "Could not start checkout.");
        checkout.disabled = false;
        checkout.textContent = originalText;
      }
    });
  };

  const setupStatusMessage = () => {
    const params = new URLSearchParams(window.location.search);
    const payment = String(params.get("payment") || "").toLowerCase();
    if (payment === "success") {
      showAlert("Payment completed. Stripe will send the checkout receipt, and Perk Nation will follow up on fulfillment.");
    } else if (payment === "cancelled") {
      showAlert("Checkout was cancelled. You can restart checkout whenever you are ready.");
    }
  };

  const init = () => {
    const slug = currentSlug();
    const product = products[slug];
    const back = $("[data-jewelry-back]");
    if (back && document.body.dataset.jewelryHome) {
      back.href = document.body.dataset.jewelryHome;
    }

    if (!product) {
      setText("[data-jewelry-title]", "Product not found");
      setText("[data-jewelry-description]", "This jewelry product link is not available.");
      const checkout = $("[data-jewelry-checkout]");
      if (checkout) checkout.hidden = true;
      return;
    }

    renderProduct(product, slug);
    setupCheckout();
    setupStatusMessage();
  };

  init();
})();
