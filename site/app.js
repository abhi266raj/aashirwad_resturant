const MENU_FILE = 'menu.json';
const CART_KEY = 'aashirwad_resturant_cart_v1';
const CUSTOMER_KEY = 'aashirwad_resturant_customer_v1';
const ORDER_PHONE = '917004230188';
const state = { items: [], category: 'All', diet: 'all', query: '', cart: {} };
const $ = (selector) => document.querySelector(selector);
const money = (amount) => `₹${amount}`;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const menuItem = (id) => state.items.find((item) => item.id === id);
const imageFor = (item) => item.image || item.fallback_image || 'assets/placeholder.svg';

function readStorage(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage can be unavailable. */ }
}
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 3000);
}
function restoreCart() {
  const saved = readStorage(CART_KEY, {});
  state.cart = {};
  if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
    for (const [id, quantity] of Object.entries(saved)) {
      if (menuItem(id) && Number.isInteger(quantity) && quantity > 0 && quantity <= 99) state.cart[id] = quantity;
    }
  }
  writeStorage(CART_KEY, state.cart);
}
function restoreCustomer() {
  const saved = readStorage(CUSTOMER_KEY, {});
  for (const [field, selector] of Object.entries({name:'#customer-name',phone:'#customer-phone',address:'#customer-address',notes:'#customer-notes'})) {
    if (typeof saved?.[field] === 'string') $(selector).value = saved[field];
  }
}
function filteredItems() {
  const query = state.query.toLocaleLowerCase();
  return state.items.filter((item) => (state.category === 'All' || item.category === state.category) && (state.diet === 'all' || item.diet === state.diet) && (!query || `${item.name} ${item.description} ${item.category}`.toLocaleLowerCase().includes(query)));
}
function renderCategories() {
  const categories = ['All', ...new Set(state.items.map((item) => item.category))];
  if (!categories.includes(state.category)) state.category = 'All';
  $('#categories').innerHTML = categories.map((category) => `<button class="category ${category === state.category ? 'active' : ''}" type="button" data-category="${escapeHtml(category)}" aria-pressed="${category === state.category}">${escapeHtml(category === 'All' ? 'All dishes' : category)}</button>`).join('');
}
function dishCard(item) {
  const quantity = state.cart[item.id] || 0;
  return `<article class="dish-card">
    <div class="dish-image"><img src="${escapeHtml(imageFor(item))}" data-fallback="${escapeHtml(item.fallback_image)}" alt="${escapeHtml(item.name)}" loading="lazy"><div class="dish-badges"><span class="dish-badge ${item.diet}">${item.diet === 'veg' ? '● VEG' : '● NON-VEG'}</span>${item.popular ? '<span class="dish-badge popular">POPULAR</span>' : ''}</div></div>
    <div class="dish-content"><span class="dish-category">${escapeHtml(item.category)}</span><div class="dish-title-row"><h3 class="dish-title">${escapeHtml(item.name)}</h3><span class="dish-price">${money(item.price)}</span></div><p class="dish-description">${escapeHtml(item.description)}</p><div class="dish-action">${quantity ? `<div class="stepper"><button type="button" data-action="decrease" data-id="${escapeHtml(item.id)}" aria-label="Remove one ${escapeHtml(item.name)}">−</button><span>${quantity} in order</span><button type="button" data-action="increase" data-id="${escapeHtml(item.id)}" aria-label="Add one ${escapeHtml(item.name)}">+</button></div>` : `<button class="add-button" type="button" data-action="increase" data-id="${escapeHtml(item.id)}">Add to order +</button>`}</div></div></article>`;
}
function renderMenu() {
  const items = filteredItems();
  $('#menu-count').textContent = `${items.length} ${items.length === 1 ? 'dish' : 'dishes'}`;
  $('#menu-grid').innerHTML = items.length ? items.map(dishCard).join('') : '<div class="empty-state"><strong>No dishes found</strong>Try another search or filter.</div>';
  $$('.diet').forEach((button) => {
    const active = button.dataset.diet === state.diet;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}
function $$(selector) { return document.querySelectorAll(selector); }
function cartItems() { return Object.entries(state.cart).map(([id, quantity]) => ({ item: menuItem(id), quantity })).filter(({item,quantity}) => item && quantity > 0); }
function totals() {
  const items = cartItems();
  return { items, count: items.reduce((sum, row) => sum + row.quantity, 0), total: items.reduce((sum, row) => sum + row.item.price * row.quantity, 0) };
}
function renderCart() {
  const {items,count,total} = totals();
  $('#header-count').textContent = count;
  $('#mobile-cart').hidden = count === 0;
  $('#mobile-cart-total').textContent = money(total);
  $('#cart-empty').hidden = count !== 0;
  $('#checkout-fields').hidden = count === 0;
  $('#cart-total').textContent = money(total);
  $('#cart-items').innerHTML = items.map(({item,quantity}) => `<div class="cart-line"><img src="${escapeHtml(imageFor(item))}" data-fallback="${escapeHtml(item.fallback_image)}" alt=""><div><strong>${escapeHtml(item.name)}</strong><small>${money(item.price)} each</small><div class="cart-line-controls"><button type="button" data-action="decrease" data-id="${escapeHtml(item.id)}" aria-label="Remove one ${escapeHtml(item.name)}">−</button><span>${quantity}</span><button type="button" data-action="increase" data-id="${escapeHtml(item.id)}" aria-label="Add one ${escapeHtml(item.name)}">+</button></div></div><span class="cart-line-price">${money(item.price * quantity)}</span></div>`).join('');
}
function changeQuantity(id, delta) {
  if (!menuItem(id)) return;
  const next = Math.min(99, Math.max(0, (state.cart[id] || 0) + delta));
  if (next) state.cart[id] = next; else delete state.cart[id];
  writeStorage(CART_KEY, state.cart);
  renderMenu();
  renderCart();
  if (delta > 0) showToast('Added to your order');
}
function openCart() {
  $('#drawer-backdrop').hidden = false;
  $('#cart-drawer').hidden = false;
  document.body.style.overflow = 'hidden';
  $('#close-cart').focus();
}
function closeCart() {
  $('#drawer-backdrop').hidden = true;
  $('#cart-drawer').hidden = true;
  document.body.style.overflow = '';
  $('#header-cart').focus();
}
function orderMessage(customer) {
  const {items,total} = totals();
  const lines = ['AASHIRWAD RESTAURANT — NEW DELIVERY ORDER', '', `Name: ${customer.name}`, `Phone: ${customer.phone}`, `Address: ${customer.address}`];
  if (customer.notes) lines.push(`Notes: ${customer.notes}`);
  lines.push('', 'Items:');
  items.forEach(({item,quantity}, index) => lines.push(`${index + 1}. ${item.name} × ${quantity} @ ${money(item.price)} = ${money(item.price * quantity)}`));
  lines.push('', `Expected total: ${money(total)}`, 'Free home delivery. Please confirm availability and timing.');
  return lines.join('\n');
}
function submitOrder(event) {
  event.preventDefault();
  if (!$('#checkout-form').reportValidity()) return;
  if (!totals().count) return;
  const customer = {
    name: $('#customer-name').value.trim(), phone: $('#customer-phone').value.trim(),
    address: $('#customer-address').value.trim(), notes: $('#customer-notes').value.trim()
  };
  if (!customer.name || !customer.phone || !customer.address) return;
  writeStorage(CUSTOMER_KEY, customer);
  const message = orderMessage(customer);
  const channel = event.submitter?.dataset.channel || 'whatsapp';
  if (channel === 'sms') {
    const separator = /iPhone|iPad|iPod/.test(navigator.userAgent) ? '&' : '?';
    window.location.href = `sms:${ORDER_PHONE}${separator}body=${encodeURIComponent(message)}`;
  } else {
    window.open(`https://wa.me/${ORDER_PHONE}?text=${encodeURIComponent(message)}`, '_blank', 'noopener,noreferrer');
  }
}
function handleImageError(event) {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  const fallback = img.dataset.fallback || 'assets/placeholder.svg';
  if (!img.src.endsWith(fallback)) { img.src = fallback; return; }
  if (!img.src.endsWith('assets/placeholder.svg')) img.src = 'assets/placeholder.svg';
}
async function loadMenu() {
  try {
    const response = await fetch(MENU_FILE, {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.version !== 1 || !Array.isArray(data.items) || !data.items.length) throw new Error('Invalid menu');
    state.items = data.items;
    restoreCart();
    restoreCustomer();
    renderCategories();
    renderMenu();
    renderCart();
  } catch (error) {
    console.error('Unable to load menu', error);
    $('#menu-count').textContent = 'Menu unavailable';
    $('#menu-grid').innerHTML = '<div class="empty-state"><strong>Menu is temporarily unavailable</strong>Please refresh the page or call us at <a href="tel:+917004230188">+91 70042 30188</a>.</div>';
    showToast('Could not load the menu. Please try again.');
  }
}
function bindEvents() {
  $('#year').textContent = new Date().getFullYear();
  $('#search').addEventListener('input', (event) => { state.query = event.target.value.trim(); renderMenu(); });
  $('.diet-tabs').addEventListener('click', (event) => { const button = event.target.closest('[data-diet]'); if (!button) return; state.diet = button.dataset.diet; renderMenu(); });
  $('#categories').addEventListener('click', (event) => { const button = event.target.closest('[data-category]'); if (!button) return; state.category = button.dataset.category; renderCategories(); renderMenu(); });
  document.addEventListener('click', (event) => { const button = event.target.closest('[data-action][data-id]'); if (button) changeQuantity(button.dataset.id, button.dataset.action === 'increase' ? 1 : -1); });
  document.addEventListener('error', handleImageError, true);
  for (const selector of ['#header-cart','#mobile-cart','#visit-cart']) $(selector).addEventListener('click', openCart);
  $('#close-cart').addEventListener('click', closeCart);
  $('#drawer-backdrop').addEventListener('click', closeCart);
  $('#empty-menu-link').addEventListener('click', closeCart);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$('#cart-drawer').hidden) closeCart(); });
  $('#checkout-form').addEventListener('submit', submitOrder);
}
bindEvents();
loadMenu();
