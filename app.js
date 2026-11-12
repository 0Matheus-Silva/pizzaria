(() => {
  const products = window.PRODUCTS;
  const productGrid = document.querySelector("#product-grid");
  const categoryList = document.querySelector("#category-list");
  const searchInput = document.querySelector("#product-search");
  const emptyMessage = document.querySelector("#empty-message");
  const cartPanel = document.querySelector("#cart-panel");
  const cartBackdrop = document.querySelector("#cart-backdrop");
  const cartItemsElement = document.querySelector("#cart-items");
  const cartEmpty = document.querySelector("#cart-empty");
  const cartFooter = document.querySelector("#cart-footer");
  const cartCount = document.querySelector("#cart-count");
  const cartTotal = document.querySelector("#cart-total");
  const toast = document.querySelector("#toast");
  const copyFeedback = document.querySelector("#copy-feedback");
  const storageKey = "bella-pizza-cart";
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  let selectedCategory = "Todos";
  let cart = loadCart();
  let toastTimer;

  function loadCart() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (!Array.isArray(saved)) return [];
      return saved.filter((item) =>
        item && products.some((product) => product.id === item.id)
        && Number.isInteger(item.quantity) && item.quantity > 0
      );
    } catch (error) {
      console.error("Não foi possível carregar a sacola salva.", error);
      return [];
    }
  }

  function saveCart() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(cart));
    } catch (error) {
      console.error("Não foi possível salvar a sacola.", error);
      showToast("Não foi possível salvar sua sacola neste navegador.");
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function renderCategories() {
    const categories = ["Todos", ...new Set(products.map((product) => product.category))];
    categoryList.innerHTML = categories.map((category) => `
      <button class="category-chip${category === selectedCategory ? " active" : ""}"
        type="button" data-category="${escapeHtml(category)}"
        aria-pressed="${category === selectedCategory}">
        ${escapeHtml(category)}
      </button>
    `).join("");
  }

  function filteredProducts() {
    const query = searchInput.value.trim().toLocaleLowerCase("pt-BR");
    return products.filter((product) => {
      const matchesCategory = selectedCategory === "Todos" || product.category === selectedCategory;
      const searchableText = `${product.name} ${product.description} ${product.ingredients}`.toLocaleLowerCase("pt-BR");
      return matchesCategory && searchableText.includes(query);
    });
  }

  function renderProducts() {
    const visibleProducts = filteredProducts();
    productGrid.innerHTML = visibleProducts.map((product) => `
      <article class="product-card">
        <div class="product-image-wrap">
          <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy">
          ${product.featured ? '<span class="product-tag">Queridinha</span>' : ""}
        </div>
        <div class="product-info">
          <span class="product-category">${escapeHtml(product.category)}</span>
          <h3>${escapeHtml(product.name)}</h3>
          <p class="product-description">${escapeHtml(product.description)}</p>
          <small class="product-ingredients">${escapeHtml(product.ingredients)}</small>
          <div class="product-bottom">
            <span class="product-price"><strong>${currency.format(product.price)}</strong><small>${escapeHtml(product.size)}</small></span>
            <button class="add-button" type="button" data-add="${escapeHtml(product.id)}">
              <span aria-hidden="true">+</span> Adicionar
            </button>
          </div>
        </div>
      </article>
    `).join("");
    emptyMessage.hidden = visibleProducts.length > 0;
  }

  function cartQuantity() {
    return cart.reduce((total, item) => total + item.quantity, 0);
  }

  function renderCart() {
    const total = cart.reduce((sum, item) => {
      const product = products.find((entry) => entry.id === item.id);
      return sum + product.price * item.quantity;
    }, 0);

    cartItemsElement.innerHTML = cart.map((item) => {
      const product = products.find((entry) => entry.id === item.id);
      return `
        <article class="cart-item">
          <img src="${escapeHtml(product.image)}" alt="">
          <div>
            <h3 class="cart-item-name">${escapeHtml(product.name)}</h3>
            <p class="cart-item-meta">${escapeHtml(product.size)}</p>
            <div class="quantity-control" aria-label="Quantidade de ${escapeHtml(product.name)}">
              <button type="button" data-quantity="${escapeHtml(product.id)}" data-change="-1" aria-label="Remover uma unidade">−</button>
              <span>${item.quantity}</span>
              <button type="button" data-quantity="${escapeHtml(product.id)}" data-change="1" aria-label="Adicionar uma unidade">+</button>
            </div>
          </div>
          <span class="cart-item-price">${currency.format(product.price * item.quantity)}</span>
        </article>
      `;
    }).join("");

    cartCount.textContent = String(cartQuantity());
    cartTotal.textContent = currency.format(total);
    cartEmpty.hidden = cart.length > 0;
    cartFooter.hidden = cart.length === 0;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 2500);
  }

  function setCartOpen(open) {
    cartPanel.classList.toggle("open", open);
    cartPanel.setAttribute("aria-hidden", String(!open));
    cartPanel.inert = !open;
    document.querySelector("#open-cart").setAttribute("aria-expanded", String(open));
    cartBackdrop.hidden = !open;
    document.body.classList.toggle("cart-open", open);
    if (open) document.querySelector("#close-cart").focus();
    else document.querySelector("#open-cart").focus();
  }

  function addToCart(productId) {
    const item = cart.find((entry) => entry.id === productId);
    if (item) item.quantity += 1;
    else cart.push({ id: productId, quantity: 1 });
    saveCart();
    renderCart();
    showToast("Adicionado à sua sacola!");
  }

  function updateQuantity(productId, amount) {
    const item = cart.find((entry) => entry.id === productId);
    if (!item) return;
    item.quantity += amount;
    cart = cart.filter((entry) => entry.quantity > 0);
    saveCart();
    renderCart();
  }

  function orderSummary() {
    const lines = ["Pedido Bella Pizza", ""];
    for (const item of cart) {
      const product = products.find((entry) => entry.id === item.id);
      lines.push(`${item.quantity}x ${product.name} (${product.size}) — ${currency.format(product.price * item.quantity)}`);
    }
    const total = cart.reduce((sum, item) => {
      const product = products.find((entry) => entry.id === item.id);
      return sum + product.price * item.quantity;
    }, 0);
    lines.push("", `Total dos itens: ${currency.format(total)}`);
    return lines.join("\n");
  }

  categoryList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    selectedCategory = button.dataset.category;
    renderCategories();
    renderProducts();
  });

  searchInput.addEventListener("input", renderProducts);
  productGrid.addEventListener("click", (event) => {
    const button = event.target.closest("[data-add]");
    if (button) addToCart(button.dataset.add);
  });
  cartItemsElement.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quantity]");
    if (button) updateQuantity(button.dataset.quantity, Number(button.dataset.change));
  });

  document.querySelector("#open-cart").addEventListener("click", () => setCartOpen(true));
  document.querySelector("#close-cart").addEventListener("click", () => setCartOpen(false));
  document.querySelector("#keep-shopping").addEventListener("click", () => setCartOpen(false));
  cartBackdrop.addEventListener("click", () => setCartOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cartPanel.classList.contains("open")) setCartOpen(false);
  });

  document.querySelector("#copy-order").addEventListener("click", async () => {
    copyFeedback.textContent = "";
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(orderSummary());
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = orderSummary();
        textArea.setAttribute("readonly", "");
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.append(textArea);
        let copied;
        try {
          textArea.select();
          copied = document.execCommand("copy");
        } finally {
          textArea.remove();
        }
        if (!copied) throw new Error("Clipboard copy command was rejected.");
      }
      copyFeedback.textContent = "Resumo copiado. Agora é só enviar à pizzaria!";
    } catch (error) {
      console.error("Não foi possível copiar o pedido.", error);
      copyFeedback.textContent = "Não foi possível copiar. Tente novamente neste navegador.";
    }
  });

  document.querySelector("#current-year").textContent = String(new Date().getFullYear());
  renderCategories();
  renderProducts();
  renderCart();
})();
