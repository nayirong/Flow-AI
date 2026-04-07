/* ============================================================
   main.js — Hey Aircon
   ============================================================ */

// ─── Mobile Navigation ─────────────────────────────────────
const hamburger = document.querySelector('.hamburger');
const navLinks  = document.querySelector('.nav-links');
const navbar    = document.querySelector('.navbar');

function closeMobileDropdowns() {
  document.querySelectorAll('.dropdown-menu.mobile-open').forEach(m => {
    m.classList.remove('mobile-open');
  });
  document.querySelectorAll('.dropdown-toggle').forEach(b => {
    b.setAttribute('aria-expanded', 'false');
    b.textContent = '+';
  });
}

function closeNav() {
  if (!navLinks) return;
  navLinks.classList.remove('open');
  if (hamburger) hamburger.classList.remove('active');
  closeMobileDropdowns();
}

if (hamburger && navLinks) {

  // Wrap each dropdown's parent <a> + new toggle button inside a .nav-row div
  document.querySelectorAll('.nav-links .dropdown').forEach(item => {
    const parentLink = item.querySelector(':scope > a');
    const menu       = item.querySelector('.dropdown-menu');
    if (!parentLink || !menu) return;

    // Create a flex row wrapper for the link + toggle button
    const row = document.createElement('div');
    row.className = 'nav-row';

    // Move the parent link into the row
    item.insertBefore(row, parentLink);
    row.appendChild(parentLink);

    // Create the toggle button and add it to the row
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'dropdown-toggle';
    toggleBtn.setAttribute('aria-label', 'Toggle submenu');
    toggleBtn.setAttribute('aria-expanded', 'false');
    toggleBtn.textContent = '+';
    row.appendChild(toggleBtn);

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.classList.contains('mobile-open');

      // Close all other dropdowns first
      closeMobileDropdowns();

      if (!isOpen) {
        menu.classList.add('mobile-open');
        toggleBtn.setAttribute('aria-expanded', 'true');
        toggleBtn.textContent = '−';
      }
    });
  });

  // Hamburger toggle
  hamburger.addEventListener('click', (e) => {
    e.stopPropagation();
    if (navLinks.classList.contains('open')) {
      closeNav();
    } else {
      navLinks.classList.add('open');
      hamburger.classList.add('active');
    }
  });

  // Close nav when any non-parent link is clicked
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      const parentDropdown = link.closest('.dropdown');
      const isParentLink   = parentDropdown && link === parentDropdown.querySelector('.nav-row > a');
      if (!isParentLink) closeNav();
    });
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (navbar && !navbar.contains(e.target)) closeNav();
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeNav();
  });
}

// ─── FAQ Accordion ─────────────────────────────────────────
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    const item   = btn.closest('.faq-item');
    const isOpen = item.classList.contains('open');
    document.querySelectorAll('.faq-item.open').forEach(i => i.classList.remove('open'));
    if (!isOpen) item.classList.add('open');
  });
});

// ─── Active Nav Highlight ──────────────────────────────────
(function () {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links > li > a, .nav-links .nav-row > a').forEach(a => {
    const href = (a.getAttribute('href') || '').split('/').pop();
    if (href === path || (path === '' && href === 'index.html')) {
      a.classList.add('active');
    }
  });
})();
