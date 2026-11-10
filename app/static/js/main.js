document.addEventListener("DOMContentLoaded", () => {
  const payment = document.querySelector("#payment_method");
  const change = document.querySelector("#change-field");
  const orderType = document.querySelector("#order_type");
  const address = document.querySelector("#address_id");

  const updateCheckoutFields = () => {
    if (change && payment) {
      change.hidden = payment.value !== "cash";
    }
    if (address && orderType) {
      const delivery = orderType.value === "delivery";
      address.closest("#address-container")?.toggleAttribute("hidden", !delivery);
      address.toggleAttribute("hidden", !delivery);
    }
  };

  payment?.addEventListener("change", updateCheckoutFields);
  orderType?.addEventListener("change", updateCheckoutFields);
  updateCheckoutFields();
});
