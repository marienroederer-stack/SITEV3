document.getElementById('year').textContent = new Date().getFullYear();

if (new URLSearchParams(window.location.search).get('envoye') === '1') {
  const feedback = document.getElementById('contact-feedback');
  if (feedback) feedback.hidden = false;
}

const navToggle = document.getElementById('nav-toggle');
const mainNav = document.getElementById('main-nav');

navToggle.addEventListener('click', () => {
  const isOpen = mainNav.classList.toggle('open');
  navToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
});

mainNav.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    mainNav.classList.remove('open');
    navToggle.setAttribute('aria-expanded', 'false');
  });
});

const stage = document.getElementById('coverflow-stage');
if (stage) {
  const cards = Array.from(stage.querySelectorAll('.coverflow-card'));
  const prevBtn = document.getElementById('coverflow-prev');
  const nextBtn = document.getElementById('coverflow-next');
  const dotsWrap = document.getElementById('coverflow-dots');
  const count = cards.length;
  let active = 0;
  let dragged = false;

  cards.forEach((card, i) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.className = 'coverflow-dot';
    dot.setAttribute('aria-label', 'Voir le témoignage ' + (i + 1));
    dot.addEventListener('click', () => setActive(i));
    dotsWrap.appendChild(dot);
    card.addEventListener('click', () => { if (!dragged && i !== active) setActive(i); });
  });
  const dots = Array.from(dotsWrap.children);

  function shortestOffset(index) {
    let diff = index - active;
    if (diff > count / 2) diff -= count;
    if (diff < -count / 2) diff += count;
    return diff;
  }

  function render() {
    cards.forEach((card, i) => {
      const offset = shortestOffset(i);
      const abs = Math.abs(offset);
      let transform, opacity, zIndex, pointerEvents;

      if (abs === 0) {
        transform = 'translateX(0) scale(1) rotateY(0deg)';
        opacity = '1';
        zIndex = 50;
        pointerEvents = 'auto';
      } else if (abs === 1) {
        const dir = offset > 0 ? 1 : -1;
        transform = `translateX(${dir * 58}%) scale(0.82) rotateY(${-dir * 32}deg)`;
        opacity = '0.85';
        zIndex = 40;
        pointerEvents = 'auto';
      } else if (abs === 2) {
        const dir = offset > 0 ? 1 : -1;
        transform = `translateX(${dir * 104}%) scale(0.66) rotateY(${-dir * 42}deg)`;
        opacity = '0.45';
        zIndex = 30;
        pointerEvents = 'auto';
      } else {
        const dir = offset > 0 ? 1 : -1;
        transform = `translateX(${dir * 140}%) scale(0.5) rotateY(${-dir * 45}deg)`;
        opacity = '0';
        zIndex = 0;
        pointerEvents = 'none';
      }

      card.style.transform = transform;
      card.style.opacity = opacity;
      card.style.zIndex = zIndex;
      card.style.pointerEvents = pointerEvents;
      card.classList.toggle('is-active', i === active);
    });

    dots.forEach((dot, i) => dot.classList.toggle('is-active', i === active));

    stage.style.height = cards[active].offsetHeight + 'px';
  }

  function setActive(index) {
    active = ((index % count) + count) % count;
    render();
  }

  window.addEventListener('resize', () => {
    stage.style.height = cards[active].offsetHeight + 'px';
  });

  prevBtn.addEventListener('click', () => setActive(active - 1));
  nextBtn.addEventListener('click', () => setActive(active + 1));

  let isDown = false;
  let startX = 0;

  stage.addEventListener('pointerdown', (e) => {
    isDown = true;
    dragged = false;
    startX = e.clientX;
    stage.setPointerCapture(e.pointerId);
  });

  stage.addEventListener('pointermove', (e) => {
    if (!isDown) return;
    if (Math.abs(e.clientX - startX) > 8) dragged = true;
  });

  const endDrag = (e) => {
    if (!isDown) return;
    isDown = false;
    const delta = e.clientX - startX;
    if (Math.abs(delta) > 50) {
      setActive(active + (delta < 0 ? 1 : -1));
    }
  };
  stage.addEventListener('pointerup', endDrag);
  stage.addEventListener('pointerleave', () => { isDown = false; });

  render();
}
