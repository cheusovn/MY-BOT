/* ══════════════════════════════════════════════════════
   TRUE AI ACADEMY — script_improved.js
   All functionality: Three.js, GSAP, Lenis, countdown,
   FAQ, count-up, viewer count, toasts, sticky CTA, cursor
══════════════════════════════════════════════════════ */

'use strict';

/* ── 1. LENIS SMOOTH SCROLL ─────────────────────────── */
let lenis;
if (typeof Lenis !== 'undefined') {
  lenis = new Lenis({
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smooth: true,
  });
  function rafLenis(time) {
    lenis.raf(time);
    requestAnimationFrame(rafLenis);
  }
  requestAnimationFrame(rafLenis);
}

/* ── 2. THREE.JS PARTICLE FIELD ─────────────────────── */
(function initThree() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 2000);
  camera.position.z = 600;

  // Particle geometry
  const PARTICLE_COUNT = 1800;
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const colors = new Float32Array(PARTICLE_COUNT * 3);
  const sizes = new Float32Array(PARTICLE_COUNT);

  const colorAcid = new THREE.Color('#C8FF00');
  const colorMint = new THREE.Color('#00FF88');
  const colorDim = new THREE.Color('#1a2010');

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    positions[i * 3]     = (Math.random() - 0.5) * 2000;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 2000;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 800;

    const rand = Math.random();
    let c;
    if (rand < 0.05)      c = colorAcid;
    else if (rand < 0.12) c = colorMint;
    else                  c = colorDim;

    colors[i * 3]     = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;

    sizes[i] = Math.random() * 2.5 + 0.5;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const material = new THREE.PointsMaterial({
    size: 1.5,
    vertexColors: true,
    transparent: true,
    opacity: 0.7,
    sizeAttenuation: true,
  });

  const particles = new THREE.Points(geometry, material);
  scene.add(particles);

  let mouseX = 0;
  let mouseY = 0;
  window.addEventListener('mousemove', (e) => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  function animateThree() {
    requestAnimationFrame(animateThree);
    const t = Date.now() * 0.00008;
    particles.rotation.y = t + mouseX * 0.05;
    particles.rotation.x = mouseY * 0.03;
    renderer.render(scene, camera);
  }
  animateThree();

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
})();

/* ── 3. CUSTOM CURSOR ───────────────────────────────── */
(function initCursor() {
  const cursor = document.getElementById('cursor');
  if (!cursor) return;

  let cx = 0, cy = 0;
  let tx = 0, ty = 0;

  document.addEventListener('mousemove', (e) => {
    tx = e.clientX;
    ty = e.clientY;
  });

  function animateCursor() {
    cx += (tx - cx) * 0.15;
    cy += (ty - cy) * 0.15;
    cursor.style.left = cx + 'px';
    cursor.style.top  = cy + 'px';
    requestAnimationFrame(animateCursor);
  }
  animateCursor();

  document.querySelectorAll('a, button, .faq__question, .pain__card, .review').forEach((el) => {
    el.addEventListener('mouseenter', () => cursor.classList.add('grow'));
    el.addEventListener('mouseleave', () => cursor.classList.remove('grow'));
  });
})();

/* ── 4. GSAP SCROLL REVEAL ──────────────────────────── */
(function initReveal() {
  const revealEls = document.querySelectorAll('.reveal, .reveal-fast');

  if (typeof IntersectionObserver === 'undefined') {
    revealEls.forEach((el) => el.classList.add('visible'));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          const delay = entry.target.classList.contains('reveal-fast') ? 0 : i * 40;
          setTimeout(() => {
            entry.target.classList.add('visible');
          }, Math.min(delay, 400));
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );

  revealEls.forEach((el) => observer.observe(el));
})();

/* ── 5. COUNT-UP ANIMATIONS ─────────────────────────── */
(function initCountUp() {
  const els = document.querySelectorAll('.count-up[data-target]');
  if (!els.length) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const target = parseInt(el.dataset.target, 10);
        const duration = 1800;
        const start = performance.now();

        function update(now) {
          const elapsed = now - start;
          const progress = Math.min(elapsed / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          el.textContent = Math.floor(eased * target).toLocaleString('ru-RU');
          if (progress < 1) requestAnimationFrame(update);
        }

        requestAnimationFrame(update);
        observer.unobserve(el);
      });
    },
    { threshold: 0.5 }
  );

  els.forEach((el) => observer.observe(el));
})();

/* ── 6. LIVE VIEWER COUNT ───────────────────────────── */
(function initViewerCount() {
  const el = document.getElementById('viewerCount');
  if (!el) return;

  let current = 247;
  const MIN = 160;
  const MAX = 450;

  function update() {
    const delta = Math.floor(Math.random() * 11) - 5;
    current = Math.max(MIN, Math.min(MAX, current + delta));
    el.textContent = current;
    setTimeout(update, 3000 + Math.random() * 4000);
  }

  setTimeout(update, 5000);
})();

/* ── 7. COUNTDOWN TIMER ─────────────────────────────── */
(function initCountdown() {
  const STORAGE_KEY = 'trueai_deadline';
  const DURATION_HOURS = 48;

  let deadline = localStorage.getItem(STORAGE_KEY);
  if (!deadline || isNaN(Number(deadline))) {
    deadline = Date.now() + DURATION_HOURS * 60 * 60 * 1000;
    localStorage.setItem(STORAGE_KEY, deadline);
  }
  deadline = Number(deadline);

  const hoursEl   = document.querySelector('[data-countdown="hours"]');
  const minutesEl = document.querySelector('[data-countdown="minutes"]');
  const secondsEl = document.querySelector('[data-countdown="seconds"]');

  if (!hoursEl || !minutesEl || !secondsEl) return;

  function pad(n) { return String(Math.max(0, n)).padStart(2, '0'); }

  function tick() {
    const remaining = Math.max(0, deadline - Date.now());
    const totalSec  = Math.floor(remaining / 1000);
    const hours   = Math.floor(totalSec / 3600);
    const minutes = Math.floor((totalSec % 3600) / 60);
    const seconds = totalSec % 60;

    hoursEl.textContent   = pad(hours);
    minutesEl.textContent = pad(minutes);
    secondsEl.textContent = pad(seconds);

    if (remaining <= 0) {
      // Reset deadline when it hits zero
      const newDeadline = Date.now() + DURATION_HOURS * 60 * 60 * 1000;
      localStorage.setItem(STORAGE_KEY, newDeadline);
      deadline = newDeadline;
    }
  }

  tick();
  setInterval(tick, 1000);
})();

/* ── 8. TOAST NOTIFICATIONS ─────────────────────────── */
(function initToasts() {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toastData = [
    { name: 'Алексей',  city: 'Москва',            action: 'только что начал курс 🚀',                        initials: 'АМ' },
    { name: 'Мария',    city: 'Санкт-Петербург',    action: 'создала карточку и продала за 1 200 ₽ 🎨',       initials: 'МС' },
    { name: 'Дмитрий',  city: 'Екатеринбург',       action: 'получил заказ на 2 500 ₽ 💸',                    initials: 'ДЕ' },
    { name: 'Анна',     city: 'Казань',              action: 'записалась на 2 дня бесплатно',                   initials: 'АК' },
    { name: 'Сергей',   city: 'Новосибирск',         action: 'сделал первое AI-видео 🎬',                       initials: 'СН' },
    { name: 'Елена',    city: 'Краснодар',           action: 'нашла удалённую работу через курс ✨',            initials: 'ЕК' },
    { name: 'Иван',     city: 'Ростов-на-Дону',      action: 'заработал 7 800 ₽ за первую неделю 💸',          initials: 'ИР' },
    { name: 'Ольга',    city: 'Санкт-Петербург',     action: 'взяла третий заказ за месяц 🔥',                  initials: 'ОС' },
    { name: 'Николай',  city: 'Пермь',               action: 'сэкономил 15 000 ₽ на дизайнере',                initials: 'НП' },
    { name: 'Татьяна',  city: 'Новосибирск',         action: 'получила первый заказ прямо во время курса ✨',   initials: 'ТН' },
    { name: 'Артём',    city: 'Самара',              action: 'прошёл все 7 дней и нашёл клиента',              initials: 'АС' },
    { name: 'Виктория', city: 'Казань',              action: 'зарабатывает 25 000 ₽/мес на фрилансе 🎯',       initials: 'ВК' },
    { name: 'Павел',    city: 'Москва',              action: 'перестал платить дизайнеру — делает сам',        initials: 'ПМ' },
    { name: 'Юлия',     city: 'Екатеринбург',        action: 'сделала видео для своего бизнеса за вечер',      initials: 'ЮЕ' },
  ];

  let index = 0;

  function showToast(data) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
      <div class="toast__avatar">${data.initials}</div>
      <div class="toast__body">
        <div><span class="toast__name">${data.name}</span> <span class="toast__city">· ${data.city}</span></div>
        <div>${data.action}</div>
      </div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('out');
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  }

  function nextToast() {
    showToast(toastData[index % toastData.length]);
    index++;
    const delay = 7000 + Math.random() * 5000;
    setTimeout(nextToast, delay);
  }

  // Start after initial delay
  setTimeout(nextToast, 3000);
})();

/* ── 9. FAQ ACCORDION ───────────────────────────────── */
(function initFaq() {
  const items = document.querySelectorAll('.faq__item');
  items.forEach((item) => {
    const btn = item.querySelector('.faq__question');
    if (!btn) return;

    btn.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');

      // Close all
      items.forEach((i) => {
        i.classList.remove('open');
        const q = i.querySelector('.faq__question');
        if (q) q.setAttribute('aria-expanded', 'false');
      });

      // Toggle clicked
      if (!isOpen) {
        item.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });
})();

/* ── 10. STICKY CTA BAR ─────────────────────────────── */
(function initStickyCta() {
  const cta = document.getElementById('stickyCta');
  const finalSection = document.querySelector('[data-final-section]');
  if (!cta) return;

  let heroBottom = 0;
  let finalTop = Infinity;

  function measure() {
    const hero = document.getElementById('top');
    if (hero) heroBottom = hero.getBoundingClientRect().bottom + window.scrollY;
    if (finalSection) finalTop = finalSection.getBoundingClientRect().top + window.scrollY;
  }

  function update() {
    const scrollY = window.scrollY;
    const viewBottom = scrollY + window.innerHeight;
    const pastHero = scrollY > heroBottom - 200;
    const finalVisible = viewBottom >= finalTop + 100;

    if (pastHero && !finalVisible) {
      cta.classList.add('visible');
      cta.classList.remove('hidden');
    } else {
      cta.classList.remove('visible');
      cta.classList.add('hidden');
    }
  }

  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', measure);
  measure();
  update();
})();

/* ── 11. GSAP + SCROLLTRIGGER (OPTIONAL ENHANCEMENT) ── */
(function initGsap() {
  if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined') return;
  gsap.registerPlugin(ScrollTrigger);

  // Parallax on hero title
  const heroTitle = document.querySelector('.hero__title');
  if (heroTitle) {
    gsap.to(heroTitle, {
      y: -60,
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: true,
      },
    });
  }

  // Stagger pain cards on enter
  gsap.from('.pain__card', {
    y: 40,
    opacity: 0,
    stagger: 0.12,
    duration: 0.6,
    ease: 'power2.out',
    scrollTrigger: {
      trigger: '.pain__grid',
      start: 'top 80%',
    },
  });

  // Day cards stagger
  gsap.from('.day__card', {
    y: 40,
    opacity: 0,
    stagger: 0.08,
    duration: 0.5,
    ease: 'power2.out',
    scrollTrigger: {
      trigger: '.program__days',
      start: 'top 80%',
    },
  });
})();

/* ── 12. MAGNETIC BUTTONS ───────────────────────────── */
(function initMagnetic() {
  const buttons = document.querySelectorAll('.btn--primary');
  buttons.forEach((btn) => {
    btn.addEventListener('mousemove', (e) => {
      const rect = btn.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = (e.clientX - cx) * 0.25;
      const dy = (e.clientY - cy) * 0.25;
      btn.style.transform = `translate(${dx}px, ${dy}px) scale(1.04)`;
    });

    btn.addEventListener('mouseleave', () => {
      btn.style.transform = '';
    });
  });
})();

/* ── 13. ANCHOR SMOOTH SCROLL ───────────────────────── */
(function initAnchors() {
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener('click', (e) => {
      const target = document.querySelector(link.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      if (lenis) {
        lenis.scrollTo(target, { offset: -80, duration: 1.2 });
      } else {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
})();
