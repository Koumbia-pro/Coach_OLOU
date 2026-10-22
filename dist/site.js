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

  form.addEventListener('submit', event => {
    event.preventDefault();
    const values = new FormData(form);
    const body = `Bonjour Coach OLOU,\n\n${values.get('message')}\n\nNom : ${values.get('name')}\nEmail : ${values.get('email')}\nOrganisation : ${values.get('company') || 'Non renseignée'}`;
    const subject = `Demande : ${values.get('subject')}`;
    const mailto = `mailto:euloge@oloustream.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    const status = document.getElementById('formstatus');
    if (!status) return;

    status.hidden = false;
    status.className = 'success';
    status.replaceChildren();

    const message = document.createElement('p');
    message.textContent = 'Votre message est prêt. Ouvrez votre messagerie ou copiez le texte ci-dessous.';

    const open = document.createElement('a');
    open.href = mailto;
    open.className = 'textlink';
    open.textContent = 'Ouvrir ma messagerie';

    const copy = document.createElement('button');
    copy.type = 'button';
    copy.id = 'copybrief';
    copy.textContent = 'Copier le message';
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(`${subject}\n\n${body}`);
        copy.textContent = 'Message copié';
      } catch {
        message.textContent = body;
        copy.textContent = 'Sélectionnez le texte ci-dessus';
      }
    });

    status.append(message, open, copy);
  });
}
