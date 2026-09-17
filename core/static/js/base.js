/* ===========================================================
   SHARED BASE JS (Django port)
   Mirrors the static build's init() behavior for the parts that
   survive the port: nav scroll compression, mobile menu toggle,
   and toast rendering/auto-dismiss. Header/footer/mega-menu markup
   itself is now server-rendered in templates/base.html rather than
   injected via the static build's header()/footer() helpers — this file only handles
   interaction, never DOM construction of shared chrome.
   Product-card rendering, star rating, quick view, and the
   the static build's localStorage layer are NOT ported here; those become
   real server-rendered template output in each app's templates.

   Step 2 (catalog) additions: generic, delegated, zero-network-call
   handlers reused across product_detail.html/configurator.html for
   swatch/pill selection, quantity steppers, gallery thumbnails, tabs,
   the sticky purchase bar, and bridging independent variant-group
   radios into AddToCartForm's single `upgrades` field — see the
   comments at each handler below. None of this is AJAX; every actual
   add-to-cart/wishlist/compare action is still a real form POST.
=========================================================== */

(function () {
  'use strict';

  /* ---- TOAST ---- */
  function showToast(message, type) {
    type = type || 'default';
    var container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    var icon = 'bx-check';
    if (type === 'success') icon = 'bx-check-circle';
    if (type === 'error') icon = 'bx-x-circle';
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<i class="bx ' + icon + '"></i><span></span>';
    toast.querySelector('span').textContent = message;
    container.appendChild(toast);
    dismissAfterDelay(toast);
    requestAnimationFrame(function () { toast.classList.add('show'); });
  }
  // Exposed globally so any app's inline AJAX handler (cart totals, promo
  // validation, configurator running total, search-as-you-type) can surface
  // a toast the same way a full-page POST redirect + Django message does.
  window.showToast = showToast;

  function dismissAfterDelay(toast) {
    setTimeout(function () {
      toast.classList.remove('show');
      setTimeout(function () { toast.remove(); }, 400);
    }, 3000);
  }

  /* ---- Generic click-to-select swatch/pill (product-detail color &
     variant pickers, Configurator's step options) ----
     Markup convention: a hidden radio immediately followed by the visible
     element carrying `data-swatch` (a `.color-swatch`, `.variant-option`,
     or `.config-option`). Clicking the visible element checks the radio
     and moves the `.active` class among every `[data-swatch]` sharing
     that radio's `name` — same visual behavior as the static build's
     per-page selectColor()/selectBattery()/etc., just backed by a real
     form field instead of an in-memory JS variable. Zero network calls,
     so this isn't AJAX; the actual add-to-cart is still a normal POST. */
  document.addEventListener('click', function (e) {
    var swatch = e.target.closest('[data-swatch]');
    if (swatch) {
      var input = swatch.previousElementSibling;
      if (input && input.type === 'radio') {
        input.checked = true;
        document.querySelectorAll('[data-swatch]').forEach(function (s) {
          var si = s.previousElementSibling;
          if (si && si.name === input.name) s.classList.remove('active');
        });
        swatch.classList.add('active');
        var nameTargetSelector = swatch.getAttribute('data-name-target');
        if (nameTargetSelector) {
          var nameTarget = document.querySelector(nameTargetSelector);
          if (nameTarget) nameTarget.textContent = swatch.getAttribute('data-name') || '';
        }
      }
      return;
    }

    /* ---- Generic click-to-toggle pill (Configurator's multi-select
       accessories) --- same idea as above, but a checkbox, and each pill
       toggles independently rather than moving `.active` across a group. */
    var toggle = e.target.closest('[data-toggle]');
    if (toggle) {
      var checkbox = toggle.previousElementSibling;
      if (checkbox && checkbox.type === 'checkbox') {
        checkbox.checked = !checkbox.checked;
        toggle.classList.toggle('active', checkbox.checked);
      }
      return;
    }

    /* ---- Quantity stepper (+/-) next to a real, submittable number input --- */
    var qtyBtn = e.target.closest('[data-qty-btn]');
    if (qtyBtn) {
      var qtyWrap = qtyBtn.closest('.qty-selector');
      var qtyInput = qtyWrap && qtyWrap.querySelector('input[type=number]');
      if (qtyInput) {
        var delta = parseInt(qtyBtn.getAttribute('data-qty-btn'), 10) || 0;
        qtyInput.value = Math.max(1, (parseInt(qtyInput.value, 10) || 1) + delta);
      }
      return;
    }

    /* ---- Product gallery thumbnails ---- */
    var thumb = e.target.closest('.product-gallery-thumbs img');
    if (thumb) {
      var thumbsWrap = thumb.closest('.product-gallery-thumbs');
      thumbsWrap.querySelectorAll('img').forEach(function (t) { t.classList.remove('active'); });
      thumb.classList.add('active');
      var galleryMain = thumbsWrap.previousElementSibling;
      var mainImg = galleryMain && galleryMain.querySelector('img');
      if (mainImg) mainImg.src = thumb.src;
      return;
    }

    /* ---- Product detail tabs (Specifications / Features / Reviews / Shipping) ---- */
    var tab = e.target.closest('.product-tab');
    if (tab) {
      var tabsWrap = tab.closest('.product-tabs');
      tabsWrap.querySelectorAll('.product-tab').forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var tabContentTarget = document.getElementById('tab-' + tab.dataset.tab);
      if (tabContentTarget) {
        tabContentTarget.parentElement.querySelectorAll('.product-tab-content').forEach(function (c) { c.classList.remove('active'); });
        tabContentTarget.classList.add('active');
      }
      return;
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    /* ---- Server-rendered toasts (Django messages, already in the DOM) ---- */
    document.querySelectorAll('.toast-container .toast').forEach(function (toast) {
      dismissAfterDelay(toast);
      requestAnimationFrame(function () { toast.classList.add('show'); });
    });

    /* ---- Mobile menu ---- */
    var burger = document.getElementById('navBurger');
    var menu = document.getElementById('mobileMenu');
    if (burger && menu) {
      burger.addEventListener('click', function () {
        menu.classList.toggle('is-open');
        burger.classList.toggle('is-open');
        if (burger.classList.contains('is-open')) {
          burger.children[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
          burger.children[1].style.opacity = '0';
          burger.children[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
        } else {
          burger.children[0].style.transform = '';
          burger.children[1].style.opacity = '';
          burger.children[2].style.transform = '';
        }
      });
    }

    /* ---- Nav scroll compression ---- */
    var nav = document.getElementById('siteNav');
    if (nav) {
      window.addEventListener('scroll', function () {
        if (window.scrollY > 60) nav.style.padding = '10px clamp(20px, 4vw, 56px)';
        else nav.style.padding = '';
      });
    }

    /* ---- Sticky purchase bar (product detail / configurator) ---- */
    var sticky = document.getElementById('stickyPurchase');
    if (sticky) {
      window.addEventListener('scroll', function () {
        if (window.scrollY > 600) sticky.classList.add('is-visible');
        else sticky.classList.remove('is-visible');
      });
    }

    /* ---- Bridge independent variant-group radios (Battery/Suspension/
       Wheels each their own mutually-exclusive `name` so the browser
       enforces one choice per group) into the single repeated `upgrades`
       field cart.forms.AddToCartForm expects, right before the browser's
       own, real form submission proceeds. No fetch/XHR involved — this
       only enriches the POST body of a normal PRG submission. */
    document.querySelectorAll('form[data-add-to-cart-form]').forEach(function (form) {
      form.addEventListener('submit', function () {
        form.querySelectorAll('[data-upgrade-bridge]').forEach(function (el) { el.remove(); });
        form.querySelectorAll('input[type=radio][data-upgrade-group]:checked').forEach(function (radio) {
          var hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'upgrades';
          hidden.value = radio.value;
          hidden.setAttribute('data-upgrade-bridge', '');
          form.appendChild(hidden);
        });
      });
    });

    /* ---- GSAP reveals ---- */
    /* Runs on every page (matching the reference build, which loads GSAP
       unconditionally) but is a no-op wherever there's nothing to select:
       the "never on cart/checkout/account/bookings" rule is enforced by
       those templates simply never emitting [data-reveal], [data-reveal-img],
       or .split-line markup — not by conditionally gating this init call. */
    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
      gsap.registerPlugin(ScrollTrigger);

      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        gsap.set('[data-reveal]', { opacity: 1, y: 0 });
        gsap.set('[data-reveal-img] img', { scale: 1 });
        gsap.set('.split-line > span', { y: 0 });
      } else {
        gsap.utils.toArray('[data-reveal]').forEach(function (el) {
          gsap.to(el, {
            opacity: 1, y: 0, duration: 1, ease: 'power3.out',
            scrollTrigger: { trigger: el, start: 'top 85%' }
          });
        });
        gsap.utils.toArray('[data-reveal-img]').forEach(function (el) {
          var img = el.querySelector('img');
          if (img) {
            gsap.to(img, {
              scale: 1, duration: 1.4, ease: 'power3.out',
              scrollTrigger: { trigger: el, start: 'top 85%' }
            });
          }
        });
        gsap.utils.toArray('.split-line').forEach(function (el) {
          var span = el.querySelector('span');
          if (span) {
            gsap.to(span, {
              y: 0, duration: 1, ease: 'power3.out',
              scrollTrigger: { trigger: el, start: 'top 85%' }
            });
          }
        });
      }
    }
  });
})();
