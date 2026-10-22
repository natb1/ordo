/* The application shell — state and behaviour for layout.css.
 *
 * The whole point of this file is that an app talks to the layout through the
 * object mount() returns and never through its DOM. Nothing below reads an app's
 * markup, and an app that reaches past this API for a `.shell-` element has
 * coupled itself to an internal that is free to change. The seams are body(id),
 * footer() and scroller(), which hand back elements for an app to fill, because
 * somebody has to fill them.
 *
 *   const shell = Shell.mount({
 *     root:    document.getElementById('app'),
 *     toolbar: node,          // whatever belongs between the two icon buttons
 *     nav:     node,          // the navigation itself
 *     content: node,          // the scrollable middle
 *     footer:  node,          // optional; pinned under the middle, absent while empty
 *     cards:   [ {id, title, background, open, content, onClose} ],
 *     storageKey: 'cadence',  // null to remember nothing
 *   });
 *
 *   shell.open(id, {focus:true})  shell.close(id)  shell.toggle(id)
 *   shell.isOpen(id)  shell.body(id)  shell.addCard(spec)  shell.removeCard(id)
 *   shell.setTitle(id, title)  shell.footer()  shell.scroller()
 *   shell.toggleNav()  shell.openNav()  shell.closeNav()
 *   shell.on('open'|'close'|'nav'|'mode', fn)  shell.refresh()  shell.destroy()
 *
 * A `background` card is one the reader turns on and leaves on — it is listed in
 * the toolbar's ⋮ menu and its state is remembered, as the nav's is: only where
 * it leaves the content usable, beside it or over it with a readable strip still
 * showing. Where it would cover the content, a remembered card would do so on
 * every visit, so there it opens for the moment, is not remembered, and one
 * remembered at a wider width stays shut. A card without
 * that flag is transient: opened by the app in response to something, closed
 * when it is done, and never listed. That distinction is the whole of what
 * replaces modals.
 *
 * Keys and focus. A card opened with {focus:true} takes the focus — onto the one
 * control inside marked data-autofocus, else onto the card itself. Not onto its
 * first field: on a phone a focused field raises the keyboard over the card, and
 * most cards are opened to be read. Whatever had the focus is remembered, and
 * closing the card gives it back, so a reader working from the keyboard is left
 * where they were rather than at the top of the page. Escape puts away the
 * transient card it is pressed in. Pressed in a field, it first leaves the field
 * — what was typed is never one stray key from gone.
 */
(function (global) {
  'use strict';

  var SVG = {
    nav: '<path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
    dots: '<circle cx="10" cy="4.2" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="15.8" r="1.5" fill="currentColor"/>',
    close: '<path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
    tick: '<path d="M4 10.5l4 4 8-9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
  };

  function el(tag, cls, attrs) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    return n;
  }

  function icon(which) {
    var s = el('span');
    s.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true">' + SVG[which] + '</svg>';
    return s.firstChild;
  }

  /* Accepts a node, a string of HTML, or nothing — so an app can hand over a
     built element or just markup, whichever it already has. */
  function fill(slot, value) {
    slot.textContent = '';
    if (value == null) return slot;
    if (typeof value === 'string') slot.innerHTML = value;
    else slot.appendChild(value);
    return slot;
  }

  /* localStorage is a convenience here, never a requirement: it is absent in a
     private window and throws outright in some embeddings, and the layout has to
     come up correctly either way. */
  function store(key) {
    var k = key == null ? null : 'shell:' + key;
    return {
      read: function () {
        if (!k) return {};
        try { return JSON.parse(localStorage.getItem(k)) || {}; } catch (e) { return {}; }
      },
      write: function (v) {
        if (!k) return;
        try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* not worth reporting */ }
      }
    };
  }

  function mount(opts) {
    opts = opts || {};
    var root = opts.root;
    if (!root) throw new Error('Shell.mount needs a root element');
    var saved = store(opts.storageKey);
    var prefs = saved.read();

    var cards = [];            // every registered card, in registration order
    var listeners = {};
    var navOpen = prefs.nav !== false;   // remembered preference, honoured only inline
    // The background cards the reader left open where they had room; null until
    // there is a preference, so a first visit takes each card's spec.open.
    var wanted = Array.isArray(prefs.cards) ? prefs.cards.slice() : null;
    var navWasInline = null;             // to notice the transition, not the state
    var dims = { nav: 0, context: 0, min: 0, strip: 0 };

    /* ---- DOM ------------------------------------------------------------ */

    root.classList.add('shell');
    root.textContent = '';

    var toolbar = el('header', 'shell-toolbar');
    var navBtn = el('button', 'shell-btn', {
      type: 'button', 'aria-expanded': 'false',
      'aria-label': opts.navLabel || 'Navigation'
    });
    navBtn.appendChild(icon('nav'));

    var slot = el('div', 'shell-toolbar-slot');
    fill(slot, opts.toolbar);

    var menuWrap = el('div', 'shell-menuwrap');
    var menuBtn = el('button', 'shell-btn', {
      type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false',
      'aria-label': opts.menuLabel || 'Background cards'
    });
    menuBtn.appendChild(icon('dots'));
    var menu = el('div', 'shell-menu', { role: 'menu' });
    menu.hidden = true;
    menuWrap.appendChild(menuBtn);
    menuWrap.appendChild(menu);

    toolbar.appendChild(navBtn);
    toolbar.appendChild(slot);
    toolbar.appendChild(menuWrap);

    var nav = el('nav', 'shell-nav', { 'aria-label': opts.navLabel || 'Navigation' });
    fill(nav, opts.nav);
    var navId = 'shell-nav-' + Math.random().toString(36).slice(2, 8);
    nav.id = navId;
    navBtn.setAttribute('aria-controls', navId);

    var content = el('main', 'shell-content');
    var scroller = el('div', 'shell-content-scroll');
    fill(scroller, opts.content);
    var footer = el('div', 'shell-content-footer');
    fill(footer, opts.footer);
    content.appendChild(scroller);
    content.appendChild(footer);

    var context = el('aside', 'shell-context', { 'aria-label': opts.contextLabel || 'Context' });
    var scrim = el('div', 'shell-scrim');
    scrim.hidden = true;

    root.appendChild(toolbar);
    root.appendChild(nav);
    root.appendChild(content);
    root.appendChild(context);
    root.appendChild(scrim);

    /* ---- events --------------------------------------------------------- */

    function emit(name, detail) {
      (listeners[name] || []).forEach(function (fn) { fn(detail); });
    }

    /* ---- geometry -------------------------------------------------------
       The three widths live in CSS so an app can retune them there, and are read
       back here rather than duplicated — the alternative is media queries with
       the numbers written out a second time, which is how the two halves drift. */

    function measure() {
      var cs = getComputedStyle(root);
      dims.nav = parseFloat(cs.getPropertyValue('--shell-nav-w')) || 0;
      dims.context = parseFloat(cs.getPropertyValue('--shell-context-w')) || 0;
      dims.min = parseFloat(cs.getPropertyValue('--shell-content-min')) || 0;
      dims.strip = parseFloat(cs.getPropertyValue('--shell-context-strip-min')) || 0;
    }

    /* Whether a card could sit beside the content rather than over it. Asked of
       the width, never of data-context, which reads 'none' while no card is open. */
    function roomForContext() {
      return root.clientWidth >= dims.min + dims.context;
    }

    /* Whether a card would leave the content usable: beside it, or over it with a
       strip still wide enough to read ('inline' or 'overlay', never 'cover'). A
       desk column is the second; a phone is 'cover'. */
    function cardLeavesContent() {
      return root.clientWidth - dims.context >= dims.strip;
    }

    function openCards() {
      return cards.filter(function (c) { return c.open; });
    }

    function apply() {
      var w = root.clientWidth;
      var shown = openCards();
      var ctxW = shown.length ? dims.context : 0;

      /* Nav sits in flow only when the full row fits: itself, a content column
         no narrower than its minimum, and whatever context is currently showing.
         Otherwise it overlays — which on a phone is every time, giving the
         collapsed-by-default behaviour without a width test written twice. */
      var navInline = w >= dims.nav + dims.min + ctxW;

      // Collapse on the way down; restore the remembered preference on the way up.
      // The first measurement counts as a transition, so arriving narrow is the
      // same as becoming narrow.
      if (navWasInline !== navInline) navOpen = navInline && prefs.nav !== false;
      navWasInline = navInline;

      /* The nav is in flow only when there is room for it AND the context beside
         content-min, so whether it takes space never decides the context's mode. */
      var contextInline = w >= dims.min + ctxW;

      root.dataset.nav = navInline ? 'inline' : 'overlay';
      root.dataset.navOpen = String(navOpen);
      /* Overlaid, a card leaves the content beside it usable. Where that strip
         would be too narrow to read, the card covers it, and the content under
         a card is inert: not reachable by touch, keyboard or screen reader. */
      var ctxMode = ctxW === 0 ? 'none'
        : contextInline ? 'inline'
        : (w - dims.context < dims.strip ? 'cover' : 'overlay');
      root.dataset.context = ctxMode;
      scroller.inert = ctxMode === 'cover';

      navBtn.setAttribute('aria-expanded', String(navOpen));
      scrim.hidden = !(navOpen && !navInline);

      emit('mode', {
        nav: root.dataset.nav, navOpen: navOpen, context: root.dataset.context
      });
    }

    /* ---- cards ---------------------------------------------------------- */

    function find(id) {
      for (var i = 0; i < cards.length; i++) if (cards[i].id === id) return cards[i];
      return null;
    }

    function buildCard(spec) {
      var card = el('section', 'shell-card');
      var bar = el('header', 'shell-card-bar');
      var h = el('h2', 'shell-card-title');
      h.id = 'shell-card-title-' + spec.id;
      h.textContent = spec.title || '';
      card.setAttribute('aria-labelledby', h.id);

      var close = el('button', 'shell-btn', {
        type: 'button', 'aria-label': 'Close ' + (spec.title || 'card')
      });
      close.appendChild(icon('close'));
      close.addEventListener('click', function () { api.close(spec.id); });

      var body = el('div', 'shell-card-body', { tabindex: '-1' });
      fill(body, spec.content);

      bar.appendChild(h);
      bar.appendChild(close);
      card.appendChild(bar);
      card.appendChild(body);
      return { card: card, body: body, title: h, close: close };
    }

    /* Cards and menu items are moved into place, never rebuilt. Detaching a card
       resets its scroll position and throws out any focus inside it, and rebuilding
       the menu under a keypress destroys the item that was just activated. */
    function renderCards() {
      var shown = openCards();
      Array.prototype.slice.call(context.children).forEach(function (n) {
        if (!shown.some(function (c) { return c.el.card === n; })) context.removeChild(n);
      });
      shown.forEach(function (c, i) {
        var at = context.children[i] || null;
        if (at !== c.el.card) context.insertBefore(c.el.card, at);
      });
      renderMenu();
      apply();
    }

    function renderMenu() {
      var bg = cards.filter(function (c) { return c.background; });
      menuWrap.hidden = bg.length === 0;
      bg.forEach(function (c, i) {
        var b = c.el.item;
        b.setAttribute('aria-checked', String(!!c.open));
        b.lastChild.textContent = c.title || c.id;
        var at = menu.children[i] || null;
        if (at !== b) menu.insertBefore(b, at);
      });
      while (menu.children.length > bg.length) menu.removeChild(menu.lastChild);
    }

    function menuItem(c) {
      var b = el('button', null, { type: 'button', role: 'menuitemcheckbox' });
      var tick = icon('tick');
      tick.classList.add('shell-tick');
      b.appendChild(tick);
      b.appendChild(document.createTextNode(''));
      /* Where the card cannot sit beside the content it lands under this menu, so
         choosing it puts the menu away and gives the card the focus — the rule the
         overlaid nav keeps. Beside the content the menu covers nothing and stays,
         so several cards can be turned on in a row. */
      b.addEventListener('click', function () {
        if (c.open) { api.close(c.id); return; }
        if (roomForContext()) { api.open(c.id); return; }
        setMenu(false);
        api.open(c.id, { focus: true });
      });
      return b;
    }

    /* What had the focus before a card took it, to be given back when it closes.
       Nothing, if that was the page itself or the card's own inside. */
    function opener(c) {
      var a = document.activeElement;
      return a && a !== document.body && !c.el.card.contains(a) ? a : null;
    }

    function giveBack(c) {
      var t = c.opener;
      c.opener = null;
      // An item of a menu that has since closed cannot hold focus; its button can.
      if (t && menu.contains(t) && menu.hidden) t = menuBtn;
      if (t && t.isConnected) t.focus({ preventScroll: true });
    }

    /* The card body, unless the app marked a control that the card exists to be
       typed into. Never simply the first field — see the header. */
    function focusFirst(c) {
      var t = c.el.body.querySelector('[data-autofocus]');
      (t || c.el.body).focus();
    }

    function persist() {
      var v = { nav: prefs.nav !== false };
      if (wanted) v.cards = wanted;
      saved.write(v);
    }

    /* The reader opened or closed a background card. Remembered only where it
       leaves the content usable (see the header). */
    function want(c, open) {
      if (!c.background || !cardLeavesContent()) return;
      if (!wanted) wanted = cards.filter(function (x) { return x.background && x.open && x !== c; })
                                 .map(function (x) { return x.id; });
      wanted = wanted.filter(function (id) { return id !== c.id; });
      if (open) wanted.push(c.id);
      persist();
    }

    function setMenu(open) {
      menu.hidden = !open;
      menuBtn.setAttribute('aria-expanded', String(open));
    }

    /* ---- API ------------------------------------------------------------ */

    var api = {
      addCard: function (spec) {
        if (find(spec.id)) throw new Error('Shell: duplicate card id ' + spec.id);
        var c = {
          id: spec.id, title: spec.title, background: !!spec.background,
          open: false, onClose: spec.onClose, el: buildCard(spec)
        };
        if (c.background) c.el.item = menuItem(c);
        cards.push(c);
        // A stored preference wins; spec.open is only the state of a first visit.
        // Either way it opens only where it leaves the content usable (see the header).
        if (c.background) {
          c.open = cardLeavesContent() && (wanted ? wanted.indexOf(c.id) !== -1 : !!spec.open);
        }
        renderCards();
        return api;
      },

      /* Closed first, so whoever tracks cards through 'close' hears about it and a
         removed background card is not remembered as open. */
      removeCard: function (id) {
        api.close(id);
        if (wanted && wanted.indexOf(id) !== -1) {
          wanted = wanted.filter(function (w) { return w !== id; });
          persist();
        }
        cards = cards.filter(function (c) { return c.id !== id; });
        renderCards();
        return api;
      },

      /* 'open' is emitted before focus is taken, so an app that fills the card on
         'open' has filled it by the time focus looks for what it marked. */
      open: function (id, o) {
        var c = find(id);
        if (!c) return api;
        if (!c.open) {
          c.opener = opener(c);
          c.open = true;
          renderCards();
          want(c, true);
          emit('open', { id: id });
        }
        if (o && o.focus) {
          // Opened again from somewhere else: that is where focus goes back to.
          c.opener = opener(c) || c.opener;
          focusFirst(c);
        }
        return api;
      },

      close: function (id) {
        var c = find(id);
        if (!c || !c.open) return api;
        // Detaching the card drops any focus inside it on the floor; pick it up.
        var had = c.el.card.contains(document.activeElement);
        c.open = false;
        renderCards();
        want(c, false);
        if (had) giveBack(c);
        else c.opener = null;
        if (c.onClose) c.onClose();
        emit('close', { id: id, hadFocus: had });
        return api;
      },

      toggle: function (id) {
        var c = find(id);
        return c && c.open ? api.close(id) : api.open(id);
      },

      isOpen: function (id) { var c = find(id); return !!(c && c.open); },

      /* The one place an app is meant to reach into a card: where its contents go. */
      body: function (id) { var c = find(id); return c ? c.el.body : null; },

      /* The same seam for the content area: the element that scrolls, and the strip
         pinned beneath it. An empty footer takes no room, so an app shows and hides
         one by filling and emptying it — there is no second switch to forget, and
         no state kept here that could disagree with what is in the DOM. */
      scroller: function () { return scroller; },
      footer: function () { return footer; },

      setTitle: function (id, title) {
        var c = find(id);
        if (c) {
          c.title = title;
          c.el.title.textContent = title;
          c.el.close.setAttribute('aria-label', 'Close ' + (title || 'card'));
          if (c.background) renderMenu();
        }
        return api;
      },

      openNav: function () { return setNav(true); },
      closeNav: function () { return setNav(false); },
      toggleNav: function () { return setNav(!navOpen); },

      on: function (name, fn) {
        (listeners[name] = listeners[name] || []).push(fn);
        return api;
      },

      refresh: function () { measure(); apply(); return api; },

      destroy: function () {
        if (ro) ro.disconnect();
        else global.removeEventListener('resize', apply);
        document.removeEventListener('keydown', onKey);
        document.removeEventListener('click', onDocClick);
      }
    };

    function setNav(open) {
      navOpen = open;
      if (root.dataset.nav === 'inline') { prefs.nav = open; persist(); }
      apply();
      emit('nav', { open: open });
      return api;
    }

    /* ---- wiring --------------------------------------------------------- */

    navBtn.addEventListener('click', function () { api.toggleNav(); });
    menuBtn.addEventListener('click', function () { setMenu(menu.hidden); });
    scrim.addEventListener('click', function () { api.closeNav(); });
    /* An overlaid nav covers what it navigates to, so choosing anything in it puts
       it away. Inline it stays: there it costs nothing, and closing it would be
       remembered as the reader's preference. */
    nav.addEventListener('click', function (e) {
      if (root.dataset.nav === 'overlay' && navOpen && e.target.closest('a,button')) api.closeNav();
    });

    function onKey(e) {
      if (e.key !== 'Escape') return;
      if (!menu.hidden) { setMenu(false); menuBtn.focus(); return; }
      if (navOpen && root.dataset.nav === 'overlay') { api.closeNav(); navBtn.focus(); return; }
      /* Escape puts away the card it is pressed in, if that card is transient. A
         background card was turned on by the reader and stays until they turn it
         off. From a field the first Escape only leaves the field, so a card is
         never closed — and what was typed in it dropped — by one stray key. */
      var c = cardOf(e.target);
      if (!c || c.background) return;
      if (isField(e.target)) { c.el.body.focus(); return; }
      api.close(c.id);
    }

    function cardOf(node) {
      for (var i = 0; i < cards.length; i++)
        if (cards[i].open && cards[i].el.card.contains(node)) return cards[i];
      return null;
    }

    function isField(n) {
      return !!n && (n.isContentEditable || (n.matches && n.matches(
        'textarea, select, input:not([type=button]):not([type=submit]):not([type=reset])' +
        ':not([type=checkbox]):not([type=radio])')));
    }

    function onDocClick(e) {
      if (!menu.hidden && !menuWrap.contains(e.target)) setMenu(false);
    }

    document.addEventListener('keydown', onKey);
    document.addEventListener('click', onDocClick);

    var ro = null;
    if (global.ResizeObserver) {
      ro = new ResizeObserver(function () { apply(); });
      ro.observe(root);
    } else {
      global.addEventListener('resize', apply);
    }

    measure();
    (opts.cards || []).forEach(api.addCard);
    renderCards();
    return api;
  }

  global.Shell = { mount: mount };
})(window);
