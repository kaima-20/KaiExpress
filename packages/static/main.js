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

function bindCheckout() {
  const form = document.querySelector('#checkout-form');
  if (!form) return;

  const item = form.querySelector('[name="item_id"]');
  const quantity = form.querySelector('[name="quantity"]');
  const total = form.querySelector('#checkout-total');
  const buttonLabel = form.querySelector('#checkout-button-label');

  const updateTotal = () => {
    const selected = item.options[item.selectedIndex];
    const price = Number(selected?.textContent.match(/\$([\d.]+)/)?.[1] || 0);
    total.textContent = `$${(price * Math.max(1, Number(quantity.value) || 1)).toFixed(2)}`;
  };

  const updatePaymentFields = () => {
    const method = form.querySelector('[name="payment_method"]:checked')?.value;
    buttonLabel.textContent = method === 'cash_on_delivery' ? 'Place order' : 'Continue to payment';
  };

  item.addEventListener('change', updateTotal);
  quantity.addEventListener('input', updateTotal);
  form.querySelectorAll('[name="payment_method"]').forEach(input => input.addEventListener('change', updatePaymentFields));
  updateTotal();
  updatePaymentFields();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await apiPost('/api/checkout', data);
      showAlert(result.message || 'Your order was submitted.', 'success');
      if (result.next) window.location.href = result.next;
    } catch (error) {
      showAlert(error.message || 'We could not complete checkout.', 'danger');
    }
  });
}

function bindForms() {
  bindCheckout();
  bindForm('#user-login-form', data => apiPost('/api/login', data));
  bindForm('#user-register-form', data => apiPost('/api/register', data));
  bindForm('#restaurant-login-form', data => apiPost('/api/restaurant/login', data));
  bindForm('#restaurant-register-form', data => apiPost('/api/restaurant/register', data));
  bindForm('#logout-form', () => apiPost('/api/logout', {}));
}

if (document.readyState !== 'loading') {
  bindForms();
} else {
  document.addEventListener('DOMContentLoaded', bindForms);
}
