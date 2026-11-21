/*
 * sale.js - the keyboard-driven Record Sale screen (Part 1, Figure 4.6.4).
 *
 * The cart lives in the browser while the cashier works. Every line is
 * checked twice:
 *   1. here, instantly, as the quantity is typed (red warning, F4 disabled)
 *   2. on the server when F4 is pressed (/sales/validate-line)
 * and the whole sale is checked a THIRD time inside the database
 * transaction when F9 is pressed (/sales/complete). The browser checks are
 * only for speed - the server checks are the ones that count (FR-15).
 */

let cart = [];          // [{product_id, product_name, quantity, unit_price, line_total}]
let results = [];       // current search results
let highlighted = -1;   // which search result the arrow keys are on
let selected = null;    // the product chosen for the next line
let searchTimer = null;

const $ = (id) => document.getElementById(id);
const money = (n) => "R " + Number(n).toFixed(2);

// ------------------------------------------------------------------ helpers
async function postJSON(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const body = await response.json();
  if (response.status === 401 && body.login) {      // idle timeout (NFR-04)
    window.location = URLS.login;
  }
  return body;
}

function showMessage(text, kind) {
  $("message").innerHTML = text ? `<div class="flash ${kind}">${text}</div>` : "";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function qtyAlreadyInCart(productId) {
  return cart.filter((l) => l.product_id === productId).reduce((sum, l) => sum + l.quantity, 0);
}

function paymentType() {
  return document.querySelector("input[name=payment]:checked").value;
}

// ------------------------------------------------------------ product search
$("product-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  const text = $("product-search").value.trim();
  if (!text) { $("search-results").hidden = true; return; }
  // wait 200ms after the last key press, so we don't search on every letter
  searchTimer = setTimeout(async () => {
    const response = await fetch(URLS.search + "?q=" + encodeURIComponent(text));
    if (response.status === 401) { window.location = URLS.login; return; }
    results = await response.json();
    highlighted = results.length ? 0 : -1;
    drawResults();
  }, 200);
});

function drawResults() {
  const box = $("search-results");
  if (!results.length) {
    box.innerHTML = '<div class="muted">No matching products</div>';
  } else {
    box.innerHTML = results.map((p, i) =>
      `<div data-i="${i}" class="${i === highlighted ? "selected" : ""}">
         ${escapeHtml(p.product_name)} - ${money(p.unit_price)} - In stock: ${p.qty_in_stock}
       </div>`).join("");
  }
  box.hidden = false;
}

$("search-results").addEventListener("click", (e) => {
  const row = e.target.closest("[data-i]");
  if (row) chooseProduct(results[Number(row.dataset.i)]);
});

$("product-search").addEventListener("keydown", (e) => {
  if ($("search-results").hidden || !results.length) return;
  if (e.key === "ArrowDown") { highlighted = Math.min(highlighted + 1, results.length - 1); drawResults(); e.preventDefault(); }
  if (e.key === "ArrowUp")   { highlighted = Math.max(highlighted - 1, 0); drawResults(); e.preventDefault(); }
  if (e.key === "Enter" && highlighted >= 0) { chooseProduct(results[highlighted]); e.preventDefault(); }
});

function chooseProduct(product) {
  selected = product;
  $("search-results").hidden = true;
  $("product-search").value = product.product_name;
  $("chosen").hidden = false;
  $("chosen").innerHTML = `<strong>${escapeHtml(product.product_name)}</strong> - ${money(product.unit_price)}
                           - In stock: ${product.qty_in_stock}`;
  $("quantity").value = 1;
  checkQuantity();
  $("quantity").focus();
  $("quantity").select();
}

// --------------------------------------------- live quantity check (FR-15)
function checkQuantity() {
  const warning = $("qty-warning");
  const qty = Number($("quantity").value);
  let problem = "";
  if (!selected) problem = "";
  else if (!Number.isInteger(qty) || qty <= 0) problem = "Quantity must be a whole number greater than zero";
  else if (qty + qtyAlreadyInCart(selected.product_id) > selected.qty_in_stock) {
    problem = `⚠ Only ${selected.qty_in_stock} in stock`
            + (qtyAlreadyInCart(selected.product_id) ? ` (${qtyAlreadyInCart(selected.product_id)} already in this sale)` : "")
            + " - reduce quantity";
  }
  warning.textContent = problem;
  warning.hidden = !problem;
  $("quantity").classList.toggle("invalid", !!problem);
  $("add-line").disabled = !selected || !!problem;     // the disabled [F4] from the mock-up
}
$("quantity").addEventListener("input", checkQuantity);
$("quantity").addEventListener("keydown", (e) => { if (e.key === "Enter") { addLine(); e.preventDefault(); } });

// ------------------------------------------------------------- [F4] add line
async function addLine() {
  if ($("add-line").disabled) return;
  const quantity = Number($("quantity").value);
  const body = await postJSON(URLS.validate, {
    product_id: selected.product_id,
    quantity: quantity,
    cart_lines: cart.map((l) => ({ product_id: l.product_id, quantity: l.quantity })),
  });
  if (!body.ok) { showMessage(body.message, "error"); return; }

  const existing = cart.find((l) => l.product_id === body.line.product_id);
  if (existing) {            // same product twice -> one line with a bigger quantity
    existing.quantity += body.line.quantity;
    existing.line_total = +(existing.quantity * existing.unit_price).toFixed(2);
  } else {
    cart.push(body.line);
  }
  showMessage("", "");
  resetProductPicker();
  drawCart();
}
$("add-line").addEventListener("click", addLine);

function resetProductPicker() {
  selected = null;
  $("product-search").value = "";
  $("chosen").hidden = true;
  $("quantity").value = 1;
  $("qty-warning").hidden = true;
  $("quantity").classList.remove("invalid");
  $("add-line").disabled = true;
  $("product-search").focus();
}

// --------------------------------------------------------------- the cart
function cartTotal() {
  return +cart.reduce((sum, l) => sum + l.line_total, 0).toFixed(2);
}

function drawCart() {
  const tbody = $("cart").querySelector("tbody");
  if (!cart.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No items yet.</td></tr>';
  } else {
    tbody.innerHTML = cart.map((l, i) => `
      <tr><td>${l.quantity} x</td><td>${escapeHtml(l.product_name)}</td>
          <td class="num">${money(l.unit_price)}</td><td class="num">${money(l.line_total)}</td>
          <td><button class="btn small secondary" data-remove="${i}" title="Remove line">✕</button></td></tr>`).join("");
  }
  $("total").textContent = money(cartTotal());
  updateChange();
}

$("cart").addEventListener("click", (e) => {
  const button = e.target.closest("[data-remove]");
  if (button) { cart.splice(Number(button.dataset.remove), 1); drawCart(); }
});

// ---------------------------------------------------------------- payment
function updateChange() {
  const cash = paymentType() === "CASH";
  $("cash-fields").hidden = !cash;
  const tendered = Number($("tendered").value || 0);
  const change = tendered - cartTotal();
  $("change").textContent = cash && tendered ? money(Math.max(change, 0)) : "R 0.00";
  $("change").classList.toggle("warning-text", cash && tendered > 0 && change < 0);
  $("complete").disabled = !cart.length || (cash && tendered < cartTotal());
}
$("tendered").addEventListener("input", updateChange);
document.querySelectorAll("input[name=payment]").forEach((r) => r.addEventListener("change", updateChange));

function togglePayment() {
  const other = paymentType() === "CASH" ? "CARD" : "CASH";
  document.querySelector(`input[name=payment][value=${other}]`).checked = true;
  updateChange();
}

// ------------------------------------------------------- [F9] complete sale
async function completeSale() {
  if ($("complete").disabled) return;
  $("complete").disabled = true;                       // stop a double click saving twice
  const body = await postJSON(URLS.complete, {
    cart_lines: cart.map((l) => ({ product_id: l.product_id, quantity: l.quantity })),
    payment_type: paymentType(),
    amount_tendered: paymentType() === "CASH" ? $("tendered").value : null,
  });
  if (!body.ok) {                                      // e.g. stock changed on another till
    showMessage(body.message, "error");
    updateChange();
    return;
  }
  showMessage(`Sale saved. Receipt <strong>${body.receipt_no}</strong> - total ${money(body.total)}
               - change due: <strong>${money(body.change_due)}</strong>.
               <a href="${URLS.receipt}${body.sale_id}">View / print receipt</a>`, "success");
  cart = [];
  $("tendered").value = "";
  drawCart();
  resetProductPicker();
}
$("complete").addEventListener("click", completeSale);

function cancelSale() {
  if (cart.length && !confirm("Cancel this sale and clear all lines?")) return;
  cart = [];
  $("tendered").value = "";
  showMessage("", "");
  drawCart();
  resetProductPicker();
}
$("cancel").addEventListener("click", cancelSale);

// ------------------------------------------------------ keyboard shortcuts
document.addEventListener("keydown", (e) => {
  const actions = {
    F2: () => { $("product-search").focus(); $("product-search").select(); },
    F3: () => { $("quantity").focus(); $("quantity").select(); },
    F4: addLine,
    F6: togglePayment,
    F7: () => { if (paymentType() === "CASH") { $("tendered").focus(); $("tendered").select(); } },
    F9: completeSale,
    Escape: () => { if (!$("search-results").hidden) $("search-results").hidden = true; else cancelSale(); },
  };
  if (actions[e.key]) {
    e.preventDefault();          // stop the browser's own use of the key (e.g. F3 = Find)
    actions[e.key]();
  }
});

drawCart();
