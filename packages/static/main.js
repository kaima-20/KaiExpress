function apiPost(url, data) {
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data),
    credentials: 'same-origin'
  }).then(async response => {
    const body = await response.json();
    if (!response.ok) throw body;
    return body;
  });
}

function showAlert(message, category = 'success') {
  const container = document.getElementById('api-alerts');
  if (!container) return;
  const alert = document.createElement('div');
  alert.className = `alert alert-${category} alert-dismissible fade show`;
  alert.role = 'alert';
  alert.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;
  container.appendChild(alert);
}

function bindForm(selector, handler) {
  const form = document.querySelector(selector);
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await handler(data);
      showAlert(result.message, 'success');
      if (result.next) window.location.href = result.next;
    } catch (error) {
      showAlert(error.message || 'Something went wrong.', 'danger');
    }
  });
}

if (document.readyState !== 'loading') {
  bindForm('#user-login-form', data => apiPost('/api/login', data));
  bindForm('#user-register-form', data => apiPost('/api/register', data));
  bindForm('#restaurant-login-form', data => apiPost('/api/restaurant/login', data));
  bindForm('#restaurant-register-form', data => apiPost('/api/restaurant/register', data));
  bindForm('#checkout-form', async data => {
    const result = await apiPost('/api/checkout', data);
    return result;
  });
  bindForm('#logout-form', () => apiPost('/api/logout', {}));
} else {
  document.addEventListener('DOMContentLoaded', () => {
    bindForm('#user-login-form', data => apiPost('/api/login', data));
    bindForm('#user-register-form', data => apiPost('/api/register', data));
    bindForm('#restaurant-login-form', data => apiPost('/api/restaurant/login', data));
    bindForm('#restaurant-register-form', data => apiPost('/api/restaurant/register', data));
    bindForm('#checkout-form', async data => {
      const result = await apiPost('/api/checkout', data);
      return result;
    });
    bindForm('#logout-form', () => apiPost('/api/logout', {}));
  });
}
