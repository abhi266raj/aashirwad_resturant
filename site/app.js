/**
 * aashirwad - Home Delivery Web Application
 * Features:
 * - Permanent non-expiring cookie delivery storage
 * - No popup on launch; address modal only on checkout (or via top header) with skip option
 * - Clean list of authentic restaurant numbers (no fabricated roles)
 * - Header navigation (Home, About Us, Location, Call Numbers) & comprehensive footer
 * - Official restaurant order tickets via WhatsApp & SMS to 7004230188
 */

let MENU_ITEMS = [];
let MENU_CATEGORIES = [];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
async function loadMenuData() {
  const data = window.MENU_SNAPSHOT;
  if (!data || !Array.isArray(data.items)) throw new Error('Menu unavailable');
  MENU_ITEMS = data.items.map(item => ({...item, isVeg:item.diet === 'veg', bestseller:item.popular}));
  MENU_CATEGORIES = [{id:'all', name:'All Dishes', icon:'🍽️'}, ...Array.from(new Set(MENU_ITEMS.map(item => item.category))).map(category => ({id:category, name:category, icon:''}))];
}
// Application State
const state = {
  activeCategory: 'all',
  dietFilter: 'all', // 'all', 'veg', 'nonveg'
  searchQuery: '',
  cart: {}, // { [itemId]: quantity }
  delivery: {
    address: '',
    name: '',
    phone: '',
    notes: ''
  },
  isDrawerOpen: false,
  pendingCheckoutType: 'whatsapp' // 'whatsapp' or 'sms'
};

// Permanent Cookie Helpers (Expires in year 2099)
function setCookie(name, value) {
  const expires = "expires=Fri, 31 Dec 2099 23:59:59 GMT";
  document.cookie = `${name}=${encodeURIComponent(value)};${expires};path=/;SameSite=Lax`;
  try {
    localStorage.setItem(name, value);
  } catch (e) {}
}

function getCookie(name) {
  const cname = `${name}=`;
  const decoded = decodeURIComponent(document.cookie);
  const ca = decoded.split(';');
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i].trim();
    if (c.indexOf(cname) === 0) {
      return c.substring(cname.length, c.length);
    }
  }
  try {
    return localStorage.getItem(name) || '';
  } catch (e) {
    return '';
  }
}

function getRestaurantConfig() {
  if (window.RESTAURANT_CONFIG) return window.RESTAURANT_CONFIG;
  return {
    name: window.RESTAURANT_LOCATION?.name || "aashirwad",
    tagline: "Authentic North Indian, Tandoori & Chinese family restaurant. Fresh food and free home delivery.",
    whatsappNumber: "7004230188",
    whatsappDisplay: "+91 70042 30188",
    phones: window.RESTAURANT_PHONES || [
      { number: "7004230188", display: "+91 70042 30188", isWhatsApp: true },
      { number: "9334047955", display: "+91 93340 47955", isWhatsApp: false },
      { number: "6207228264", display: "+91 62072 28264", isWhatsApp: false },
      { number: "9931579212", display: "+91 99315 79212", isWhatsApp: false }
    ],
    location: window.RESTAURANT_LOCATION || {
      city: "Hazaribagh",
      address: "Near Bansilal Chowk / Kani Bazar Chowk, Munka Bagicha, Hazaribagh, Jharkhand - 825301",
      landmark: "Near Bansilal Chowk",
      timings: "10:30 AM – 10:30 PM (All 7 Days)",
      coordinates: "23.9928812, 85.3616478",
      googleMapsUrl: "https://maps.google.com"
    }
  };
}

function initRestaurantInfo() {
  const cfg = getRestaurantConfig();
  const name = cfg.name || 'Restaurant';
  const city = cfg.location?.city || '';
  const address = cfg.location?.address || '';
  const timings = cfg.location?.timings || '';
  const landmark = cfg.location?.landmark || '';
  const mapsUrl = cfg.location?.googleMapsUrl || '';
  const waDisplay = cfg.whatsappDisplay || cfg.whatsappNumber;

  // 1. Title & Meta
  document.title = `${name} - Home Delivery & Restaurant Menu`;
  const metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc) {
    metaDesc.content = `Order food online from ${name}${city ? ` in ${city}` : ''}. Searchable menu, free home delivery, WhatsApp & SMS ordering to ${waDisplay}.`;
  }

  // 2. Brand name across all brand classes / IDs
  document.querySelectorAll('.brand-restaurant-name').forEach(el => {
    el.textContent = name;
  });

  // 3. Headings & Taglines
  const aboutHeading = document.getElementById('about-restaurant-heading');
  if (aboutHeading) aboutHeading.textContent = `Welcome to ${name}`;

  const aboutTagline = document.getElementById('about-restaurant-tagline');
  if (aboutTagline && cfg.tagline) {
    aboutTagline.innerHTML = `${city ? `Located around ${landmark || city}, ` : ''}<strong class="brand-restaurant-name">${escapeHTML(name)}</strong> offers wholesome, authentic food and fresh preparations. All orders placed on our website enjoy complimentary home delivery${city ? ` across ${escapeHTML(city)}` : ''}.`;
  }

  const deliveryBadge = document.getElementById('hero-delivery-badge');
  if (deliveryBadge) {
    deliveryBadge.textContent = `Free Home Delivery${city ? ` in ${city}` : ''}`;
  }

  // 4. Location & Timings
  const aboutAddress = document.getElementById('about-restaurant-address');
  if (aboutAddress && address) aboutAddress.textContent = address;

  const aboutTimings = document.getElementById('about-restaurant-timings');
  if (aboutTimings && timings) aboutTimings.textContent = timings;

  const aboutCoords = document.getElementById('about-restaurant-coordinates');
  if (aboutCoords && cfg.location?.coordinates) aboutCoords.textContent = cfg.location.coordinates;

  const aboutMaps = document.getElementById('about-maps-link');
  if (aboutMaps && mapsUrl) aboutMaps.href = mapsUrl;

  // 5. Address Modal & Drawer Address
  const modalAddrLabel = document.getElementById('modal-address-label');
  if (modalAddrLabel) {
    modalAddrLabel.textContent = `Delivery Address & Landmark${city ? ` in ${city}` : ''}`;
  }
  const modalAddrInput = document.getElementById('modal-address');
  if (modalAddrInput) {
    modalAddrInput.placeholder = `e.g. Near ${landmark || 'Main Road'}${city ? `, ${city}` : ''}`;
  }
  const drawerAddr = document.getElementById('drawer-delivery-addr');
  if (drawerAddr && (!state.delivery.address || state.delivery.address === 'Hazaribagh')) {
    drawerAddr.textContent = city || 'Home Delivery';
  }

  // 6. Call Modal Heading
  const callHeading = document.getElementById('call-modal-heading');
  if (callHeading) callHeading.textContent = `Call ${name}`;

  // 7. Order Action Buttons text
  const waBtnText = document.getElementById('order-whatsapp-btn-text');
  if (waBtnText) waBtnText.textContent = `Order via WhatsApp (${waDisplay})`;

  const smsBtnText = document.getElementById('order-sms-btn-text');
  if (smsBtnText) smsBtnText.textContent = `Send Order via SMS (${waDisplay})`;

  // 8. Footer Elements
  const footerName = document.getElementById('footer-restaurant-name');
  if (footerName) footerName.textContent = name;

  const footerTagline = document.getElementById('footer-restaurant-tagline');
  if (footerTagline && cfg.tagline) footerTagline.textContent = cfg.tagline;

  const footerAddress = document.getElementById('footer-restaurant-address');
  if (footerAddress && address) footerAddress.textContent = address;

  const footerTimings = document.getElementById('footer-restaurant-timings');
  if (footerTimings && timings) footerTimings.textContent = timings;

  const footerCopyright = document.getElementById('footer-copyright');
  if (footerCopyright) footerCopyright.textContent = `© ${new Date().getFullYear()} ${name}. All rights reserved.`;

  // 9. Contact numbers in Contact Section, Call Modal, and Footer
  renderPhoneLists(cfg);
}

function renderPhoneLists(cfg) {
  const phones = cfg.phones || [];
  if (!phones.length) return;

  const contactGrid = document.getElementById('contact-phones-grid');
  if (contactGrid) {
    contactGrid.innerHTML = phones.map(p => `
      <div class="p-3.5 rounded-xl border border-stone-200 bg-stone-50 flex items-center justify-between">
        <span class="font-extrabold text-sm text-stone-900">${escapeHTML(p.display || p.number)}</span>
        <div class="flex items-center gap-1">
          <a href="tel:${p.number}" class="p-1.5 rounded-lg bg-stone-900 text-white text-xs font-bold">Call</a>
          ${p.isWhatsApp ? `<a href="https://wa.me/91${p.number.replace(/\D/g,'').slice(-10)}" target="_blank" rel="noopener noreferrer" class="p-1.5 rounded-lg bg-emerald-600 text-white text-xs font-bold">WhatsApp</a>` : ''}
        </div>
      </div>
    `).join('');
  }

  const modalList = document.getElementById('call-modal-phones-list');
  if (modalList) {
    modalList.innerHTML = phones.map(p => `
      <div class="p-3 rounded-xl border border-stone-200 bg-stone-50 flex items-center justify-between gap-2">
        <span class="font-extrabold text-sm text-stone-900">${escapeHTML(p.display || p.number)}</span>
        <div class="flex items-center gap-1.5">
          <a href="tel:${p.number}" class="px-2.5 py-1.5 rounded-lg bg-stone-900 hover:bg-stone-800 text-white text-xs font-bold transition">Call</a>
          ${p.isWhatsApp ? `<a href="https://wa.me/91${p.number.replace(/\D/g,'').slice(-10)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition">WhatsApp</a>` : ''}
        </div>
      </div>
    `).join('');
  }

  const footerList = document.getElementById('footer-phones-list');
  if (footerList) {
    footerList.innerHTML = phones.map(p => `
      <li><a href="tel:${p.number}" class="hover:text-white">${escapeHTML(p.display || p.number)}</a></li>
    `).join('');
  }
}

// Initialize on Load (NO POPUP AT LAUNCH)
document.addEventListener('DOMContentLoaded', async () => {
  initRestaurantInfo();
  setupEventListeners();
  try { await loadMenuData(); } catch (error) {
    document.getElementById('menu-count-label').textContent = 'Menu unavailable';
    document.getElementById('menu-grid').innerHTML = '<p class="col-span-full p-6 text-center">Please refresh or call us to order.</p>';
    return;
  }
  loadSavedData();
  for (const id of Object.keys(state.cart)) {
    if (!MENU_ITEMS.some(item => item.id === id) || !Number.isInteger(state.cart[id]) || state.cart[id] < 1) delete state.cart[id];
  }
  saveCartToStorage();
  renderCategories();
  renderMenu();
  updateCartUI();
  updateLocationHeader();
});

// Load Cookies & LocalStorage
function loadSavedData() {
  state.delivery.address = getCookie('aashirwad_resturant_addr') || '';
  state.delivery.name = getCookie('aashirwad_resturant_name') || '';
  state.delivery.phone = getCookie('aashirwad_resturant_phone') || '';
  try { state.delivery.notes = localStorage.getItem('aashirwad_resturant_notes') || ''; } catch { state.delivery.notes = ''; }

  try {
    const savedCart = localStorage.getItem('aashirwad_resturant_cart');
    if (savedCart) state.cart = JSON.parse(savedCart);
  } catch (e) {
    state.cart = {};
  }
}

function saveDeliveryData(address, name, phone, notes = '') {
  state.delivery.address = address.trim();
  state.delivery.name = name.trim();
  state.delivery.phone = phone.trim();
  state.delivery.notes = notes.trim();

  setCookie('aashirwad_resturant_addr', state.delivery.address);
  setCookie('aashirwad_resturant_name', state.delivery.name);
  setCookie('aashirwad_resturant_phone', state.delivery.phone);

  try {
    localStorage.setItem('aashirwad_resturant_notes', state.delivery.notes);
  } catch (e) {}

  updateLocationHeader();
}

function saveCartToStorage() {
  try {
    localStorage.setItem('aashirwad_resturant_cart', JSON.stringify(state.cart));
  } catch (e) {
    console.error('Failed to save cart', e);
  }
}

// Update Top Bar Location Display
function updateLocationHeader() {
  const label = document.getElementById('header-location-label');
  if (!label) return;

  if (state.delivery.address) {
    label.innerHTML = `
      <span class="truncate max-w-[140px] sm:max-w-[260px] inline-block font-semibold text-stone-800">${escapeHTML(state.delivery.address)}</span>
      <span class="text-orange-600 font-bold ml-1 text-[11px] underline">Change</span>
    `;
  } else {
    label.innerHTML = `
      <span class="text-orange-700 font-bold">Set Delivery Location ▾</span>
    `;
  }
}

// Address / Checkout Modal Controls
function openAddressModal(isCheckout = false, checkoutType = null) {
  // If not checkout, pendingCheckoutType is null so it ONLY saves address
  state.pendingCheckoutType = isCheckout ? checkoutType : null;

  const modal = document.getElementById('address-modal');
  const addrInput = document.getElementById('modal-address');
  const nameInput = document.getElementById('modal-name');
  const phoneInput = document.getElementById('modal-phone');
  const submitBtn = document.getElementById('address-submit-btn');
  const skipBtn = document.getElementById('skip-address-btn');
  const title = document.getElementById('address-modal-title');

  if (modal) {
    if (addrInput) addrInput.value = state.delivery.address;
    if (nameInput) nameInput.value = state.delivery.name;
    if (phoneInput) phoneInput.value = state.delivery.phone;

    if (isCheckout) {
      // ORDER FLOW ONLY: User prompted during checkout
      if (title) title.textContent = "Delivery Address for Order";
      if (submitBtn) submitBtn.textContent = checkoutType === 'whatsapp' ? "Save & Proceed to WhatsApp" : "Save & Proceed to SMS";
      if (skipBtn) {
        skipBtn.textContent = checkoutType === 'whatsapp' ? "Skip Address & Continue to WhatsApp" : "Skip Address & Continue to SMS";
        skipBtn.classList.remove('hidden');
        skipBtn.style.display = 'block';
      }
    } else {
      // OUTSIDE ORDER FLOW (Top section / Header / General address edit)
      // Skip address button should ONLY be when it is from order flow
      if (title) title.textContent = "Your Delivery Address";
      if (submitBtn) submitBtn.textContent = "Save Address";
      if (skipBtn) {
        skipBtn.classList.add('hidden');
        skipBtn.style.display = 'none';
      }
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

function closeAddressModal() {
  const modal = document.getElementById('address-modal');
  const skipBtn = document.getElementById('skip-address-btn');
  if (modal) {
    modal.classList.add('hidden');
    document.body.style.overflow = '';
  }
  if (skipBtn) {
    skipBtn.classList.add('hidden');
    skipBtn.style.display = 'none';
  }
}

// Call Options Modal Controls
function openCallModal() {
  const modal = document.getElementById('call-modal');
  if (modal) {
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

function closeCallModal() {
  const modal = document.getElementById('call-modal');
  if (modal) {
    modal.classList.add('hidden');
    document.body.style.overflow = '';
  }
}

// Render Category Navigation
function renderCategories() {
  const container = document.getElementById('category-tabs');
  if (!container) return;

  container.innerHTML = MENU_CATEGORIES.map(cat => `
    <button
      class="category-tab px-3.5 py-1.5 rounded-full font-semibold text-xs border flex-shrink-0 transition-all cursor-pointer ${state.activeCategory === cat.id ? 'bg-orange-600 text-white border-orange-600 shadow-sm' : 'bg-white text-stone-700 border-stone-200 hover:border-orange-300 hover:bg-orange-50'}"
      data-category="${escapeHTML(cat.id)}">
      <span>${cat.icon}</span>
      <span class="ml-1">${escapeHTML(cat.name)}</span>
    </button>
  `).join('');

  container.querySelectorAll('.category-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.activeCategory = btn.dataset.category;
      renderCategories();
      renderMenu();
    });
  });
}

// Filter Menu Items
function getFilteredItems() {
  return MENU_ITEMS.filter(item => {
    const categoryMatch = (state.activeCategory === 'all') || (item.category === state.activeCategory);

    let dietMatch = true;
    if (state.dietFilter === 'veg') dietMatch = item.isVeg;
    if (state.dietFilter === 'nonveg') dietMatch = !item.isVeg;

    let searchMatch = true;
    if (state.searchQuery.trim() !== '') {
      const q = state.searchQuery.toLowerCase().trim();
      searchMatch = item.name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q);
    }

    return categoryMatch && dietMatch && searchMatch;
  });
}

// Render Menu Cards
function renderMenu() {
  const grid = document.getElementById('menu-grid');
  const countLabel = document.getElementById('menu-count-label');
  if (!grid) return;

  const items = getFilteredItems();

  if (countLabel) {
    countLabel.textContent = `${items.length} ${items.length === 1 ? 'dish' : 'dishes'}`;
  }

  if (items.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full py-12 text-center bg-white rounded-2xl border border-stone-200 p-8">
        <div class="text-3xl mb-2">🔍</div>
        <h3 class="text-sm font-bold text-stone-800">No matching dishes</h3>
        <p class="text-xs text-stone-500 mt-1">Try another search term or view all dishes.</p>
        <button id="reset-search-btn" class="mt-3 px-4 py-1.5 bg-orange-600 text-white rounded-lg text-xs font-bold hover:bg-orange-700 transition cursor-pointer">
          Show All Dishes
        </button>
      </div>
    `;
    document.getElementById('reset-search-btn')?.addEventListener('click', () => {
      state.activeCategory = 'all';
      state.dietFilter = 'all';
      state.searchQuery = '';
      const searchInput = document.getElementById('search-input');
      if (searchInput) searchInput.value = '';
      renderCategories();
      updateDietFilterUI();
      renderMenu();
    });
    return;
  }

  grid.innerHTML = items.map(item => {
    const qty = state.cart[item.id] || 0;
    const lineTotal = item.price * qty;
    return `
      <div class="menu-card bg-white rounded-2xl border border-stone-200 overflow-hidden flex flex-col justify-between shadow-sm hover:shadow-md transition">
        <div>
          <!-- Dish Image -->
          <div class="relative w-full aspect-[4/3] bg-stone-100 overflow-hidden">
            <img
              src="${escapeHTML(item.image)}"
              alt="${escapeHTML(item.name)}"
              loading="lazy"
              class="w-full h-full object-cover"
              onerror="this.onerror=null;this.src='assets/placeholder.svg';"
            />
            <div class="absolute top-2.5 left-2.5 flex items-center gap-1">
              <span class="food-badge ${item.isVeg ? 'veg' : 'non-veg'}"></span>
              <span class="text-[10px] font-bold px-1.5 py-0.5 rounded ${item.isVeg ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'} backdrop-blur-sm">
                ${item.isVeg ? 'VEG' : 'NON-VEG'}
              </span>
            </div>
            ${item.bestseller ? `
              <span class="absolute top-2.5 right-2.5 text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-amber-500 text-white shadow-sm">
                ★ Popular
              </span>
            ` : ''}
          </div>

          <!-- Dish Info -->
          <div class="p-3.5">
            <div class="flex items-start justify-between gap-1.5">
              <h3 class="font-bold text-stone-900 text-sm leading-snug">${escapeHTML(item.name)}</h3>
              <span class="text-sm sm:text-base font-extrabold text-stone-900 flex-shrink-0">₹${item.price}</span>
            </div>
            <p class="text-stone-500 text-xs mt-1 line-clamp-2">${escapeHTML(item.description)}</p>
          </div>
        </div>

        <!-- Add & Stepper Control -->
        <div class="p-3.5 pt-0">
          ${qty === 0 ? `
            <button
              class="w-full py-2 px-3 rounded-xl bg-orange-50 hover:bg-orange-600 text-orange-700 hover:text-white font-bold text-xs border border-orange-200 hover:border-transparent transition flex items-center justify-center gap-1 add-to-order-btn cursor-pointer"
              data-item-id="${escapeHTML(item.id)}">
              <span>Add</span>
              <span>· ₹${item.price}</span>
            </button>
          ` : `
            <div>
              <div class="flex items-center justify-between bg-orange-600 text-white rounded-xl p-1 shadow-sm">
                <button
                  class="qty-btn bg-white/20 hover:bg-white/30 text-white decrease-qty-btn cursor-pointer"
                  data-item-id="${escapeHTML(item.id)}"
                  aria-label="Decrease quantity">
                  -
                </button>
                <span class="font-bold text-xs px-2 select-none">${qty} in cart</span>
                <button
                  class="qty-btn bg-white/20 hover:bg-white/30 text-white increase-qty-btn cursor-pointer"
                  data-item-id="${escapeHTML(item.id)}"
                  aria-label="Increase quantity">
                  +
                </button>
              </div>
              <div class="flex items-center justify-between mt-1 px-1 text-[11px] text-stone-500 font-medium">
                <span>Subtotal:</span>
                <span class="text-orange-700 font-bold">₹${lineTotal}</span>
              </div>
            </div>
          `}
        </div>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('.add-to-order-btn').forEach(btn => {
    btn.addEventListener('click', () => addToCart(btn.dataset.itemId));
  });
  grid.querySelectorAll('.increase-qty-btn').forEach(btn => {
    btn.addEventListener('click', () => addToCart(btn.dataset.itemId));
  });
  grid.querySelectorAll('.decrease-qty-btn').forEach(btn => {
    btn.addEventListener('click', () => removeFromCart(btn.dataset.itemId));
  });
}

// Cart State Modifications
function addToCart(itemId) {
  state.cart[itemId] = (state.cart[itemId] || 0) + 1;
  saveCartToStorage();
  updateCartUI();
  renderMenu();
  const item = MENU_ITEMS.find(i => i.id === itemId);
  if (item) {
    showToast(`Added ${item.name} (${state.cart[itemId]}x = ₹${item.price * state.cart[itemId]})`);
  }
}

function removeFromCart(itemId) {
  if (!state.cart[itemId]) return;
  state.cart[itemId] -= 1;
  if (state.cart[itemId] <= 0) delete state.cart[itemId];
  saveCartToStorage();
  updateCartUI();
  renderMenu();
}

function deleteEntireItem(itemId) {
  delete state.cart[itemId];
  saveCartToStorage();
  updateCartUI();
  renderMenu();
}

function clearCart() {
  if (Object.keys(state.cart).length === 0) return;
  if (confirm("Clear your current order selection?")) {
    state.cart = {};
    saveCartToStorage();
    updateCartUI();
    renderMenu();
    showToast("Cart cleared");
  }
}

// Calculate Totals
function getCartTotals() {
  let count = 0;
  let totalAmount = 0;
  const items = [];

  for (const [id, qty] of Object.entries(state.cart)) {
    const item = MENU_ITEMS.find(i => i.id === id);
    if (item && qty > 0) {
      count += qty;
      const lineTotal = item.price * qty;
      totalAmount += lineTotal;
      items.push({
        ...item,
        quantity: qty,
        unitPrice: item.price,
        lineTotal: lineTotal
      });
    }
  }

  return { count, totalAmount, items };
}

// Update UI
function updateCartUI() {
  const { count, totalAmount, items } = getCartTotals();

  const navBadge = document.getElementById('nav-cart-count');
  const navAmount = document.getElementById('nav-cart-total');
  if (navBadge) navBadge.textContent = count;
  if (navAmount) navAmount.textContent = `₹${totalAmount}`;

  const floatBtn = document.getElementById('floating-cart-btn');
  const floatCount = document.getElementById('floating-cart-count');
  const floatAmount = document.getElementById('floating-cart-amount');
  if (floatBtn) {
    if (count > 0) {
      floatBtn.classList.remove('hidden');
    } else {
      floatBtn.classList.add('hidden');
    }
  }
  if (floatCount) floatCount.textContent = count;
  if (floatAmount) floatAmount.textContent = `₹${totalAmount}`;

  renderCartDrawer(items, count, totalAmount);
}

// Render Order Drawer
function renderCartDrawer(items, count, totalAmount) {
  const drawerItems = document.getElementById('cart-drawer-items');
  const drawerSummary = document.getElementById('cart-drawer-summary');
  const drawerEmpty = document.getElementById('cart-drawer-empty');
  const drawerCount = document.getElementById('cart-drawer-count');
  const notesBox = document.getElementById('delivery-notes-box');
  const drawerAddrDisplay = document.getElementById('drawer-delivery-addr');

  if (drawerCount) {
    drawerCount.textContent = `${count} ${count === 1 ? 'item' : 'items'} • Expected Total: ₹${totalAmount}`;
  }

  if (drawerAddrDisplay) {
    drawerAddrDisplay.textContent = state.delivery.address || 'Address not set (tap to set)';
  }

  if (count === 0) {
    if (drawerItems) drawerItems.innerHTML = '';
    if (drawerSummary) drawerSummary.classList.add('hidden');
    if (notesBox) notesBox.classList.add('hidden');
    if (drawerEmpty) drawerEmpty.classList.remove('hidden');
    return;
  }

  if (drawerEmpty) drawerEmpty.classList.add('hidden');
  if (drawerSummary) drawerSummary.classList.remove('hidden');
  if (notesBox) notesBox.classList.remove('hidden');

  if (drawerItems) {
    drawerItems.innerHTML = items.map(item => `
      <div class="flex items-center justify-between py-3 border-b border-stone-100 gap-2">
        <div class="flex items-center gap-2.5 min-w-0">
          <img src="${escapeHTML(item.image)}" alt="${escapeHTML(item.name)}" class="w-10 h-10 rounded-lg object-cover flex-shrink-0" onerror="this.onerror=null;this.src='assets/placeholder.svg';"/>
          <div class="min-w-0">
            <h4 class="font-bold text-stone-900 text-xs truncate">${escapeHTML(item.name)}</h4>
            <span class="text-[11px] text-stone-500">₹${item.unitPrice} each</span>
          </div>
        </div>

        <div class="flex items-center gap-2 flex-shrink-0">
          <div class="flex items-center bg-stone-100 rounded-lg p-0.5 border border-stone-200">
            <button class="w-6 h-6 flex items-center justify-center font-bold text-stone-700 hover:text-orange-600 drawer-decrease-btn cursor-pointer" data-item-id="${escapeHTML(item.id)}">-</button>
            <span class="px-2 text-xs font-bold text-stone-800 select-none">${item.quantity}</span>
            <button class="w-6 h-6 flex items-center justify-center font-bold text-stone-700 hover:text-orange-600 drawer-increase-btn cursor-pointer" data-item-id="${escapeHTML(item.id)}">+</button>
          </div>
          <span class="font-bold text-stone-900 text-xs w-14 text-right">₹${item.lineTotal}</span>
          <button class="text-stone-400 hover:text-red-500 drawer-delete-btn p-1 cursor-pointer" data-item-id="${escapeHTML(item.id)}">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </div>
      </div>
    `).join('');

    drawerItems.querySelectorAll('.drawer-increase-btn').forEach(btn => {
      btn.addEventListener('click', () => addToCart(btn.dataset.itemId));
    });
    drawerItems.querySelectorAll('.drawer-decrease-btn').forEach(btn => {
      btn.addEventListener('click', () => removeFromCart(btn.dataset.itemId));
    });
    drawerItems.querySelectorAll('.drawer-delete-btn').forEach(btn => {
      btn.addEventListener('click', () => deleteEntireItem(btn.dataset.itemId));
    });
  }

  const drawerSubtotal = document.getElementById('cart-drawer-subtotal');
  const drawerGrandTotal = document.getElementById('cart-drawer-grand-total');
  if (drawerSubtotal) drawerSubtotal.textContent = `₹${totalAmount}`;
  if (drawerGrandTotal) drawerGrandTotal.textContent = `₹${totalAmount}`;
}

// Drawer Visibility
function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('cart-drawer-overlay');
  if (drawer && overlay) {
    overlay.classList.remove('hidden');
    setTimeout(() => {
      overlay.classList.remove('opacity-0');
      overlay.classList.add('opacity-100');
      drawer.classList.remove('translate-x-full');
      drawer.classList.add('translate-x-0');
    }, 10);
    state.isDrawerOpen = true;
    document.body.style.overflow = 'hidden';
  }
}

function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('cart-drawer-overlay');
  if (drawer && overlay) {
    overlay.classList.remove('opacity-100');
    overlay.classList.add('opacity-0');
    drawer.classList.remove('translate-x-0');
    drawer.classList.add('translate-x-full');
    setTimeout(() => overlay.classList.add('hidden'), 300);
    state.isDrawerOpen = false;
    document.body.style.overflow = '';
  }
}

// Order Compilation (Trigger to restaurant to confirm and deliver the order)
function generateWhatsAppMessage() {
  const { items, totalAmount, count } = getCartTotals();
  if (count === 0) return null;

  const cfg = getRestaurantConfig();
  const restName = cfg.name || 'Restaurant';
  const restLoc = cfg.location?.landmark || cfg.location?.city || '';
  const notes = document.getElementById('delivery-notes')?.value.trim() || state.delivery.notes;
  const address = state.delivery.address || cfg.location?.city || 'Home Delivery';
  const name = state.delivery.name || '';
  const phone = state.delivery.phone || '';

  let msg = `🔔 *NEW HOME DELIVERY ORDER - PLEASE CONFIRM*\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
  msg += `*To:* ${restName}${restLoc ? ` (${restLoc})` : ''}\n`;
  msg += `*From Customer:* Please prepare and deliver this order:\n\n`;
  msg += `📍 *DELIVERY ADDRESS:* ${address}\n`;
  if (name) msg += `👤 *Customer Name:* ${name}\n`;
  if (phone) msg += `📞 *Customer Contact:* ${phone}\n`;
  if (notes) msg += `📝 *Kitchen Instructions:* ${notes}\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
  msg += `🍽️ *ITEMS TO PREPARE:*\n`;

  items.forEach((item, index) => {
    msg += `${index + 1}. *${item.name}* x ${item.quantity}\n`;
    msg += `   • Price: ₹${item.unitPrice} each  |  Subtotal: ₹${item.lineTotal}\n`;
  });

  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
  msg += `💰 *TOTAL EXPECTED BILL: ₹${totalAmount}*\n`;
  msg += `🚀 *Delivery:* FREE Home Delivery\n`;
  msg += `⏰ *Order Time:* ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
  msg += `👉 *ACTION FOR RESTAURANT:*\n`;
  msg += `Please reply with *"ORDER CONFIRMED"* and your estimated delivery time (e.g. 30-40 mins).\n`;
  msg += `If any item is unavailable, please call customer immediately.`;

  return msg;
}

function generateSMSMessage() {
  const { items, totalAmount, count } = getCartTotals();
  if (count === 0) return null;

  const cfg = getRestaurantConfig();
  const restName = cfg.name || 'Restaurant';
  const notes = document.getElementById('delivery-notes')?.value.trim() || state.delivery.notes;
  const address = state.delivery.address || cfg.location?.city || 'Home Delivery';
  const name = state.delivery.name || '';
  const phone = state.delivery.phone ? ` (${state.delivery.phone})` : '';

  let sms = `[NEW ORDER - PLEASE CONFIRM - ${restName}]\n`;
  sms += `Delivery To: ${address}\n`;
  if (name) sms += `Customer: ${name}${phone}\n`;
  if (notes) sms += `Instructions: ${notes}\n`;
  sms += `\nITEMS TO PREPARE:\n`;

  items.forEach((item, idx) => {
    sms += `${idx + 1}. ${item.name} x${item.quantity} = Rs.${item.lineTotal}\n`;
  });

  sms += `\nTOTAL BILL: Rs.${totalAmount} (Free Delivery)\n\n`;
  sms += `ACTION FOR RESTAURANT: Please reply "CONFIRMED" with estimated delivery time.`;

  return sms;
}

// Trigger Checkout: Asks for address if not set, else executes
function triggerCheckout(type = 'whatsapp') {
  const { count } = getCartTotals();
  if (count === 0) {
    alert("Please select dishes first!");
    return;
  }

  // If user hasn't set an address, ask first on checkout
  if (!state.delivery.address) {
    openAddressModal(true, type);
    return;
  }

  executeOrderDispatch(type);
}

// Dispatches order to WhatsApp or SMS
function executeOrderDispatch(type = 'whatsapp') {
  const cfg = getRestaurantConfig();
  const rawWa = cfg.whatsappNumber || "7004230188";
  const cleanDigits = rawWa.replace(/\D/g, '');
  const waPhone = cleanDigits.length === 10 ? `91${cleanDigits}` : cleanDigits;
  const smsPhone = cleanDigits.length === 10 ? cleanDigits : (cleanDigits.startsWith('91') ? cleanDigits.slice(2) : cleanDigits);

  if (type === 'whatsapp') {
    const message = generateWhatsAppMessage();
    const url = `https://wa.me/${waPhone}?text=${encodeURIComponent(message)}`;
    window.open(url, '_blank');
    showToast("Opening WhatsApp with your order & delivery address...");
  } else {
    const smsText = generateSMSMessage();
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const separator = isIOS ? '&' : '?';
    const smsUrl = `sms:${smsPhone}${separator}body=${encodeURIComponent(smsText)}`;

    copyOrderToClipboard(false);
    window.location.href = smsUrl;
    showToast(`Opening SMS to ${cfg.whatsappDisplay || smsPhone}...`);
  }
}

function copyOrderToClipboard(showUserToast = true) {
  const message = generateWhatsAppMessage();
  if (!message) return;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(message).then(() => {
      if (showUserToast) showToast("Order copied to clipboard!");
    });
  }
}

// Toast Helper
function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = `🛵 ${msg}`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 2200);
}

// Event Listeners
function setupEventListeners() {
  // Live Instant Search
  document.getElementById('search-input')?.addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    renderMenu();
  });

  // Dietary Toggle Buttons
  document.querySelectorAll('.diet-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.dietFilter = btn.dataset.diet;
      updateDietFilterUI();
      renderMenu();
    });
  });

  // Top Section Location Change Trigger
  document.getElementById('header-location-btn')?.addEventListener('click', () => openAddressModal(false));
  document.getElementById('drawer-change-addr-btn')?.addEventListener('click', () => {
    closeCartDrawer();
    openAddressModal(false);
  });
  document.getElementById('close-address-modal-btn')?.addEventListener('click', closeAddressModal);

  // Address Modal Form Submit
  document.getElementById('address-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const addr = document.getElementById('modal-address').value;
    const name = document.getElementById('modal-name').value;
    const phone = document.getElementById('modal-phone').value;

    saveDeliveryData(addr, name, phone);
    const targetCheckout = state.pendingCheckoutType;
    closeAddressModal();
    showToast("Address saved in permanent cookies!");

    // If submitted during checkout flow, proceed to WhatsApp/SMS
    if (targetCheckout) {
      state.pendingCheckoutType = null;
      executeOrderDispatch(targetCheckout);
    }
  });

  // Skip Address Button (ONLY visible and usable during order flow)
  document.getElementById('skip-address-btn')?.addEventListener('click', () => {
    const targetCheckout = state.pendingCheckoutType;
    closeAddressModal();
    if (targetCheckout) {
      state.pendingCheckoutType = null;
      executeOrderDispatch(targetCheckout);
    }
  });

  // Call Options Modal Triggers
  document.getElementById('header-call-btn')?.addEventListener('click', openCallModal);
  document.getElementById('drawer-call-btn')?.addEventListener('click', openCallModal);
  document.getElementById('close-call-modal-btn')?.addEventListener('click', closeCallModal);

  // Drawer Triggers
  document.getElementById('nav-cart-btn')?.addEventListener('click', openCartDrawer);
  document.getElementById('floating-cart-btn')?.addEventListener('click', openCartDrawer);
  document.getElementById('close-drawer-btn')?.addEventListener('click', closeCartDrawer);
  document.getElementById('cart-drawer-overlay')?.addEventListener('click', closeCartDrawer);
  document.getElementById('clear-cart-btn')?.addEventListener('click', clearCart);

  // Order Actions
  document.getElementById('order-whatsapp-btn')?.addEventListener('click', () => triggerCheckout('whatsapp'));
  document.getElementById('order-sms-btn')?.addEventListener('click', () => triggerCheckout('sms'));
  document.getElementById('copy-order-btn')?.addEventListener('click', () => copyOrderToClipboard(true));

  // Escape Key
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAddressModal();
      closeCallModal();
      if (state.isDrawerOpen) closeCartDrawer();
    }
  });
}

function updateDietFilterUI() {
  document.querySelectorAll('.diet-filter-btn').forEach(btn => {
    if (btn.dataset.diet === state.dietFilter) {
      btn.classList.add('bg-stone-900', 'text-white', 'border-stone-900');
      btn.classList.remove('bg-white', 'text-stone-700', 'border-stone-200');
    } else {
      btn.classList.remove('bg-stone-900', 'text-white', 'border-stone-900');
      btn.classList.add('bg-white', 'text-stone-700', 'border-stone-200');
    }
  });
}
