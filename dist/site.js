const menu = document.querySelector('.menu');
const nav = document.querySelector('.navlinks');
function closeMenu() {
  if (!menu || !nav) return;
  nav.classList.remove('open');
  menu.setAttribute('aria-expanded', 'false');
  menu.textContent = 'Menu';
}

menu?.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open));
  nav?.classList.toggle('open', open);
  menu.textContent = open ? 'Fermer' : 'Menu';
});

nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && nav?.classList.contains('open')) {
    closeMenu();
    menu?.focus();
  }
});

document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-filter]').forEach(item => {
    item.setAttribute('aria-pressed', String(item === button));
  });
  let count = 0;
  document.querySelectorAll('[data-category]').forEach(card => {
    card.hidden = button.dataset.filter !== 'all' && card.dataset.category !== button.dataset.filter;
    if (!card.hidden) count += 1;
  });
  const status = document.getElementById('filterstatus');
  if (status) status.textContent = `${count} projet${count > 1 ? 's présentés' : ' présenté'}`;
}));
const form = document.getElementById('contactform');
if (form) {
  const topic = new URLSearchParams(location.search).get('objet');
  const map = { branding: 0, digital: 1, protection: 2, coaching: 3, Coaching: 3, Intervention: 4, Projet: 6 };
  if (Object.hasOwn(map, topic)) form.elements.subject.selectedIndex = map[topic];

  let csrf = '';
  const status = document.getElementById('formstatus');
  const submit = form.querySelector('button[type="submit"]');

  const showStatus = (message, success) => {
    if (!status) return;
    status.hidden = false;
    status.className = success ? 'success' : 'success';
    status.replaceChildren();
    const paragraph = document.createElement('p');
    paragraph.textContent = message;
    status.append(paragraph);
  };

  fetch('/api/contact-token', { headers: { Accept: 'application/json' } })
    .then(response => response.ok ? response.json() : Promise.reject(new Error('token')))
    .then(data => { csrf = data.token || ''; })
    .catch(() => { csrf = ''; });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!csrf) {
      showStatus('Le formulaire est temporairement indisponible. Écrivez directement à euloge@oloustream.com.', false);
      return;
    }

    if (submit) submit.disabled = true;
    const values = Object.fromEntries(new FormData(form).entries());
    values.csrf = csrf;
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(values),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw new Error(result.message || 'send');
      showStatus(result.message || 'Votre demande a bien été enregistrée.', true);
      form.reset();
    } catch (error) {
      showStatus(error.message === 'send' ? 'Le service est temporairement indisponible. Écrivez directement à euloge@oloustream.com.' : error.message, false);
    } finally {
      if (submit) submit.disabled = false;
    }
  });
}
