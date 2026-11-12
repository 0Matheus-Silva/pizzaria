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
  const checkoutView = document.querySelector("#checkout-view");
  const checkoutForm = document.querySelector("#checkout-form");
  const checkoutError = document.querySelector("#checkout-error");
  const orderView = document.querySelector("#order-view");
  const openOrderButton = document.querySelector("#open-order");
  const storageKey = "bella-pizza-cart";
  const ordersStorageKey = "bella-pizza-orders";
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const paymentMethods = {
    cash: "Dinheiro na entrega",
    debit_card: "Cartão de débito na entrega",
    credit_card: "Cartão de crédito na entrega"
  };

  let selectedCategory = "Todos";
  let cart = loadCart();
  let orders = loadOrders();
  let toastTimer;
  let cartReturnTarget = null;

  function loadOrders() {
    try {
      const saved = JSON.parse(localStorage.getItem(ordersStorageKey) || "[]");
      if (!Array.isArray(saved)) return [];
      return saved.filter((order) =>
        order && typeof order.id === "string" && Array.isArray(order.items)
        && typeof order.customerName === "string" && typeof order.address === "string"
      );
    } catch (error) {
      console.error("Não foi possível carregar os pedidos salvos.", error);
      return [];
    }
  }

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

  function renderOrder(order) {
    document.querySelector("#order-number").textContent =
      `Pedido ${order.id} · ${new Date(order.createdAt).toLocaleString("pt-BR")}`;
    document.querySelector("#order-status").textContent = order.status;
    document.querySelector("#order-details").innerHTML = `
      <p class="order-customer">${escapeHtml(order.customerName)}</p>
      <p class="order-address">${escapeHtml(order.address)}</p>
      <p class="order-payment">Pagamento: ${escapeHtml(order.payment)}</p>
      ${order.items.map((item) => `
        <div class="order-line">
          <span>${item.quantity}x ${escapeHtml(item.name)}</span>
          <strong>${currency.format(item.price * item.quantity)}</strong>
        </div>
      `).join("")}
      <div class="order-line order-grand-total"><span>Total dos itens</span><strong>${currency.format(order.total)}</strong></div>
    `;
    openOrderButton.hidden = false;
  }

  function showCartContents() {
    cartItemsElement.hidden = false;
    cartEmpty.hidden = cart.length > 0;
    cartFooter.hidden = cart.length === 0;
    checkoutView.hidden = true;
    orderView.hidden = true;
  }

  function showCheckout() {
    cartItemsElement.hidden = true;
    cartEmpty.hidden = true;
    cartFooter.hidden = true;
    checkoutView.hidden = false;
    orderView.hidden = true;
    checkoutError.hidden = true;
    document.querySelector("#customer-first-name").focus();
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 2500);
  }

  function setCartOpen(open, trigger) {
    if (open && trigger) cartReturnTarget = trigger;
    cartPanel.classList.toggle("open", open);
    cartPanel.setAttribute("aria-hidden", String(!open));
    cartPanel.inert = !open;
    document.querySelector("#open-cart").setAttribute("aria-expanded", String(open));
    cartBackdrop.hidden = !open;
    document.body.classList.toggle("cart-open", open);
    if (open) document.querySelector("#close-cart").focus();
    else {
      (cartReturnTarget || document.querySelector("#open-cart")).focus();
      cartReturnTarget = null;
    }
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

  function createOrder(formData) {
    const items = cart.map((item) => {
      const product = products.find((entry) => entry.id === item.id);
      return {
        id: product.id,
        name: product.name,
        size: product.size,
        price: product.price,
        quantity: item.quantity
      };
    });
    const firstName = String(formData.get("firstName")).trim();
    const lastName = String(formData.get("lastName")).trim();
    const order = {
      id: `BP-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      createdAt: new Date().toISOString(),
      customerName: `${firstName} ${lastName}`,
      address: String(formData.get("address")).trim(),
      payment: paymentMethods[String(formData.get("paymentMethod"))],
      status: "Recebido pela loja · aguardando aceitação",
      estimatedDelivery: "30 a 40 minutos",
      items,
      total: items.reduce((sum, item) => sum + item.price * item.quantity, 0)
    };

    try {
      orders = [order, ...orders].slice(0, 20);
      localStorage.setItem(ordersStorageKey, JSON.stringify(orders));
    } catch (error) {
      console.error("Não foi possível registrar o pedido de teste.", error);
      orders = loadOrders();
      checkoutError.textContent = "Não foi possível salvar o pedido neste navegador. Libere espaço e tente novamente.";
      checkoutError.hidden = false;
      return;
    }

    cart = [];
    saveCart();
    renderCart();
    renderOrder(order);
    cartItemsElement.hidden = true;
    cartEmpty.hidden = true;
    cartFooter.hidden = true;
    checkoutView.hidden = true;
    orderView.hidden = false;
    setCartOpen(true, document.querySelector("#open-cart"));
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

  document.querySelector("#open-cart").addEventListener("click", (event) => {
    showCartContents();
    setCartOpen(true, event.currentTarget);
  });
  openOrderButton.addEventListener("click", (event) => {
    const latestOrder = orders[0];
    if (!latestOrder) {
      openOrderButton.hidden = true;
      return;
    }
    renderOrder(latestOrder);
    cartItemsElement.hidden = true;
    cartEmpty.hidden = true;
    cartFooter.hidden = true;
    checkoutView.hidden = true;
    orderView.hidden = false;
    setCartOpen(true, event.currentTarget);
  });
  document.querySelector("#close-cart").addEventListener("click", () => setCartOpen(false));
  document.querySelector("#keep-shopping").addEventListener("click", (event) => setCartOpen(false, event.currentTarget));
  cartBackdrop.addEventListener("click", () => setCartOpen(false));
  document.querySelector("#continue-checkout").addEventListener("click", showCheckout);
  document.querySelector("#back-to-cart").addEventListener("click", showCartContents);
  document.querySelector("#finish-order").addEventListener("click", () => {
    showCartContents();
    setCartOpen(false);
  });
  checkoutForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!checkoutForm.reportValidity()) return;
    if (cart.length === 0) {
      checkoutError.textContent = "Sua sacola está vazia. Adicione pelo menos um produto antes de continuar.";
      checkoutError.hidden = false;
      return;
    }
    const formData = new FormData(checkoutForm);
    const firstName = String(formData.get("firstName")).trim();
    const lastName = String(formData.get("lastName")).trim();
    const address = String(formData.get("address")).trim();
    const paymentMethod = String(formData.get("paymentMethod"));
    if (!firstName || !lastName || address.length < 10) {
      checkoutError.textContent = "Informe nome, sobrenome e um endereço válido para continuar.";
      checkoutError.hidden = false;
      if (!firstName) document.querySelector("#customer-first-name").focus();
      else if (!lastName) document.querySelector("#customer-last-name").focus();
      else document.querySelector("#delivery-address").focus();
      return;
    }
    if (!Object.hasOwn(paymentMethods, paymentMethod)) {
      checkoutError.textContent = "Selecione uma forma de pagamento para continuar.";
      checkoutError.hidden = false;
      document.querySelector("#payment-method").focus();
      return;
    }
    createOrder(formData);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cartPanel.classList.contains("open")) setCartOpen(false);
  });

  document.querySelector("#current-year").textContent = String(new Date().getFullYear());
  renderCategories();
  renderProducts();
  renderCart();
  if (orders.length > 0) renderOrder(orders[0]);
})();
