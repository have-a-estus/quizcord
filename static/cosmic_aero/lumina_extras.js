/* ============================================
   LUMINA EXTRAS - Menu de Contexto, Mini Perfil & Perfil Completo
   v2.0 - Corrigido: inicializa mesmo se DOM já estiver pronto
   ============================================ */

// ===== CACHE =====
let _blockedList = [];
let _blockedLoaded = false;

// ===== INIT =====
function initLuminaExtras() {
  console.log('[LuminaExtras] Iniciando...');
  loadBlockedList();
  patchAppendMessage();

  // Bind em elementos já existentes
  bindAllInteractiveElements();

  // Polling para novos elementos (fallback seguro)
  setInterval(bindAllInteractiveElements, 300);

  // Context menu global
  document.addEventListener('contextmenu', handleGlobalContextMenu);

  // Event delegation para clicks no chat (mais confiável que polling)
  setupChatDelegation();

  console.log('[LuminaExtras] Iniciado com sucesso');
}

// Inicia IMEDIATAMENTE se DOM já estiver pronto, senão espera
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLuminaExtras);
} else {
  initLuminaExtras();
}

// ===== EVENT DELEGATION NO CHAT (mais confiável) =====
function setupChatDelegation() {
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  chatArea.addEventListener('click', (e) => {
    const author = e.target.closest('.msg-author');
    const avatar = e.target.closest('.msg-avatar');

    if (author) {
      e.stopPropagation();
      const bubble = author.closest('.message-bubble');
      if (!bubble) return;
      let uid = bubble.dataset.uid;
      if (!uid) {
        const name = author.textContent.trim();
        uid = resolveUserIdByName(name);
        if (uid) bubble.dataset.uid = uid;
      }
      if (uid && uid !== me?.id) showMiniProfile(uid, author);
      return;
    }

    if (avatar) {
      e.stopPropagation();
      const bubble = avatar.closest('.message-bubble');
      if (!bubble) return;
      let uid = bubble.dataset.uid;
      if (!uid) {
        const authorEl = bubble.querySelector('.msg-author');
        const name = authorEl ? authorEl.textContent.trim() : null;
        uid = resolveUserIdByName(name);
        if (uid) bubble.dataset.uid = uid;
      }
      if (uid && uid !== me?.id) showMiniProfile(uid, avatar);
      return;
    }
  });

  chatArea.addEventListener('contextmenu', (e) => {
    const bubble = e.target.closest('.message-bubble');
    if (!bubble || bubble.classList.contains('own')) return;

    let uid = bubble.dataset.uid;
    if (!uid) {
      const authorEl = bubble.querySelector('.msg-author');
      const name = authorEl ? authorEl.textContent.trim() : null;
      uid = resolveUserIdByName(name);
      if (uid) bubble.dataset.uid = uid;
    }
    if (!uid || uid === me?.id) return;

    e.preventDefault();
    e.stopPropagation();
    const authorEl = bubble.querySelector('.msg-author');
    const name = authorEl ? authorEl.textContent.trim() : 'Usuario';
    const avatarEl = bubble.querySelector('.msg-avatar img');
    const avatar = avatarEl ? avatarEl.src : '/static/cosmic_aero/alpacas/alpaca_gray.png';
    showFriendContextMenu(e, uid, name, avatar);
  });
}

// ===== PATCH appendMessage para guardar user.id =====
function patchAppendMessage() {
  if (typeof appendMessage !== 'function') {
    console.log('[LuminaExtras] appendMessage nao encontrado');
    return;
  }
  const original = appendMessage;
  appendMessage = function(m) {
    original(m);
    const area = document.getElementById('chatArea');
    if (!area) return;
    const lastBubble = area.lastElementChild;
    if (lastBubble && m.user?.id && !lastBubble.dataset.uid) {
      lastBubble.dataset.uid = m.user.id;
      lastBubble.dataset.uname = m.user.name || '';
    }
  };
  console.log('[LuminaExtras] appendMessage patched');
}

// ===== RESOLVE USER ID por nome =====
function resolveUserIdByName(name) {
  if (!name) return null;
  const friend = (window.friends?.friends || []).find(f => (f.display_name || f.username) === name);
  if (friend) return friend.fid;
  if (window.currentCircle?.members) {
    const member = window.currentCircle.members.find(m => (m.display_name || m.username) === name);
    if (member) return member.id;
  }
  return null;
}

// ===== BLOQUEIOS =====
async function loadBlockedList() {
  if (!token) return;
  try {
    const res = await fetch(API + '/api/blocks', { headers: { 'Authorization': 'Bearer ' + token } });
    if (res.ok) {
      _blockedList = await res.json();
      _blockedLoaded = true;
    }
  } catch (e) { console.log('[LuminaExtras] Erro ao carregar bloqueios:', e); }
}

function isBlocked(userId) {
  return _blockedList.some(b => b.id === userId);
}

async function blockUser(userId) {
  if (!token) return;
  try {
    const res = await fetch(API + '/api/users/' + encodeURIComponent(userId) + '/block', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.ok) {
      await loadBlockedList();
      showToast('Bloqueado', 'Usuario bloqueado com sucesso', '#ef4444');
      closeAnyLumina();
    } else {
      const d = await res.json();
      showToast('Erro', d.detail || 'Nao foi possivel bloquear', '#ef4444');
    }
  } catch (e) { showToast('Erro', 'Falha na conexao', '#ef4444'); }
}

async function unblockUser(userId) {
  if (!token) return;
  try {
    const res = await fetch(API + '/api/users/' + encodeURIComponent(userId) + '/unblock', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.ok) {
      await loadBlockedList();
      showToast('Desbloqueado', 'Usuario desbloqueado', '#4ade80');
      closeAnyLumina();
    }
  } catch (e) { showToast('Erro', 'Falha na conexao', '#ef4444'); }
}

// ===== BIND ALL (polling - fallback) =====
function bindAllInteractiveElements() {
  // 1. Avatares no painel (contact-item)
  document.querySelectorAll('.contact-item .contact-avatar-wrap, .contact-item .contact-avatar').forEach(el => {
    if (el._luminaBound) return;
    el._luminaBound = true;
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const item = el.closest('.contact-item');
      if (!item) return;
      const fid = item.dataset.peer;
      if (fid && fid !== me?.id) showMiniProfile(fid, el);
    });
  });

  // 2. Avatares na tela de amigos (friends-row)
  document.querySelectorAll('.friends-row .friends-row-avatar-wrap, .friends-row .friends-row-avatar').forEach(el => {
    if (el._luminaBound) return;
    el._luminaBound = true;
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = el.closest('.friends-row');
      if (!row) return;
      const onclick = row.getAttribute('onclick') || '';
      const match = onclick.match(/openDM\('([^']+)'/);
      const fid = match ? match[1] : null;
      if (fid && fid !== me?.id) showMiniProfile(fid, el);
    });
  });
}

// ===== CONTEXT MENU =====
function handleGlobalContextMenu(e) {
  // 1. Painel (contact-item)
  const item = e.target.closest('.contact-item');
  if (item) {
    e.preventDefault();
    const fid = item.dataset.peer;
    if (!fid) return;
    const nameEl = item.querySelector('.contact-name');
    const name = nameEl ? nameEl.textContent : 'Usuario';
    const imgEl = item.querySelector('.contact-avatar img');
    const avatar = imgEl ? imgEl.src : '/static/cosmic_aero/alpacas/alpaca_gray.png';
    showFriendContextMenu(e, fid, name, avatar);
    return;
  }

  // 2. Tela de amigos (friends-row)
  const row = e.target.closest('.friends-row');
  if (row && row.closest('.friends-list')) {
    e.preventDefault();
    const onclick = row.getAttribute('onclick') || '';
    const match = onclick.match(/openDM\('([^']+)',\s*'([^']+)'/);
    const fid = match ? match[1] : null;
    const name = match ? match[2] : 'Usuario';
    const imgEl = row.querySelector('.friends-row-avatar');
    const avatar = imgEl ? imgEl.src : '/static/cosmic_aero/alpacas/alpaca_gray.png';
    if (fid) showFriendContextMenu(e, fid, name, avatar);
    return;
  }

  // 3. Chat já é tratado pelo listener no chatArea (setupChatDelegation)
}

function showFriendContextMenu(e, friendId, friendName, friendAvatar) {
  closeAnyLumina();

  const blocked = isBlocked(friendId);
  const menu = document.createElement('div');
  menu.className = 'lumina-context-menu';
  menu.id = 'luminaContextMenu';
  menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(e.clientY, window.innerHeight - 160) + 'px';

  const safeName = friendName.replace(/'/g, "\\'");

  menu.innerHTML = `
    <button class="lumina-ctx-item" onclick="showFullProfile('${friendId}'); closeAnyLumina();">
      <span class="lumina-ctx-icon">👤</span> Ver perfil
    </button>
    <button class="lumina-ctx-item" onclick="openDM('${friendId}', '${safeName}', '#a78bfa'); closeAnyLumina();">
      <span class="lumina-ctx-icon">💬</span> Enviar mensagem
    </button>
    <div class="lumina-ctx-divider"></div>
    ${blocked ? `
    <button class="lumina-ctx-item" onclick="unblockUser('${friendId}');">
      <span class="lumina-ctx-icon">🔓</span> Desbloquear
    </button>
    ` : `
    <button class="lumina-ctx-item danger" onclick="blockUser('${friendId}');">
      <span class="lumina-ctx-icon">🚫</span> Bloquear
    </button>
    `}
  `;

  document.body.appendChild(menu);

  setTimeout(() => {
    document.addEventListener('click', function closeCtx(ev) {
      if (!menu.contains(ev.target)) {
        menu.remove();
        document.removeEventListener('click', closeCtx);
      }
    });
  }, 10);
}

// ===== MINI PROFILE =====
function showMiniProfile(userId, anchorEl) {
  closeAnyLumina();
  if (!userId || userId === me?.id) return;

  const rect = anchorEl.getBoundingClientRect();
  const popover = document.createElement('div');
  popover.className = 'lumina-mini-profile';
  popover.id = 'luminaMiniProfile';

  let left = rect.right + 12;
  let top = rect.top;
  if (left + 280 > window.innerWidth) left = rect.left - 292;
  if (top + 200 > window.innerHeight) top = window.innerHeight - 220;
  if (top < 10) top = 10;
  popover.style.left = left + 'px';
  popover.style.top = top + 'px';

  popover.innerHTML = `
    <div style="text-align:center;padding:20px;color:#6366f1;font-size:13px;">
      <div style="display:flex;gap:4px;justify-content:center;">
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite;"></span>
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite 0.2s;"></span>
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite 0.4s;"></span>
      </div>
      <div style="margin-top:8px;">Carregando...</div>
    </div>
  `;
  document.body.appendChild(popover);

  fetch(API + '/api/users/' + encodeURIComponent(userId) + '/profile', {
    headers: { 'Authorization': 'Bearer ' + token }
  })
  .then(r => r.ok ? r.json() : null)
  .then(user => {
    if (!user || !document.getElementById('luminaMiniProfile')) return;
    const statusMap = { online: '#10b981', busy: '#ef4444', away: '#f59e0b', invisible: '#6b7280', offline: '#6b7280' };
    const statusColor = statusMap[user.status] || '#6b7280';
    const statusLabel = { online: 'Online', busy: 'Ocupado', away: 'Ausente', invisible: 'Invisivel', offline: 'Offline' }[user.status] || 'Offline';
    const safeName = escapeHtml(user.display_name || user.username).replace(/'/g, "\\'");

    popover.innerHTML = `
      <div class="lumina-mini-header">
        <img src="${user.avatar_image || '/static/cosmic_aero/alpacas/alpaca_gray.png'}" class="lumina-mini-avatar" alt="">
        <div class="lumina-mini-info">
          <div class="lumina-mini-name">${escapeHtml(user.display_name || user.username)}</div>
          <div class="lumina-mini-user">@${escapeHtml(user.username)}</div>
          <div class="lumina-mini-status">
            <span class="lumina-mini-status-dot" style="background:${statusColor};box-shadow:0 0 6px ${statusColor}99"></span>
            ${statusLabel}
          </div>
        </div>
      </div>
      ${user.bio ? `<div class="lumina-mini-bio">${escapeHtml(user.bio)}</div>` : ''}
      <div class="lumina-mini-actions">
        <button class="lumina-mini-btn primary" onclick="openDM('${user.id}', '${safeName}', '${user.avatar_color || '#a78bfa'}'); closeAnyLumina();">💬 Mensagem</button>
        <button class="lumina-mini-btn ghost" onclick="showFullProfile('${user.id}'); closeAnyLumina();">👤 Perfil</button>
      </div>
    `;
  })
  .catch(() => {
    if (document.getElementById('luminaMiniProfile')) {
      popover.innerHTML = `<div style="text-align:center;padding:20px;color:#f87171;font-size:13px;">Erro ao carregar perfil</div>`;
    }
  });

  setTimeout(() => {
    document.addEventListener('click', function closeMini(ev) {
      if (!popover.contains(ev.target) && ev.target !== anchorEl && !anchorEl.contains(ev.target)) {
        popover.remove();
        document.removeEventListener('click', closeMini);
      }
    });
  }, 10);
}

// ===== FULL PROFILE MODAL =====
async function showFullProfile(userId) {
  closeAnyLumina();
  closeModal();

  openModal('Perfil', `
    <div style="text-align:center;padding:40px;color:#6366f1;">
      <div style="display:flex;gap:4px;justify-content:center;margin-bottom:12px;">
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite;"></span>
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite 0.2s;"></span>
        <span style="width:6px;height:6px;background:#8b5cf6;border-radius:50%;animation:typingDot 1.4s ease-in-out infinite 0.4s;"></span>
      </div>
      <div style="font-size:13px;">Carregando perfil...</div>
    </div>
  `, `<button class="btn-sm btn-ghost" onclick="closeModal()">Fechar</button>`);

  const modalBox = document.getElementById('modalBox');
  if (modalBox) modalBox.classList.add('lumina-profile-modal-box');

  try {
    const [profileRes, mutualsRes] = await Promise.all([
      fetch(API + '/api/users/' + encodeURIComponent(userId) + '/profile', {
        headers: { 'Authorization': 'Bearer ' + token }
      }),
      fetch(API + '/api/users/' + encodeURIComponent(userId) + '/mutuals', {
        headers: { 'Authorization': 'Bearer ' + token }
      })
    ]);

    if (!profileRes.ok) {
      closeModal();
      showToast('Erro', 'Usuario nao encontrado', '#ef4444');
      return;
    }

    const user = await profileRes.json();
    const mutuals = mutualsRes.ok ? await mutualsRes.json() : { friends: [], circles: [] };
    const blocked = isBlocked(userId);

    const statusMap = { online: '#10b981', busy: '#ef4444', away: '#f59e0b', invisible: '#6b7280', offline: '#6b7280' };
    const statusColor = statusMap[user.status] || '#6b7280';
    const statusLabel = { online: 'Online', busy: 'Ocupado', away: 'Ausente', invisible: 'Invisivel', offline: 'Offline' }[user.status] || 'Offline';
    const safeName = escapeHtml(user.display_name || user.username).replace(/'/g, "\\'");

    let mutualFriendsHtml = '';
    if (mutuals.friends && mutuals.friends.length) {
      mutualFriendsHtml = mutuals.friends.map(f => `
        <div class="lumina-mutual-row" onclick="showFullProfile('${f.id}');">
          <img src="${f.avatar_image || '/static/cosmic_aero/alpacas/alpaca_gray.png'}" class="lumina-mutual-avatar" alt="">
          <div class="lumina-mutual-info">
            <div class="lumina-mutual-name">${escapeHtml(f.display_name || f.username)}</div>
            <div class="lumina-mutual-sub">@${escapeHtml(f.username)}</div>
          </div>
        </div>
      `).join('');
    } else {
      mutualFriendsHtml = '<div class="lumina-empty-state">Nenhum amigo em comum</div>';
    }

    let mutualCirclesHtml = '';
    if (mutuals.circles && mutuals.circles.length) {
      mutualCirclesHtml = mutuals.circles.map(c => `
        <div class="lumina-mutual-row" onclick="selectCircle('${c.id}'); closeModal();">
          <div class="lumina-mutual-avatar" style="background:${c.color}20;color:${c.color};display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;border:2px solid ${c.color}40;">${c.name[0].toUpperCase()}</div>
          <div class="lumina-mutual-info">
            <div class="lumina-mutual-name">${escapeHtml(c.name)}</div>
            <div class="lumina-mutual-sub">Circulo</div>
          </div>
        </div>
      `).join('');
    } else {
      mutualCirclesHtml = '<div class="lumina-empty-state">Nenhum circulo em comum</div>';
    }

    const bodyHtml = `
      <div class="lumina-profile-modal">
        <div class="lumina-profile-banner">
        </div>
        <div class="lumina-profile-avatar-section">
          <img src="${user.avatar_image || '/static/cosmic_aero/alpacas/alpaca_gray.png'}" class="lumina-profile-avatar-big" alt="">
          <div class="lumina-profile-status-big" style="background:${statusColor};box-shadow:0 0 8px ${statusColor}99"></div>
        </div>
        <div class="lumina-profile-body">
          <div class="lumina-profile-name-row">
            <div class="lumina-profile-display">${escapeHtml(user.display_name || user.username)}</div>
          </div>
          <div class="lumina-profile-username">@${escapeHtml(user.username)}</div>
          <div class="lumina-profile-id">ID: ${user.id}</div>

          ${user.bio ? `
          <div class="lumina-profile-section">
            <div class="lumina-profile-section-title">Sobre mim</div>
            <div class="lumina-profile-bio">${escapeHtml(user.bio)}</div>
          </div>
          ` : ''}

          <div class="lumina-profile-divider"></div>

          <div class="lumina-profile-section">
            <div class="lumina-profile-section-title">Amigos em comum · ${mutuals.friends?.length || 0}</div>
            <div class="lumina-profile-mutuals">${mutualFriendsHtml}</div>
          </div>

          <div class="lumina-profile-section">
            <div class="lumina-profile-section-title">Circulos em comum · ${mutuals.circles?.length || 0}</div>
            <div class="lumina-profile-mutuals">${mutualCirclesHtml}</div>
          </div>

          <div class="lumina-profile-actions-row">
            <button class="lumina-profile-btn msg" onclick="openDM('${user.id}', '${safeName}', '${user.avatar_color || '#a78bfa'}'); closeModal();">
              💬 Enviar mensagem
            </button>
            ${blocked ? `
            <button class="lumina-profile-btn unblock" onclick="unblockUser('${user.id}'); closeModal();">
              🔓 Desbloquear
            </button>
            ` : `
            <button class="lumina-profile-btn block" onclick="blockUser('${user.id}'); closeModal();">
              🚫 Bloquear
            </button>
            `}
          </div>
        </div>
      </div>
    `;

    openModal('', bodyHtml, `<button class="btn-sm btn-ghost" onclick="closeModal(); document.getElementById('modalBox').classList.remove('lumina-profile-modal-box');">Fechar</button>`);
    document.getElementById('modalTitle').style.display = 'none';

  } catch (e) {
    if (modalBox) modalBox.classList.remove('lumina-profile-modal-box');
    closeModal();
    showToast('Erro', 'Nao foi possivel carregar o perfil', '#ef4444');
  }
}

// ===== UTILS =====
function closeAnyLumina() {
  const ctx = document.getElementById('luminaContextMenu');
  if (ctx) ctx.remove();
  const mini = document.getElementById('luminaMiniProfile');
  if (mini) mini.remove();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAnyLumina();
});

setInterval(() => {
  if (token) loadBlockedList();
}, 30000);
